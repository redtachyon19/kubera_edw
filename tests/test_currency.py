"""Cross-currency listings: conversion, and the ratios built across it.

An ADR trades in one currency and files in another. Yahoo publishes some of its
ratios straight across the two without converting, which inflates them by
exactly the exchange rate — Ferrari's NYSE line reports a price/sales of 9.59
where its Milan line reports 8.29, and EUR/USD is 1.15.

The property that matters is that a ratio is dimensionless once its two halves
share a unit, so the multiples must not move when the display currency does.
Levels must.
"""

from __future__ import annotations

import pytest

from dashboard_hub.lib import market_data as m


@pytest.fixture
def rates(monkeypatch):
    """Fix the FX table so the arithmetic is checkable by hand."""
    table = {
        ("EUR", "USD"): 1.15,
        ("USD", "EUR"): 1 / 1.15,
        ("EUR", "JPY"): 180.0,
        ("USD", "JPY"): 180.0 / 1.15,
    }

    def fx(source, target):
        if source == target:
            return 1.0
        return table.get((source, target))

    monkeypatch.setattr(m, "fx_rate", fx)
    return table


def _info(**overrides):
    """A Ferrari-shaped listing: trades USD, files EUR."""
    base = {
        "currency": "USD",
        "financialCurrency": "EUR",
        "currentPrice": 401.28,
        "regularMarketPreviousClose": 400.0,
        "marketCap": 70_535_716_864,
        "enterpriseValue": 71_028_613_120,
        "bookValue": 23.988186,
        "totalRevenue": 7_353_308_160,
        "ebitda": 2_469_690_112,
        "trailingEps": 10.63,
        "trailingPE": 37.749763,
        "priceToBook": 16.728235,
        "priceToSalesTrailing12Months": 9.592379,
        "enterpriseToEbitda": 28.76,
        "longName": "Ferrari N.V.",
        "fiftyTwoWeekHigh": 500.0,
        "fiftyTwoWeekLow": 300.0,
    }
    return {**base, **overrides}


@pytest.fixture
def ferrari(monkeypatch, rates):
    monkeypatch.setattr(m, "_info", lambda symbol: _info())
    monkeypatch.setattr(m, "_statements", lambda symbol: {"annual": [], "quarterly": []})
    monkeypatch.setattr(m, "_filed", lambda symbol: {"held": False, "meta": None, "years": []})
    monkeypatch.setattr(m, "_peers", lambda symbol: ([], []))
    monkeypatch.setattr(m, "_by_symbol", dict)


# ── Ratios are unit-invariant ────────────────────────────────────────────────


def test_multiples_do_not_move_with_the_display_currency(ferrari):
    shapes = [m.company("RACE", ccy)["kpis"] for ccy in (None, "USD", "EUR", "JPY")]
    for field in ("priceToBook", "priceToSales", "evToEbitda", "trailingPe"):
        values = {round(k[field], 6) for k in shapes}
        assert len(values) == 1, f"{field} changed with the display currency: {values}"


def test_price_to_sales_matches_the_home_listing(ferrari):
    """Milan reports 8.29 for the same company; Yahoo's US figure says 9.59."""
    kpis = m.company("RACE", "USD")["kpis"]
    # 70.536bn USD over (7.353bn EUR x 1.15).
    assert kpis["priceToSales"] == pytest.approx(8.34, abs=0.05)
    assert kpis["priceToSales"] != pytest.approx(9.592379, abs=0.01)


def test_price_to_book_converts_the_book_value(ferrari):
    kpis = m.company("RACE", "USD")["kpis"]
    # 401.28 USD over (23.988 EUR x 1.15).
    assert kpis["priceToBook"] == pytest.approx(401.28 / (23.988186 * 1.15), rel=1e-6)


def test_enterprise_value_is_rebuilt_not_converted(ferrari):
    """Yahoo's EV is itself mixed — cap in one currency, net debt in another."""
    kpis = m.company("RACE", "USD")["kpis"]
    net_debt_eur = 71_028_613_120 - 70_535_716_864
    assert kpis["enterpriseValue"] == pytest.approx(70_535_716_864 + net_debt_eur * 1.15, rel=1e-6)


