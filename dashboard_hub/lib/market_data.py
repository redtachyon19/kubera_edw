"""Live market data — search, history and risk stats for any listed security.

No warehouse, no `.env`, no API key: this reads Yahoo Finance at request time, so
the Stock Explorer works on a clean checkout and is not limited to the 38 names
in `companies.yml`.

Yahoo's JSON hosts reject plain requests without a session cookie and crumb,
which is why this goes through `yfinance` (it impersonates a browser and manages
that handshake) rather than the frontend calling Yahoo directly.
"""

from __future__ import annotations

import math
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
