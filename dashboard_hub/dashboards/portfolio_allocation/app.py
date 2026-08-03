from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dashboard_hub.lib import queries, ui  # noqa: E402

entry = ui.boot("allocation")
ui.require_warehouse()

st.caption(
    "**Equal-weighted**: Kubera's positions are simulated and the warehouse holds no share "
    "counts, so there are no real weights to compute — the assumption is stated rather than "
    "invented."
)

holdings = queries.holdings()
c1, c2, c3 = st.columns(3)
c1.metric("Holdings", len(holdings))
c2.metric("Countries", holdings["country_iso3"].nunique())
c3.metric("Reporting currencies", holdings["reporting_currency"].nunique())

dimension = st.radio("Break down by", ["Country", "Sector", "Currency", "Region"], horizontal=True)
alloc = queries.allocation(dimension)

st.altair_chart(
    ui.bar_with_labels(
        alloc,
        "weight_pct",
        "category",
        "category",
        f"Allocation by {dimension.lower()} (% of portfolio)",
        "% of portfolio",
        ".1f",
    ),
    use_container_width=True,
)
ui.table_view(alloc)

st.markdown("##### Holdings")
st.dataframe(holdings, use_container_width=True, hide_index=True)

ui.footer(entry)