# ── Levels do move ───────────────────────────────────────────────────────────


def test_levels_convert(ferrari):
    usd = m.company("RACE", "USD")["kpis"]
    eur = m.company("RACE", "EUR")["kpis"]

    assert eur["marketCap"] == pytest.approx(usd["marketCap"] / 1.15, rel=1e-6)
    assert eur["price"] == pytest.approx(401.28 / 1.15, rel=1e-6)
    assert eur["high52"] == pytest.approx(500.0 / 1.15, rel=1e-6)


def test_the_default_is_the_trading_currency(ferrari):
    payload = m.company("RACE")
    assert payload["money"]["displayCurrency"] == "USD"
    assert payload["kpis"]["price"] == pytest.approx(401.28)


def test_the_listings_own_currencies_are_always_offered(ferrari):
    options = m.company("RACE")["money"]["options"]
    assert "USD" in options and "EUR" in options


# ── Same-currency listings are left alone ────────────────────────────────────


def test_a_single_currency_listing_keeps_yahoos_own_ratios(monkeypatch, rates):
    """Apple files and trades in USD; there is nothing to correct."""
    monkeypatch.setattr(m, "_info", lambda symbol: _info(currency="USD", financialCurrency="USD"))
    monkeypatch.setattr(m, "_statements", lambda symbol: {"annual": [], "quarterly": []})
    monkeypatch.setattr(m, "_filed", lambda symbol: {"held": False, "meta": None, "years": []})
    monkeypatch.setattr(m, "_peers", lambda symbol: ([], []))
    monkeypatch.setattr(m, "_by_symbol", dict)

    payload = m.company("AAPL")
    assert payload["kpis"]["mixedCurrency"] is False
    assert payload["kpis"]["priceToBook"] == pytest.approx(16.728235)
    assert payload["money"]["converted"] is False


# ── Statements ───────────────────────────────────────────────────────────────


def test_restate_scales_money_and_leaves_ratios_alone():
    period = {
        "end": "2025-12-31",
        "label": "FY2025",
        "revenue": 100.0,
        "netIncome": 20.0,
        "netMargin": 0.2,
        "currentRatio": 1.4,
        "debtToEquity": 0.5,
    }
    out = m._restate({"annual": [period], "quarterly": []}, 2.0)["annual"][0]

    assert out["revenue"] == 200.0
    assert out["netIncome"] == 40.0
    # Dimensionless — doubling the unit must not double the margin.
    assert out["netMargin"] == 0.2
    assert out["currentRatio"] == 1.4
    assert out["debtToEquity"] == 0.5
    assert out["label"] == "FY2025"


def test_restate_is_a_no_op_at_parity():
    statements = {"annual": [{"revenue": 100.0}], "quarterly": []}
    assert m._restate(statements, 1.0) is statements
    assert m._restate(statements, None) is statements


# ── Missing rates ────────────────────────────────────────────────────────────


def test_an_unavailable_pair_blanks_the_figure_rather_than_faking_it(monkeypatch):
    monkeypatch.setattr(m, "fx_rate", lambda a, b: 1.0 if a == b else None)
    monkeypatch.setattr(m, "_info", lambda symbol: _info())
    monkeypatch.setattr(m, "_statements", lambda symbol: {"annual": [], "quarterly": []})
    monkeypatch.setattr(m, "_filed", lambda symbol: {"held": False, "meta": None, "years": []})
    monkeypatch.setattr(m, "_peers", lambda symbol: ([], []))
    monkeypatch.setattr(m, "_by_symbol", dict)

    payload = m.company("RACE", "GBP")
    assert payload["money"]["incomplete"] is True
    assert payload["kpis"]["marketCap"] is None
    assert payload["kpis"]["priceToSales"] is None


def test_fx_rate_is_one_for_a_currency_against_itself():
    assert m.fx_rate("USD", "USD") == 1.0
    assert m.fx_rate("", "USD") is None
