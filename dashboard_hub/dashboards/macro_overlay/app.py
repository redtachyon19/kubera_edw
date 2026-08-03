from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dashboard_hub.lib import queries, theme, ui  # noqa: E402

entry = ui.boot("macro-overlay")
ui.require_warehouse()

st.caption("Includes an independent IMF cross-check on the World Bank figures.")

macro = queries.macro()

if macro.empty:
    ui.empty_state(
        "No macro data",
        "`marts.fact_macro_indicators` is empty.",
        "run `make demo` (offline) or `make pipeline` (live).",
    )
else:
    countries = sorted(macro["country_iso3"].unique())
    picked = st.multiselect("Countries", countries, default=countries[:6])
    view = macro[macro["country_iso3"].isin(picked)]

    if view.empty:
        st.warning("No rows for that selection.")
    else:
        scale = ui.scale_for(countries, picked)
        ui.grid(
            [
                (
                    ui.line_by(view, "calendar_year:O", field, "country_iso3", scale, title, fmt),
                    title,
                )
                for field, title, fmt in [
                    ("gdp_growth_pct", "GDP growth (%)", ".1f"),
                    ("cpi_inflation_pct", "CPI inflation (%)", ".1f"),
                    ("unemployment_pct", "Unemployment (%)", ".1f"),
                    ("gdp_growth_source_diff", "IMF minus World Bank growth (pp)", ".2f"),
                ]
            ]
        )
        st.caption(
            "The fourth panel is a data-quality check, not an economic indicator: World Bank "
            "and IMF publish independently, so a large divergence flags a figure worth "
            "verifying."
        )
        ui.table_view(view)

    st.markdown("##### Gold benchmark")
    gold = queries.gold_prices()
    if gold.empty:
        ui.empty_state(
            "No gold series yet",
            "`marts.fact_gold_price` is empty, so the safe-haven overlay against portfolio "
            "returns and inflation cannot be drawn.",
            "add `FRED_API_KEY` to `.env` and re-run `make pipeline`.",
        )
    else:
        st.altair_chart(
            alt.Chart(gold)
            .mark_line(strokeWidth=2, color=theme.SERIES[0])
            .encode(
                x=alt.X("price_date:T", title=None),
                y=alt.Y("gold_price_usd:Q", title="Gold proxy (USD/share)"),
                tooltip=["price_date", "gold_price_usd", "series_id"],
            )
            .properties(height=260),
            use_container_width=True,
        )
        ui.table_view(gold)

ui.footer(entry)
