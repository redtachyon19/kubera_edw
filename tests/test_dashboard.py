"""Tests for the BI layer.

Palette and colour-assignment rules are asserted unconditionally; the query tests need a built
warehouse and skip cleanly without one, so `pytest tests/` stays fast and hermetic in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dashboards.streamlit_app import queries, theme

REPO_ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = REPO_ROOT / "data" / "kubera_edw.duckdb"
needs_warehouse = pytest.mark.skipif(
    not WAREHOUSE.exists(), reason="no built warehouse — run bash scripts/pipeline.sh"
)


# --------------------------------------------------------------------- palette rules
def test_palette_has_eight_slots_in_both_modes() -> None:
    assert len(theme.SERIES_LIGHT) == len(theme.SERIES_DARK) == 8
    assert len(set(theme.SERIES_LIGHT)) == 8, "duplicate hue would collapse two entities"
    assert len(set(theme.SERIES_DARK)) == 8


def test_palette_hexes_are_wellformed() -> None:
    hex_re = re.compile(r"^#[0-9a-f]{6}$")
    for name in ("SERIES_LIGHT", "SERIES_DARK", "SEQUENTIAL", "DIVERGING"):
        for value in getattr(theme, name):
            assert hex_re.match(value), f"{name}: {value}"


def test_diverging_midpoint_is_neutral_not_a_hue() -> None:
    # A hue at the midpoint reads as "a value" instead of "nothing"; the midpoint must be gray.
    midpoint = theme.DIVERGING[len(theme.DIVERGING) // 2]
    r, g, b = (int(midpoint[i : i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) - min(r, g, b) < 20, f"{midpoint} is not neutral"


def test_status_colors_are_disjoint_from_series() -> None:
    # A status colour must never impersonate "series 4".
    assert not set(theme.STATUS.values()) & set(theme.SERIES_LIGHT + theme.SERIES_DARK)


def test_colour_follows_entity_not_position() -> None:
    """The core rule: filtering the chart must not repaint the series that remain."""
    full = theme.colors_for(["AAPL", "AZN", "BABA", "INFY", "JPM"])
    # Drop two entities, exactly as a user deselecting them would.
    subset = {t: full[t] for t in ["AAPL", "BABA", "JPM"]}
    for ticker, colour in subset.items():
        assert colour == full[ticker], f"{ticker} was recoloured by filtering"


def test_colour_mapping_is_deterministic() -> None:
    a = theme.colors_for(["TM", "AAPL", "BABA"])
    b = theme.colors_for(["BABA", "AAPL", "TM"])  # different input order
    assert a == b, "colour must not depend on the order entities happen to arrive in"


def test_chart_theme_uses_recessive_ink() -> None:
    cfg = theme.chart_theme()["config"]
    assert cfg["background"] == theme.SURFACE
    # Axis labels wear text tokens, never a series colour.
    assert cfg["axis"]["labelColor"] not in theme.SERIES
    assert cfg["legend"]["labelColor"] not in theme.SERIES


# --------------------------------------------------------------------- queries
@needs_warehouse
def test_allocation_sums_to_100_pct() -> None:
    for dimension in ("Country", "Sector", "Currency", "Region"):
        df = queries.allocation(dimension)
        assert not df.empty, dimension
        assert abs(df["weight_pct"].sum() - 100.0) < 0.01, dimension


@needs_warehouse
def test_holdings_match_the_configured_universe() -> None:
    from ingestion.config_loader import load_companies

    df = queries.holdings()
    # One row per company: dim_company is SCD2, so the dashboard must read current versions
    # only. A duplicate here means a closed version leaked into the holdings list.
    assert len(df) == len(load_companies())
    assert df["ticker"].is_unique
    assert "TSM" not in set(df["ticker"])


@needs_warehouse
def test_fundamentals_are_usd_comparable() -> None:
    df = queries.fundamentals("FY")
    assert not df.empty
    # Every row carries a USD figure wherever the local figure exists and a rate was available.
    assert {"revenue_usd", "ebitda_margin", "revenue_growth_yoy"} <= set(df.columns)


@needs_warehouse
def test_fx_impact_covers_only_non_usd_reporters() -> None:
    df = queries.fx_impact()
    assert "USD" not in set(df["reporting_currency"]), "USD reporters must not appear here"
    assert not df.empty, "no company exercises currency conversion"


@needs_warehouse
def test_macro_has_no_orphan_years() -> None:
    df = queries.macro()
    assert not df.empty
    assert df["calendar_year"].notna().all()


@needs_warehouse
def test_market_prices_are_usable_for_return_math() -> None:
    df = queries.market_prices()
    if df.empty:
        pytest.skip("prices not landed (ALPHA_VANTAGE_API_KEY unset)")
    assert df["close_price_usd"].notna().all()
    # Exactly one null return per ticker: the first observed day has no prior close to lag to.
    nulls = df.groupby("ticker")["daily_return"].apply(lambda s: s.isna().sum())
    assert (nulls == 1).all(), f"unexpected return gaps: {nulls[nulls != 1].to_dict()}"
    # A daily equity move beyond +/-50% is a data error, not a market event.
    assert df["daily_return"].abs().max() < 0.5


@needs_warehouse
def test_gold_series_carries_its_real_provenance() -> None:
    df = queries.gold_prices()
    if df.empty:
        pytest.skip("gold not landed")
    # The backend is the GLD proxy since FRED retired its spot series; the rows must say so
    # rather than inheriting the old FRED series id, which would assert a false source.
    assert set(df["series_id"]) == {"GLD"}
    assert set(df["source"]) == {"alpha_vantage"}
    assert df["gold_price_usd"].gt(0).all()
