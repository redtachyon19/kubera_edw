"""Self-contained market data for the Stock Explorer.

This dashboard deliberately does not touch the warehouse. It fetches straight from
Yahoo Finance at request time, so it works on a clean checkout with no pipeline run,
no `.env` and no API key — which is what makes it usable for any listed company
rather than only the 38 in `companies.yml`.

Everything is cached in-process, so flipping between periods or adding a company
re-uses what has already been fetched.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pandas as pd
import streamlit as st
import yfinance as yf

# Yahoo period strings, in the order they should appear as options.
PERIODS: dict[str, str] = {
    "1Y": "1y",
    "5Y": "5y",
    "10Y": "10y",
    "All time": "max",
}

GOLD_SYMBOL = "GC=F"
GOLD_LABEL = "Gold (COMEX front-month)"

_TRADING_DAYS = 252


@st.cache_data(ttl=900, show_spinner=False)
def search(query: str, limit: int = 8) -> list[dict]:
    """Look up listings matching a free-text query.

    Args:
        query: Company name or ticker fragment, e.g. "apple" or "AAPL".
        limit: Maximum results to return.

    Returns:
        One dict per match with `symbol`, `name`, `type` and `exchange`. Empty on a
        blank query or if the lookup fails — a search outage should not take the
        page down.
    """
    query = query.strip()
    if not query:
        return []
    try:
        quotes = yf.Search(query, max_results=limit).quotes
    except Exception:  # noqa: BLE001 — any lookup failure degrades to "no matches"
        return []

    results: list[dict] = []
    for quote in quotes:
        symbol = quote.get("symbol")
        if not symbol:
            continue
        results.append(
            {
                "symbol": symbol,
                "name": quote.get("shortname") or quote.get("longname") or symbol,
                "type": (quote.get("quoteType") or "").title(),
                "exchange": quote.get("exchDisp") or quote.get("exchange") or "",
            }
        )
    return results


@st.cache_data(ttl=900, show_spinner=False)
def closes(symbols: tuple[str, ...], period: str) -> pd.DataFrame:
    """Daily split/dividend-adjusted closing prices.

    Args:
        symbols: Tickers to fetch. A tuple so the result is cacheable.
        period: A Yahoo period string — one of the values in `PERIODS`.

    Returns:
        A date-indexed frame with one column per symbol, columns ordered as passed.
        Symbols that returned nothing are dropped rather than left as all-NaN.
    """
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
    ordered = [s for s in symbols if s in frame.columns]
    return frame[ordered].sort_index()


@st.cache_data(ttl=3600, show_spinner=False)
def currency_of(symbol: str) -> str:
    """The currency a symbol is quoted in, or an empty string if unavailable."""
    try:
        return str(yf.Ticker(symbol).fast_info.get("currency") or "")
    except Exception:  # noqa: BLE001
        return ""


def align(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp | None, str | None]:
    """Put every series on one calendar starting where they all have data.

    Equities, futures and foreign listings keep different trading calendars, so a
    raw join leaves gaps. Gaps are carried forward; the window then starts at the
    latest first-quote across the selection, because rebasing series that begin on
    different dates would overstate whichever one started earliest.

    Args:
        frame: Wide close prices, one column per symbol.

    Returns:
        `(aligned, start, limiting_symbol)` — the clipped frame, the common start
        date, and the symbol that forced that start (None when only one series).
    """
    if frame.empty:
        return frame, None, None

    filled = frame.ffill().dropna(how="all")
    firsts = {col: filled[col].first_valid_index() for col in filled.columns}
    firsts = {col: idx for col, idx in firsts.items() if idx is not None}
    if not firsts:
        return pd.DataFrame(), None, None

    start = max(firsts.values())
    limiting = max(firsts, key=lambda col: firsts[col]) if len(firsts) > 1 else None
    clipped = filled.loc[start:].dropna(how="any")
    return clipped, start, limiting


def rebase(frame: pd.DataFrame) -> pd.DataFrame:
    """Percent change from the first row, so series at different price levels compare."""
    if frame.empty:
        return frame
    return frame.div(frame.iloc[0]).sub(1).mul(100)


def growth_of(frame: pd.DataFrame, base: float = 100.0) -> pd.DataFrame:
    """What `base` invested at the start would be worth — always positive, so it can
    take a log axis. Over ten years or more that matters: one holding up 2,000%
    flattens every other line on a linear scale."""
    if frame.empty:
        return frame
    return frame.div(frame.iloc[0]).mul(base)


# label -> (y-axis title, axis type, transform)
SCALES: dict[str, tuple[str, str, Callable[[pd.DataFrame], pd.DataFrame]]] = {
    "Rebased (%)": ("Change since start (%)", "linear", rebase),
    "Growth of 100 (log)": ("Growth of 100 invested", "log", growth_of),
    "Actual price (log)": ("Close price (listing currency)", "log", lambda frame: frame),
}


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-symbol performance and risk over the window given.

    Args:
        frame: Aligned close prices, one column per symbol.

    Returns:
        A row per symbol: first/last price, total return, CAGR, annualised
        volatility and worst peak-to-trough drawdown.
    """
    rows: list[dict] = []
    for symbol in frame.columns:
        series = frame[symbol].dropna()
        if len(series) < 2:
            continue
        years = (series.index[-1] - series.index[0]).days / 365.25
        growth = series.iloc[-1] / series.iloc[0]
        daily = series.pct_change().dropna()
        rows.append(
            {
                "symbol": symbol,
                "start_price": series.iloc[0],
                "end_price": series.iloc[-1],
                "total_return": growth - 1,
                "cagr": growth ** (1 / years) - 1 if years > 0 else math.nan,
                "annualised_vol": daily.std() * math.sqrt(_TRADING_DAYS),
                "max_drawdown": (series / series.cummax() - 1).min(),
            }
        )
    return pd.DataFrame(rows)
