"""Live market data — search, history and risk stats for any listed security.

Mostly no warehouse, no `.env`, no API key: this reads Yahoo Finance at request
time, so the Stock Explorer works on a clean checkout and is not limited to the
38 names in `companies.yml`. The one exception is the Companies desk, which adds
an as-filed panel for the names the warehouse does carry — and does without it,
rather than failing, when there is no warehouse to read.

Yahoo's JSON hosts reject plain requests without a session cookie and crumb,
which is why this goes through `yfinance` (it impersonates a browser and manages
that handshake) rather than the frontend calling Yahoo directly.
"""

from __future__ import annotations

import functools
import json
import math
import pathlib
import time
from typing import Any

import pandas as pd
import yfinance as yf

from . import filings, warehouse

# Window -> (Yahoo period, bar interval). Yahoo caps how far back each interval
# reaches — 1m is 7 days, sub-hourly is 60 days, hourly is 2 years — so short
# windows take fine bars and long ones fall back to daily.
PERIODS: dict[str, tuple[str, str]] = {
    "1D": ("1d", "1m"),
    "1W": ("5d", "30m"),
    "1M": ("1mo", "1h"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1d"),
    "10Y": ("10y", "1d"),
    "All time": ("max", "1d"),
}

GOLD_SYMBOL = "GC=F"
GOLD_LABEL = "Gold"

# How long a fetch stays warm, by window. A one-day chart is worthless if it is
# fifteen minutes stale; ten years of daily bars does not change intraday.
_TTL_BY_PERIOD: dict[str, int] = {
    "1D": 30,
    "1W": 60,
    "1M": 120,
    "3M": 600,
    "6M": 600,
    "1Y": 900,
}
_DEFAULT_TTL = 3600

_YEAR_SECONDS = 365.25 * 24 * 3600
# Annualising a move shorter than this says more about the window than the asset.
_MIN_YEARS_FOR_CAGR = 0.9
_MIN_YEARS_FOR_VOL = 0.02

# key -> (fetched_at, value). Small and process-local; the API server is a single
# long-lived process, so this is all the caching the hub needs.
_cache: dict[tuple, tuple[float, Any]] = {}


def _cached(key: tuple, produce, ttl: int = _DEFAULT_TTL, keep=None):
    """Memoise `produce` for `ttl` seconds.

    `keep` guards against poisoning: Yahoo answers a throttled request with a
    partial frame rather than an error, and caching that would serve a
    half-empty sector list for the full TTL. A result that fails the predicate
    is returned to this caller but not stored, so the next request retries.
    """
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = produce()
    if keep is None or keep(value):
        _cache[key] = (now, value)
    return value


def search(query: str, limit: int = 8) -> list[dict]:
    """Listings matching a free-text name or ticker fragment."""
    query = query.strip()
    if not query:
        return []

    def run() -> list[dict]:
        try:
            quotes = yf.Search(query, max_results=limit).quotes
        except Exception:  # noqa: BLE001 — a lookup outage degrades to "no matches"
            return []
        out: list[dict] = []
        for quote in quotes:
            symbol = quote.get("symbol")
            if not symbol:
                continue
            out.append(
                {
                    "symbol": symbol,
                    "name": quote.get("shortname") or quote.get("longname") or symbol,
                    "type": (quote.get("quoteType") or "").title(),
                    "exchange": quote.get("exchDisp") or quote.get("exchange") or "",
                }
            )
        return out

    return _cached(("search", query.lower(), limit), run)


def _closes(symbols: tuple[str, ...], period: str, interval: str, prepost: bool) -> pd.DataFrame:
    """Split/dividend-adjusted closes at `interval`, one column per symbol.

    `prepost` matters more than it looks: outside regular hours an equity has no
    regular-session bars at all, so a one-day chart would show its last close
    from the previous session and look frozen. With extended hours included, the
    same request returns quotes seconds old.
    """
    if not symbols:
        return pd.DataFrame()
    raw = yf.download(
        list(symbols),
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        group_by="column",
        prepost=prepost,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()

    frame = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        frame.columns = [symbols[0]]
    frame = frame.dropna(axis=1, how="all")

    # Intraday bars come back tz-aware; daily bars do not. Normalise to naive so
    # both paths format and compare the same way.
    index = pd.to_datetime(frame.index)
    frame.index = index.tz_convert(None) if index.tz is not None else index.tz_localize(None)
    return frame[[s for s in symbols if s in frame.columns]].sort_index()


def _currency(symbol: str) -> str:
    def run() -> str:
        try:
            return str(yf.Ticker(symbol).fast_info.get("currency") or "")
        except Exception:  # noqa: BLE001
            return ""

    return _cached(("ccy", symbol), run, ttl=3600)


def _align(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp | None, str | None]:
    """Put every series on one clock starting where they all have data.

    Equities, futures and foreign listings keep different sessions — gold trades
    while an equity market is shut — so a raw join leaves gaps. Gaps are carried
    forward; the window then starts at the latest first-quote across the
    selection, because rebasing series that begin at different points would
    flatter whichever one started earliest.
    """
    if frame.empty:
        return frame, None, None
    filled = frame.ffill().dropna(how="all")
    firsts = {c: filled[c].first_valid_index() for c in filled.columns}
    firsts = {c: i for c, i in firsts.items() if i is not None}
    if not firsts:
        return pd.DataFrame(), None, None
    start = max(firsts.values())
    limiting = max(firsts, key=lambda c: firsts[c]) if len(firsts) > 1 else None
    return filled.loc[start:].dropna(how="any"), start, limiting


def _stats(series: pd.Series) -> dict:
    """Return and risk over the window, annualised only where that is honest."""
    span = (series.index[-1] - series.index[0]).total_seconds()
    years = span / _YEAR_SECONDS if span > 0 else 0.0
    growth = series.iloc[-1] / series.iloc[0]
    steps = series.pct_change().dropna()
    drawdown = (series / series.cummax() - 1).min()

    cagr = None
    if years >= _MIN_YEARS_FOR_CAGR and growth > 0:
        cagr = float(growth ** (1 / years) - 1)

    vol = None
    if years >= _MIN_YEARS_FOR_VOL and len(steps) > 2:
        # Bars per year measured from the data, so intraday and daily windows are
        # both annualised with the right factor rather than a hardcoded 252.
        bars_per_year = len(steps) / years
        vol = float(steps.std() * math.sqrt(bars_per_year))

    return {
        "startPrice": float(series.iloc[0]),
        "endPrice": float(series.iloc[-1]),
        "totalReturn": float(growth - 1),
        "cagr": cagr,
        "annualisedVol": vol,
        "maxDrawdown": float(drawdown) if not math.isnan(drawdown) else None,
    }


def history(symbols: list[str], period_label: str) -> dict:
    """Aligned closes plus per-symbol risk stats, ready for the browser.

    Args:
        symbols: Tickers to compare.
        period_label: A key of `PERIODS`, e.g. "1D", "6M" or "All time".

    Returns:
        `{dates, series[], start, limiting, missing[], intraday, interval}`.
        Prices are aligned, so the client can rebase, index or plot them raw
        without refetching.
    """
    period, interval = PERIODS.get(period_label, PERIODS["5Y"])
    intraday = interval.endswith(("m", "h"))
    wanted = tuple(dict.fromkeys(symbols))
    empty = {
        "dates": [],
        "series": [],
        "start": None,
        "limiting": None,
        "missing": [],
        "intraday": intraday,
        "interval": interval,
    }
    if not wanted:
        return empty

    # Extended hours only for intraday windows: it is what makes a same-day chart
    # current when the regular session is shut.
    prepost = intraday
    frame = _cached(
        ("hist", wanted, period, interval, prepost),
        lambda: _closes(wanted, period, interval, prepost),
        ttl=_TTL_BY_PERIOD.get(period_label, _DEFAULT_TTL),
        keep=lambda f: len(f.columns) >= len(wanted) * 0.9,
    )
    missing = [s for s in wanted if s not in frame.columns]
    aligned, start, limiting = _align(frame)
    if aligned.empty:
        return {**empty, "missing": missing}

    stamp = "%Y-%m-%dT%H:%M" if intraday else "%Y-%m-%d"
    series = []
    for symbol in aligned.columns:
        column = aligned[symbol].dropna()
        if len(column) < 2:
            continue
        series.append(
            {
                "symbol": symbol,
                "label": GOLD_LABEL if symbol == GOLD_SYMBOL else symbol,
                "isGold": symbol == GOLD_SYMBOL,
                "currency": _currency(symbol),
                "closes": [round(float(v), 4) for v in aligned[symbol]],
                **_stats(column),
            }
        )

    return {
        "dates": [d.strftime(stamp) for d in aligned.index],
        "series": series,
        "start": start.strftime(stamp) if start is not None else None,
        "limiting": limiting,
        "missing": missing,
        "intraday": intraday,
        "interval": interval,
    }


def quotes(symbols: tuple[str, ...]) -> list[dict]:
    """Last price and move on the day, for the ticker tape.

    Args:
        symbols: Tickers to quote.

    Returns:
        One dict per symbol that returned data, in the order requested. A symbol
        that fails is skipped rather than raising — a tape with nine of ten
        entries is better than no tape.
    """

    def one(symbol: str) -> dict | None:
        try:
            info = yf.Ticker(symbol).fast_info
            last, prev = info.get("lastPrice"), info.get("previousClose")
            if last is None or not prev:
                return None
            return {
                "symbol": symbol,
                "price": float(last),
                "previousClose": float(prev),
                "change": float(last) - float(prev),
                "changePct": float(last) / float(prev) - 1,
                "currency": str(info.get("currency") or ""),
            }
        except Exception:  # noqa: BLE001 — one bad symbol must not empty the tape
            return None

    out = []
    for symbol in symbols:
        quote = _cached(("quote", symbol), lambda s=symbol: one(s), ttl=45)
        if quote:
            out.append(quote)
    return out


_SECTORS_PATH = pathlib.Path(__file__).resolve().parents[1] / "sectors.json"


@functools.lru_cache(maxsize=1)
def sectors() -> list[dict]:
    """Editorial sector definitions from `sectors.json`."""
    with _SECTORS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)["sectors"]


def sector(slug: str) -> dict | None:
    return next((s for s in sectors() if s["slug"] == slug), None)


# RiskMetrics daily decay — the standard weighting for "recent counts more".
_EWMA_LAMBDA = 0.94
_ROLL_MIN = 20
_SPARK_POINTS = 36


def _grid(matrix: pd.DataFrame, labels: list[str]) -> list[list[float | None]]:
    """A correlation frame as a plain nested list, aligned to `labels`."""
    matrix = matrix.reindex(index=labels, columns=labels)
    return [
        [None if pd.isna(v) else round(float(v), 4) for v in matrix.loc[row].tolist()]
        for row in labels
    ]


def _matrices(returns: pd.DataFrame) -> tuple[list[str], dict[str, list[list[float | None]]]]:
    """Four readings of the same relationships, because one number hides a lot.

    pearson   linear co-movement over the whole window — the headline.
    spearman  the same on ranks, so a handful of gap days cannot dominate it.
    downside  conditioned on the basket falling. Diversification tends to fail
              exactly when it is needed, and an unconditional number cannot show
              that.
    ewma      exponentially weighted, so last month counts for more than a year
              ago. This is what "exponential" properly means here — prices are
              already de-trended by working in returns.
    """
    labels = list(returns.columns)
    basket = returns.mean(axis=1)
    down = returns[basket < 0]

    out = {
        "pearson": _grid(returns.corr(), labels),
        # Rank-then-Pearson is Spearman by definition, and avoids a scipy dependency.
        "spearman": _grid(returns.rank().corr(), labels),
        "downside": _grid(down.corr(), labels) if len(down) > _ROLL_MIN else [],
        "ewma": [],
    }
    try:
        weighted = returns.ewm(alpha=1 - _EWMA_LAMBDA).corr()
        out["ewma"] = _grid(weighted.loc[returns.index[-1]], labels)
    except (KeyError, ValueError):  # too few observations to weight
        out["ewma"] = []
    return labels, out


def _betas(returns: pd.DataFrame) -> dict[str, dict]:
    """Sensitivity to the basket, not just co-movement with it.

    Correlation says whether two things move together; beta says by how much. A
    name can track its sector almost perfectly and still swing twice as hard.
    """
    basket = returns.mean(axis=1)
    variance = float(basket.var())
    out: dict[str, dict] = {}
    for symbol in returns.columns:
        if not variance:
            out[symbol] = {"beta": None, "r2": None}
            continue
        correlation = returns[symbol].corr(basket)
        out[symbol] = {
            "beta": round(float(returns[symbol].cov(basket) / variance), 4),
            "r2": None if pd.isna(correlation) else round(float(correlation**2), 4),
        }
    return out


def _rolling(returns: pd.DataFrame, a: str, b: str) -> dict | None:
    """How much the pair's correlation actually moves over the window.

    A headline of +0.71 can be a band from +0.40 to +0.90; the range is often
    more informative than the average.
    """
    window = max(_ROLL_MIN, min(60, len(returns) // 4))
    if len(returns) < window + 5:
        return None
    series = returns[a].rolling(window).corr(returns[b]).dropna()
    if series.empty:
        return None
    step = max(1, len(series) // _SPARK_POINTS)
    return {
        "min": round(float(series.min()), 3),
        "median": round(float(series.median()), 3),
        "max": round(float(series.max()), 3),
        "window": window,
        "series": [round(float(v), 3) for v in series.iloc[::step].tolist()],
    }


def sector_snapshot(symbols: list[str], period_label: str) -> dict:
    """Constituents, performance and pairwise correlation for a basket.

    Correlation is computed on returns, never on price. Two securities can both
    drift upward and look related on a price chart while their day-to-day moves
    are unconnected — it is the returns that say whether they travel together.

    Args:
        symbols: Tickers in the basket.
        period_label: A key of `PERIODS`.

    Returns:
        `{constituents, labels, matrix, pairs, missing, interval, start}` where
        `pairs` is every pairing sorted by correlation, strongest first.
    """
    period, interval = PERIODS.get(period_label, PERIODS["1Y"])
    intraday = interval.endswith(("m", "h"))
    wanted = tuple(dict.fromkeys(symbols))
    blank = {
        "constituents": [],
        "labels": [],
        "matrices": {},
        "pairs": [],
        "observations": 0,
        "downDays": 0,
        "missing": list(wanted),
        "interval": interval,
        "start": None,
    }
    if not wanted:
        return blank

    frame = _cached(
        ("hist", wanted, period, interval, intraday),
        lambda: _closes(wanted, period, interval, intraday),
        ttl=_TTL_BY_PERIOD.get(period_label, _DEFAULT_TTL),
        keep=lambda f: len(f.columns) >= len(wanted) * 0.9,
    )
    missing = [s for s in wanted if s not in frame.columns]
    aligned, start, _ = _align(frame)
    if aligned.empty:
        return {**blank, "missing": missing}

    returns = aligned.pct_change().dropna(how="any")
    labels, matrices = _matrices(returns)
    betas = _betas(returns)

    constituents = []
    for symbol in aligned.columns:
        column = aligned[symbol].dropna()
        if len(column) < 2:
            continue
        stats = _stats(column)
        constituents.append(
            {
                "symbol": symbol,
                "currency": _currency(symbol),
                "last": stats["endPrice"],
                "periodReturn": stats["totalReturn"],
                "annualisedVol": stats["annualisedVol"],
                "maxDrawdown": stats["maxDrawdown"],
                **betas.get(symbol, {"beta": None, "r2": None}),
            }
        )
    constituents.sort(key=lambda c: c["periodReturn"], reverse=True)

    pearson = matrices["pearson"]
    downside = matrices["downside"]
    pairs = []
    for i, a in enumerate(labels):
        for j in range(i + 1, len(labels)):
            value = pearson[i][j]
            if value is None:
                continue
            pairs.append(
                {
                    "a": a,
                    "b": labels[j],
                    "correlation": value,
                    "downside": downside[i][j] if downside else None,
                    "rolling": _rolling(returns, a, labels[j]),
                }
            )
    pairs.sort(key=lambda p: p["correlation"], reverse=True)

    return {
        "constituents": constituents,
        "labels": labels,
        "matrices": matrices,
        "pairs": pairs,
        "observations": len(returns),
        "downDays": int((returns.mean(axis=1) < 0).sum()),
        "missing": missing,
        "interval": interval,
        "start": start.strftime("%Y-%m-%dT%H:%M" if intraday else "%Y-%m-%d"),
    }


def sectors_overview(period_label: str) -> list[dict]:
    """Every sector with its equal-weighted return over the window.

    All constituents across all sectors are fetched in a single batch — twelve
    separate downloads would take far longer than one call for the ~100 unique
    tickers they share between them.
    """
    period, interval = PERIODS.get(period_label, PERIODS["1Y"])
    every = tuple(dict.fromkeys(s for sec in sectors() for s in sec["symbols"]))
    frame = _cached(
        ("overview", every, period, interval),
        lambda: _closes(every, period, interval, False),
        ttl=_TTL_BY_PERIOD.get(period_label, _DEFAULT_TTL),
        # A throttled batch comes back with most columns missing; serve it once
        # rather than pinning it for the next quarter of an hour.
        keep=lambda f: len(f.columns) >= len(every) * 0.9,
    )

    out = []
    for sec in sectors():
        moves: list[tuple[str, float]] = []
        for symbol in sec["symbols"]:
            if symbol not in frame.columns:
                continue
            column = frame[symbol].dropna()
            if len(column) < 2 or not column.iloc[0]:
                continue
            moves.append((symbol, float(column.iloc[-1] / column.iloc[0] - 1)))
        moves.sort(key=lambda m: m[1], reverse=True)
        out.append(
            {
                "slug": sec["slug"],
                "name": sec["name"],
                "blurb": sec["blurb"],
                "count": len(sec["symbols"]),
                "priced": len(moves),
                "averageReturn": (sum(m[1] for m in moves) / len(moves)) if moves else None,
                "best": {"symbol": moves[0][0], "return": moves[0][1]} if moves else None,
                "worst": {"symbol": moves[-1][0], "return": moves[-1][1]} if moves else None,
            }
        )
    return out


_NEWS_TTL = 600
_NEWS_TICKERS = 5
_NEWS_LIMIT = 12
_NEWS_PER_TICKER = 8


def _story(item: dict) -> dict | None:
    """Flatten one Yahoo news item to what the card needs.

    Only the headline, source, timestamp, image and link are kept — this is a
    reading list, not a content pipeline, and nothing here is parsed for meaning.
    """
    content = item.get("content") or item
    title = (content.get("title") or "").strip()
    link = (content.get("canonicalUrl") or content.get("clickThroughUrl") or {}).get("url")
    if not title or not link:
        return None

    resolutions = (content.get("thumbnail") or {}).get("resolutions") or []
    # Prefer a small rendition; the originals run to 1400px and would dwarf a card.
    small = next((r.get("url") for r in resolutions if r.get("tag") != "original"), None)

    return {
        "id": content.get("id") or link,
        "title": title,
        "summary": (content.get("summary") or content.get("description") or "").strip()[:240],
        "url": link,
        "publisher": (content.get("provider") or {}).get("displayName") or "",
        "published": content.get("pubDate") or content.get("displayTime"),
        "thumbnail": small or (resolutions[0].get("url") if resolutions else None),
    }


def sector_news(slug: str, limit: int = _NEWS_LIMIT) -> list[dict]:
    """Recent coverage across a sector's largest names.

    Yahoo publishes news per ticker, not per industry, so a sector feed is the
    union over a handful of its constituents — deduplicated, because the same
    wire story is routinely attached to every name it mentions.
    """
    definition = sector(slug)
    if not definition:
        return []

    return _cached(
        ("news", slug, limit),
        lambda: _coverage(definition["symbols"][:_NEWS_TICKERS], limit),
        ttl=_NEWS_TTL,
    )


def _coverage(symbols: list[str], limit: int) -> list[dict]:
    """Recent stories across several tickers, newest first and deduplicated.

    The same wire story is routinely filed against every name it mentions, so the
    union has to be keyed on the article rather than on the ticker that carried it.
    """
    seen: set[str] = set()
    stories: list[dict] = []
    for symbol in symbols:
        try:
            items = yf.Ticker(symbol).news or []
        except Exception:  # noqa: BLE001 — one dead feed must not empty the list
            continue
        for item in items:
            story = _story(item)
            if not story:
                continue
            key = story["url"].split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            stories.append({**story, "ticker": symbol})
    stories.sort(key=lambda s: s.get("published") or "", reverse=True)
    return stories[:limit]


def company_news(symbol: str, limit: int = _NEWS_PER_TICKER) -> list[dict]:
    """Recent coverage for one listing."""
    symbol = symbol.strip()
    if not symbol:
        return []
    return _cached(("conews", symbol, limit), lambda: _coverage([symbol], limit), ttl=_NEWS_TTL)


# ── Companies ─────────────────────────────────────────────────────────────────
#
# The Companies desk browses a fixed universe and then opens one name in depth.
# Both halves read Yahoo live, the same as the rest of this module; the names and
# classifications behind the grid are the one thing resolved ahead of time, in
# `companies.json`, because ~300 profile lookups is not a page load.

_COMPANIES_PATH = pathlib.Path(__file__).resolve().parents[1] / "companies.json"

# Filed statements move once a quarter, so they can stay warm far longer than a
# price. The profile block carries the market cap and the multiples, which do
# move intraday, and is refreshed on its own clock.
_STATEMENT_TTL = 6 * 3600
_PROFILE_TTL = 300
_PERIODS_KEPT = 8
_PEERS = 8

# Shortest gap between two periods of the same cadence. Yahoo's annual statements
# for a foreign filer sometimes carry an interim column — Toyota's annual income
# statement lists 2025-06-30 and 2025-09-30 beside its 03-31 year ends — and a
# calendar-year rule cannot tell those apart from a real 52/53-week year end that
# drifts by a few days. Spacing can.
_MIN_GAP_DAYS = {True: 300, False: 45}


@functools.lru_cache(maxsize=1)
def companies() -> list[dict]:
    """The browsable universe from `companies.json`.

    Returns:
        One dict per listing — symbol, name, Yahoo's classification, the sector
        slugs it belongs to, and whether the warehouse holds filings for it.
        Empty if the file has not been generated yet.
    """
    try:
        with _COMPANIES_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)["companies"]
    except (OSError, KeyError, json.JSONDecodeError):
        return []


@functools.lru_cache(maxsize=1)
def _by_symbol() -> dict[str, dict]:
    return {entry["symbol"]: entry for entry in companies()}


def companies_overview(period_label: str) -> list[dict]:
    """The whole universe with its move over the window.

    Every symbol is priced in a single batch — one download for ~300 names rather
    than one per card — so the grid costs about what a single sector costs.
    """
    period, interval = PERIODS.get(period_label, PERIODS["1Y"])
    universe = companies()
    every = tuple(entry["symbol"] for entry in universe)
    if not every:
        return []

    frame = _cached(
        ("universe", every, period, interval),
        lambda: _closes(every, period, interval, False),
        ttl=_TTL_BY_PERIOD.get(period_label, _DEFAULT_TTL),
        # A throttled batch returns most columns missing; serve it once rather
        # than pinning a near-empty grid for the rest of the TTL.
        keep=lambda f: len(f.columns) >= len(every) * 0.9,
    )

    out = []
    for entry in universe:
        symbol = entry["symbol"]
        last: float | None = None
        move: float | None = None
        if symbol in frame.columns:
            column = frame[symbol].dropna()
            if len(column) >= 2 and column.iloc[0]:
                last = float(column.iloc[-1])
                move = float(column.iloc[-1] / column.iloc[0] - 1)
        out.append({**entry, "last": last, "periodReturn": move})
    return out


def _info(symbol: str) -> dict:
    def run() -> dict:
        try:
            return yf.Ticker(symbol).info or {}
        except Exception:  # noqa: BLE001 — a page without multiples beats no page
            return {}

    # A throttled profile request comes back thin rather than failing, and pinning
    # that for the TTL would show a page of em dashes for five minutes. Serve it,
    # do not keep it: the next load asks again.
    return _cached(
        ("info", symbol),
        run,
        ttl=_PROFILE_TTL,
        keep=lambda payload: bool(payload.get("marketCap")),
    )


def _number(value: Any) -> float | None:
    """A JSON-safe float, or None for anything that is not a real number.

    Yahoo returns NaN for a line an issuer does not report — a bank has no gross
    profit — and NaN is not valid JSON. Every absent figure becomes null here so
    the table can draw an em dash rather than the string "NaN".
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _pick(frame: pd.DataFrame, column: Any, *labels: str) -> float | None:
    """First of `labels` that this issuer actually reports, as a number.

    Yahoo normalises statement rows but does not make them universal: a bank's
    income statement has no `Operating Income`, an asset-light filer no
    `Cost Of Revenue`. Each figure is therefore a short list of the labels it can
    legitimately arrive under, in order of preference.
    """
    for label in labels:
        if label in frame.index:
            value = _number(frame.at[label, column])
            if value is not None:
                return value
    return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


# label -> the statement rows it may arrive under, best first.
_INCOME = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "costOfRevenue": ("Cost Of Revenue", "Reconciled Cost Of Revenue"),
    "grossProfit": ("Gross Profit",),
    "researchDevelopment": ("Research And Development",),
    "sellingGeneralAdmin": ("Selling General And Administration",),
    "operatingExpense": ("Operating Expense",),
    "operatingIncome": ("Operating Income", "Total Operating Income As Reported", "EBIT"),
    "ebitda": ("EBITDA", "Normalized EBITDA"),
    "interestExpense": ("Interest Expense", "Interest Expense Non Operating"),
    "pretaxIncome": ("Pretax Income",),
    "taxProvision": ("Tax Provision",),
    "netIncome": ("Net Income", "Net Income Common Stockholders"),
    "dilutedEps": ("Diluted EPS",),
    "dilutedShares": ("Diluted Average Shares",),
}

_BALANCE = {
    "cash": (
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash Financial",
    ),
    "totalDebt": ("Total Debt",),
    "netDebt": ("Net Debt",),
    "totalAssets": ("Total Assets",),
    "totalLiabilities": ("Total Liabilities Net Minority Interest",),
    "equity": (
        "Stockholders Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ),
    "currentAssets": ("Current Assets",),
    "currentLiabilities": ("Current Liabilities",),
    "workingCapital": ("Working Capital",),
}

_CASHFLOW = {
    "operatingCashFlow": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    "investingCashFlow": ("Investing Cash Flow", "Cash Flow From Continuing Investing Activities"),
    "financingCashFlow": ("Financing Cash Flow", "Cash Flow From Continuing Financing Activities"),
    "capitalExpenditure": ("Capital Expenditure",),
    "freeCashFlow": ("Free Cash Flow",),
    "dividendsPaid": ("Cash Dividends Paid", "Common Stock Dividend Paid"),
    "buybacks": ("Repurchase Of Capital Stock",),
}


def _period(frames: dict[str, pd.DataFrame], column: Any, annual: bool) -> dict:
    """One reporting period across all three statements, plus what they imply.

    The ratios are derived here rather than in the browser because they belong to
    the period, not to the rendering: a margin computed against the wrong year's
    revenue is a different number, and doing it once removes that chance.
    """
    income = frames.get("income")
    balance = frames.get("balance")
    cashflow = frames.get("cashflow")

    figures: dict[str, float | None] = {}
    for target, source in ((_INCOME, income), (_BALANCE, balance), (_CASHFLOW, cashflow)):
        for key, labels in target.items():
            figures[key] = (
                _pick(source, column, *labels)
                if source is not None and column in source.columns
                else None
            )

    revenue = figures["revenue"]
    # Yahoo reports capex as a negative outflow; free cash flow is derived only
    # when it is not published, and then with the sign it already carries.
    if figures["freeCashFlow"] is None and figures["operatingCashFlow"] is not None:
        capex = figures["capitalExpenditure"]
        figures["freeCashFlow"] = figures["operatingCashFlow"] + (capex or 0.0)

    stamp = pd.Timestamp(column)
    return {
        "end": stamp.strftime("%Y-%m-%d"),
        "label": str(stamp.year) if annual else stamp.strftime("%b %Y"),
        **figures,
        "grossMargin": _ratio(figures["grossProfit"], revenue),
        "operatingMargin": _ratio(figures["operatingIncome"], revenue),
        "ebitdaMargin": _ratio(figures["ebitda"], revenue),
        "netMargin": _ratio(figures["netIncome"], revenue),
        "fcfMargin": _ratio(figures["freeCashFlow"], revenue),
        "effectiveTaxRate": _ratio(figures["taxProvision"], figures["pretaxIncome"]),
        "netDebtToEbitda": _ratio(figures["netDebt"], figures["ebitda"]),
        "debtToEquity": _ratio(figures["totalDebt"], figures["equity"]),
        "currentRatio": _ratio(figures["currentAssets"], figures["currentLiabilities"]),
        "returnOnEquity": _ratio(figures["netIncome"], figures["equity"]),
    }


# The top line of each statement. A period without any of them is padding, not a
# reporting period — Yahoo's oldest annual column routinely carries one stray
# figure (Apple's 2021 arrives with an interest expense and nothing else), which
# is enough to pass a "has any value" test and draws a column of em dashes.
_ANCHORS = ("revenue", "netIncome", "totalAssets", "operatingCashFlow")


def _reports(period: dict) -> bool:
    """True when a period carries the top line of at least one statement."""
    return any(period.get(key) is not None for key in _ANCHORS)


def _spine(columns: set, annual: bool) -> list:
    """The reporting dates of one cadence, oldest first.

    Walks back from the most recent column and keeps the next only once a full
    period has elapsed, which drops interim columns mixed into an annual
    statement without also dropping a 52/53-week year end that lands a few days
    off its usual date.
    """
    gap = pd.Timedelta(days=_MIN_GAP_DAYS[annual])
    kept: list = []
    for stamp in sorted({pd.Timestamp(c) for c in columns}, reverse=True):
        if not kept or kept[-1] - stamp >= gap:
            kept.append(stamp)
    return list(reversed(kept))


def _statements(symbol: str) -> dict:
    """Annual and quarterly statements for one issuer, oldest period first.

    Returns:
        `{annual: [...], quarterly: [...]}`. Either list is empty when Yahoo has
        no filings for the symbol — an index or a currency pair, say.
    """

    def run() -> dict:
        ticker = yf.Ticker(symbol)
        out: dict[str, list[dict]] = {"annual": [], "quarterly": []}
        for cadence, attributes in (
            ("annual", ("income_stmt", "balance_sheet", "cashflow")),
            (
                "quarterly",
                ("quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow"),
            ),
        ):
            frames: dict[str, pd.DataFrame] = {}
            for name, attribute in zip(("income", "balance", "cashflow"), attributes, strict=True):
                try:
                    frame = getattr(ticker, attribute)
                except Exception:  # noqa: BLE001 — a missing statement is not an error
                    frame = None
                if frame is not None and not frame.empty:
                    frames[name] = frame
            if not frames:
                continue
            annual = cadence == "annual"
            columns = _spine({c for frame in frames.values() for c in frame.columns}, annual)
            periods = [_period(frames, column, annual) for column in columns]
            # Yahoo pads the oldest column of a statement it only partly holds —
            # Toyota's 2022 arrives with one populated row out of forty-five. A
            # column with nothing on any of the three statements is a header, not
            # a period, and drawing it puts a year of em dashes across the page.
            out[cadence] = [p for p in periods if _reports(p)][-_PERIODS_KEPT:]
        return out

    return _cached(("stmts", symbol), run, ttl=_STATEMENT_TTL)


def _peers(symbol: str) -> tuple[list[dict], list[str]]:
    """Sectors this name sits in, and the other names sitting in them."""
    entry = _by_symbol().get(symbol)
    slugs = list((entry or {}).get("sectors") or [])
    memberships = [{"slug": s["slug"], "name": s["name"]} for s in sectors() if s["slug"] in slugs]

    seen: list[str] = []
    for sector_def in sectors():
        if sector_def["slug"] not in slugs:
            continue
        for other in sector_def["symbols"]:
            if other != symbol and other not in seen:
                seen.append(other)
    lookup = _by_symbol()
    peers = [{"symbol": s, "name": (lookup.get(s) or {}).get("name") or s} for s in seen[:_PEERS]]
    return memberships, peers


def company(symbol: str) -> dict:
    """Everything the detail page draws for one listing.

    Args:
        symbol: A Yahoo ticker. It need not be in `companies.json` — anything the
            search box turns up opens the same way.

    Returns:
        `{symbol, profile, kpis, statements, warehouse, sectors, peers}`.
        `statements` are in the issuer's reporting currency, which is not always
        the currency its shares trade in; both are stated in `profile`.
    """
    symbol = symbol.strip()
    if not symbol:
        return {}

    info = _info(symbol)
    entry = _by_symbol().get(symbol, {})
    memberships, peers = _peers(symbol)

    # Yahoo gives the yield as a percentage here (0.35 means 0.35%), unlike every
    # other rate in this module — divided once, so the client formats one way.
    dividend_yield = _number(info.get("dividendYield"))

    profile = {
        "name": info.get("longName") or info.get("shortName") or entry.get("name") or symbol,
        "sector": info.get("sector") or entry.get("sector") or "",
        "industry": info.get("industry") or entry.get("industry") or "",
        "country": info.get("country") or entry.get("country") or "",
        "website": info.get("website") or "",
        "employees": _number(info.get("fullTimeEmployees")),
        "exchange": info.get("fullExchangeName") or info.get("exchange") or entry.get("exchange"),
        "currency": info.get("currency") or entry.get("currency") or "",
        "reportingCurrency": info.get("financialCurrency") or "",
        "inWarehouse": bool(entry.get("warehouse")),
    }

    # An ADR trades in one currency and files in another, and Yahoo builds some
    # of its ratios across the two without converting: Toyota's US line comes
    # back with a price/sales of 0.004 (USD price over JPY sales) and a
    # price/book of 15.4 against the 1.0 its Tokyo line reports. Those are drawn
    # from the same fields for every listing, so they cannot be trusted here and
    # are withheld rather than printed as figures. Trailing P/E survives because
    # Yahoo does convert the EPS behind it, and the enterprise value survives as
    # a level — it is simply denominated in the reporting currency, not the
    # trading one, which is what the panel labels it with.
    mixed = bool(
        profile["reportingCurrency"]
        and profile["currency"]
        and profile["reportingCurrency"] != profile["currency"]
    )

    kpis = {
        "price": _number(info.get("currentPrice") or info.get("regularMarketPrice")),
        "previousClose": _number(info.get("regularMarketPreviousClose")),
        "marketCap": _number(info.get("marketCap")),
        "enterpriseValue": _number(info.get("enterpriseValue")),
        "trailingPe": _number(info.get("trailingPE")),
        "forwardPe": _number(info.get("forwardPE")),
        "priceToBook": None if mixed else _number(info.get("priceToBook")),
        "priceToSales": None if mixed else _number(info.get("priceToSalesTrailing12Months")),
        "evToEbitda": None if mixed else _number(info.get("enterpriseToEbitda")),
        "dividendYield": None if dividend_yield is None else dividend_yield / 100,
        "payoutRatio": _number(info.get("payoutRatio")),
        "beta": _number(info.get("beta")),
        "high52": _number(info.get("fiftyTwoWeekHigh")),
        "low52": _number(info.get("fiftyTwoWeekLow")),
        "eps": _number(info.get("trailingEps")),
        "profitMargin": _number(info.get("profitMargins")),
        "returnOnEquity": _number(info.get("returnOnEquity")),
        "revenueGrowth": _number(info.get("revenueGrowth")),
        "sharesOutstanding": _number(info.get("sharesOutstanding")),
        "averageVolume": _number(info.get("averageVolume")),
        "mixedCurrency": mixed,
    }

    return {
        "symbol": symbol,
        "profile": profile,
        "kpis": kpis,
        "statements": _statements(symbol),
        "warehouse": _filed(symbol),
        "sectors": memberships,
        "peers": peers,
    }


# A series shorter than this is not worth a long-run chart, and is the signal to
# try the next source rather than draw eight points across twenty years of axis.
_MIN_QUARTERS = 8


def _warehouse_quarters(ticker: str) -> list[dict]:
    """Filed quarters from the marts, with the missing fourth one derived.

    The warehouse carries what the filer published, and a 10-K filer never
    publishes a fourth quarter — the annual report covers it. A fiscal year with
    exactly three quarters is therefore missing one by construction, and the
    annual revenue less those three is what it was.
    """
    rows = warehouse.quarterly(ticker)
    if not rows:
        return []

    annual = {
        int(row["fiscal_year"]): row
        for row in warehouse.financials(ticker)
        if row.get("fiscal_year") and row.get("revenue") is not None
    }

    points: list[dict] = []
    by_year: dict[int, list[dict]] = {}
    for row in rows:
        end = row["period_end_date"]
        points.append(
            {
                "end": end.isoformat() if hasattr(end, "isoformat") else str(end),
                "revenue": _number(row.get("revenue")),
                "grossProfit": _number(row.get("gross_profit")),
                "netIncome": _number(row.get("net_income")),
                "derived": False,
            }
        )
        if row.get("fiscal_year"):
            by_year.setdefault(int(row["fiscal_year"]), []).append(row)

    for year, quarters in by_year.items():
        full = annual.get(year)
        if full is None or len(quarters) != 3:
            continue
        covered = sum(_number(q.get("revenue")) or 0.0 for q in quarters)
        end = full.get("period_end_date")
        stamp = end.isoformat() if hasattr(end, "isoformat") else str(end)
        if any(point["end"] == stamp for point in points):
            continue

        # Every line the chart draws gets the same treatment: the year less the
        # three quarters that were published.
        def remainder(key: str, year=full, three=quarters) -> float | None:
            whole = _number(year.get(key))
            if whole is None:
                return None
            return whole - sum(_number(q.get(key)) or 0.0 for q in three)

        points.append(
            {
                "end": stamp,
                "revenue": (_number(full.get("revenue")) or 0.0) - covered,
                "grossProfit": remainder("gross_profit"),
                "netIncome": remainder("net_income"),
                "derived": True,
            }
        )

    points.sort(key=lambda point: point["end"])
    for point in points:
        point["label"] = pd.Timestamp(point["end"]).strftime("%b %Y")
    return points


def _yahoo_points(periods: list[dict]) -> list[dict]:
    return [
        {
            "end": period["end"],
            "label": period["label"],
            "revenue": period["revenue"],
            "grossProfit": period["grossProfit"],
            "netIncome": period["netIncome"],
            "derived": False,
        }
        for period in periods
        if period["revenue"] is not None or period["netIncome"] is not None
    ]


def _warehouse_years(ticker: str) -> list[dict]:
    """Filed annual revenue from the marts, oldest first."""
    return [
        {
            "end": (
                row["period_end_date"].isoformat()
                if hasattr(row.get("period_end_date"), "isoformat")
                else str(row.get("period_end_date") or "")
            ),
            "label": str(int(row["fiscal_year"])) if row.get("fiscal_year") else "",
            "revenue": _number(row.get("revenue")),
            "grossProfit": _number(row.get("gross_profit")),
            "netIncome": _number(row.get("net_income")),
            "derived": False,
        }
        for row in warehouse.financials(ticker)
        if row.get("revenue") is not None
    ]


def _span_years(points: list[dict]) -> float:
    """How much time a series actually covers, in years."""
    if len(points) < 2:
        return 0.0
    first, last = pd.Timestamp(points[0]["end"]), pd.Timestamp(points[-1]["end"])
    return max(0.0, (last - first).days / 365.25)


def revenue_history(symbol: str) -> dict:
    """Revenue at the best cadence and the longest history obtainable.

    Both cadences are assembled and both are returned, because which one is
    worth reading depends on the filer. A US filer has seventy quarters and the
    quarterly series is the interesting one. A foreign private issuer files
    annually on Form 20-F and has no quarters at all — Yahoo will offer five,
    but its own filings carry twenty annual figures, and twenty years beats five
    quarters. The client shows the richer one first and offers the other.

    Each cadence is filled from whichever source reaches furthest back:

    SEC EDGAR, read live, going back to whenever the filer began tagging XBRL.

    The warehouse, for a held name — the same filings already landed, so this
    works with no network and no User-Agent.

    Yahoo, which publishes five quarters and four years, as the floor.

    Returns:
        `{quarterly, annual, currency, default, files}` where each cadence is
        `{points, source, derived}`. `files` is false for a listing that
        publishes no statements at all — an index, a fund or a currency — which
        is a different thing from a lookup that found nothing.
    """
    symbol = symbol.strip()
    blank = {"points": [], "source": "", "derived": 0}
    if not symbol:
        return {
            "quarterly": blank,
            "annual": blank,
            "currency": "",
            "default": "quarterly",
            "files": False,
            "edgar": filings.available(),
        }

    held = warehouse.holdings().get(symbol)
    edgar = filings.series(symbol, (held or {}).get("cik"))
    statements = _statements(symbol)
    currency = edgar["currency"] or _info(symbol).get("financialCurrency") or ""

    # Quarterly: EDGAR, then the marts, then the quote feed.
    quarterly = dict(blank)
    if len(edgar["quarterly"]) >= _MIN_QUARTERS:
        quarterly = {
            "points": edgar["quarterly"],
            "source": "SEC EDGAR company facts",
            "derived": edgar["derived"],
        }
    elif held:
        points = _warehouse_quarters(symbol)
        if len(points) >= _MIN_QUARTERS:
            quarterly = {
                "points": points,
                "source": "Kubera warehouse",
                "derived": sum(1 for point in points if point["derived"]),
            }
    if not quarterly["points"]:
        points = _yahoo_points(statements.get("quarterly") or [])
        if len(points) >= 2:
            quarterly = {"points": points, "source": "Yahoo Finance", "derived": 0}

    # Annual: the same three, in the same order.
    annual = dict(blank)
    if len(edgar["annual"]) >= 2:
        annual = {"points": edgar["annual"], "source": "SEC EDGAR company facts", "derived": 0}
    elif held:
        points = _warehouse_years(symbol)
        if len(points) >= 2:
            annual = {"points": points, "source": "Kubera warehouse", "derived": 0}
    if not annual["points"]:
        points = _yahoo_points(statements.get("annual") or [])
        if len(points) >= 2:
            annual = {"points": points, "source": "Yahoo Finance", "derived": 0}

    # Quarterly is the better read when it covers real ground and covers it
    # densely. Five quarters against twenty annual years is not a close call;
    # neither is nine quarters scattered across nine years, which is what a
    # foreign filer's occasional interim reporting looks like. Both lose to the
    # annual series the issuer actually publishes.
    quarterly_span = _span_years(quarterly["points"])
    dense = quarterly_span > 0 and len(quarterly["points"]) / quarterly_span >= 2
    default = (
        "quarterly"
        if (quarterly_span >= 3 and dense) or quarterly_span >= _span_years(annual["points"])
        else "annual"
    )

    return {
        "quarterly": quarterly,
        "annual": annual,
        "currency": currency,
        "default": default,
        "files": bool(quarterly["points"] or annual["points"]),
        # Whether the deep source was even reachable. Four annual periods is what
        # a page looks like both when a filer publishes nothing and when SEC is
        # switched off, and those are not the same thing to say.
        "edgar": filings.available(),
    }


def _backfill():
    """The queue module, imported late.

    `ingestion` pulls in httpx, tenacity and the rest of the extractor stack. The
    hub should not pay for that at import time to serve a price chart, and a
    checkout without those installed should still run the desk.
    """
    from ingestion import backfill

    return backfill


def request_backfill(symbol: str) -> dict:
    """Queue a company to be built into the warehouse.

    The hints come from what the desk already knows about the listing — Yahoo's
    name, sector and country — because SEC does not publish a sector and its
    registrant names are shouted ("NVIDIA CORP").
    """
    symbol = symbol.strip().upper()
    entry = _by_symbol().get(symbol, {})
    info = _info(symbol)
    hints = {
        "name": info.get("longName") or entry.get("name") or "",
        "sector": info.get("sector") or entry.get("sector") or "",
        "country": info.get("country") or entry.get("country") or "",
        "currency": info.get("currency") or entry.get("currency") or "USD",
    }
    return _backfill().request(symbol, {k: v for k, v in hints.items() if v})


def backfill_status(symbol: str) -> dict:
    """Where a company stands: held already, queued, running, done or failed."""
    symbol = symbol.strip().upper()
    if warehouse.holdings().get(symbol):
        return {"ticker": symbol, "status": "held"}
    try:
        row = _backfill().find(symbol)
    except ImportError:
        return {"ticker": symbol, "status": "unavailable"}
    return row or {"ticker": symbol, "status": "absent"}


def _filed(symbol: str) -> dict:
    """The warehouse's own view of this issuer, where it has one.

    This is the half of the page that is not Yahoo: figures parsed from the
    company's SEC filings and converted at the year-end rate. It covers only the
    38 names Kubera holds, so most companies return `held: false` and the page
    simply does not draw the panel.
    """
    held = warehouse.holdings().get(symbol)
    if not held:
        return {"held": False, "meta": None, "years": []}

    years = []
    for row in warehouse.financials(symbol):
        end = row.get("period_end_date")
        years.append(
            {
                "fiscalYear": int(row["fiscal_year"]) if row.get("fiscal_year") else None,
                "periodEnd": end.isoformat() if hasattr(end, "isoformat") else end,
                "reportingCurrency": row.get("reporting_currency") or "",
                "revenue": _number(row.get("revenue")),
                "revenueUsd": _number(row.get("revenue_usd")),
                "grossProfit": _number(row.get("gross_profit")),
                "operatingIncome": _number(row.get("operating_income")),
                "operatingIncomeUsd": _number(row.get("operating_income_usd")),
                "netIncome": _number(row.get("net_income")),
                "netIncomeUsd": _number(row.get("net_income_usd")),
                "ebitda": _number(row.get("ebitda")),
                "ebitdaUsd": _number(row.get("ebitda_usd")),
                "cash": _number(row.get("cash_and_equivalents")),
                "totalDebt": _number(row.get("total_debt")),
                "netDebt": _number(row.get("net_debt")),
                "netDebtUsd": _number(row.get("net_debt_usd")),
                "grossMargin": _number(row.get("gross_margin")),
                "ebitdaMargin": _number(row.get("ebitda_margin")),
                "netMargin": _number(row.get("net_margin")),
                "netDebtToEbitda": _number(row.get("net_debt_to_ebitda")),
                "ratePerUsd": _number(row.get("rate_per_usd")),
                "rateCarriedForward": bool(row.get("fx_rate_carried_forward")),
            }
        )

    return {
        "held": True,
        "meta": {
            "legalName": held.get("legal_name") or "",
            "cik": held.get("cik") or "",
            "sector": held.get("sector") or "",
            "filerType": held.get("filer_type") or "",
            "countryIso3": held.get("country_iso3") or "",
            "reportingCurrency": held.get("reporting_currency") or "",
            "taxonomy": held.get("xbrl_taxonomy") or "",
            "fiscalYearEnd": held.get("fiscal_year_end") or "",
        },
        "years": years,
    }
