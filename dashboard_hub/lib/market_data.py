"""Live market data — search, history and risk stats for any listed security.

No warehouse, no `.env`, no API key: this reads Yahoo Finance at request time, so
the Stock Explorer works on a clean checkout and is not limited to the 38 names
in `companies.yml`.

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


def _cached(key: tuple, produce, ttl: int = _DEFAULT_TTL):
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = produce()
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

    def run() -> list[dict]:
        seen: set[str] = set()
        stories: list[dict] = []
        for symbol in definition["symbols"][:_NEWS_TICKERS]:
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

    return _cached(("news", slug, limit), run, ttl=_NEWS_TTL)
