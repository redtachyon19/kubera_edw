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

PERIODS: dict[str, str] = {"1Y": "1y", "5Y": "5y", "10Y": "10y", "All time": "max"}

GOLD_SYMBOL = "GC=F"
GOLD_LABEL = "Gold"

_TRADING_DAYS = 252
_TTL_SECONDS = 900

# symbol/period -> (fetched_at, value). Small and process-local; the API server is
# a single long-lived process, so this is all the caching the hub needs.
_cache: dict[tuple, tuple[float, Any]] = {}


def _cached(key: tuple, produce):
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _TTL_SECONDS:
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


def _closes(symbols: tuple[str, ...], period: str) -> pd.DataFrame:
    """Daily split/dividend-adjusted closes, one column per symbol."""
    if not symbols:
        return pd.DataFrame()
    raw = yf.download(
        list(symbols),
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    if raw is None or raw.empty:
        return pd.DataFrame()

    frame = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        frame.columns = [symbols[0]]
    frame = frame.dropna(axis=1, how="all")
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    return frame[[s for s in symbols if s in frame.columns]].sort_index()


def _currency(symbol: str) -> str:
    def run() -> str:
        try:
            return str(yf.Ticker(symbol).fast_info.get("currency") or "")
        except Exception:  # noqa: BLE001
            return ""

    return _cached(("ccy", symbol), run)


def _align(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp | None, str | None]:
    """Put every series on one calendar starting where they all have data.

    Equities, futures and foreign listings keep different trading calendars, so a
    raw join leaves gaps. Gaps are carried forward; the window then starts at the
    latest first-quote across the selection, because rebasing series that begin on
    different dates would flatter whichever one started earliest.
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
    years = (series.index[-1] - series.index[0]).days / 365.25
    growth = series.iloc[-1] / series.iloc[0]
    daily = series.pct_change().dropna()
    drawdown = (series / series.cummax() - 1).min()
    return {
        "startPrice": float(series.iloc[0]),
        "endPrice": float(series.iloc[-1]),
        "totalReturn": float(growth - 1),
        "cagr": float(growth ** (1 / years) - 1) if years > 0 else None,
        "annualisedVol": float(daily.std() * math.sqrt(_TRADING_DAYS)),
        "maxDrawdown": float(drawdown) if not math.isnan(drawdown) else None,
    }


def history(symbols: list[str], period_label: str) -> dict:
    """Aligned close prices plus per-symbol risk stats, ready for the browser.

    Args:
        symbols: Tickers to compare.
        period_label: A key of `PERIODS` — "1Y", "5Y", "10Y" or "All time".

    Returns:
        `{dates, series[], start, limiting, missing[]}`. Prices are aligned, so the
        client can rebase, index or plot them raw without refetching.
    """
    period = PERIODS.get(period_label, "5y")
    wanted = tuple(dict.fromkeys(symbols))
    if not wanted:
        return {"dates": [], "series": [], "start": None, "limiting": None, "missing": []}

    frame = _cached(("hist", wanted, period), lambda: _closes(wanted, period))
    missing = [s for s in wanted if s not in frame.columns]
    aligned, start, limiting = _align(frame)
    if aligned.empty:
        return {"dates": [], "series": [], "start": None, "limiting": None, "missing": missing}

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
        "dates": [d.strftime("%Y-%m-%d") for d in aligned.index],
        "series": series,
        "start": start.strftime("%Y-%m-%d") if start is not None else None,
        "limiting": limiting,
        "missing": missing,
    }
