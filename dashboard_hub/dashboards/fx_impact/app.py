from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dashboard_hub.lib import queries, theme, ui  # noqa: E402

entry = ui.boot("fx-impact")
ui.require_warehouse()

st.caption(
    "Only **Toyota (JPY)** and **Alibaba (CNY)** actually convert — AZN, SHEL and INFY are "
    "foreign issuers that file with the SEC in USD, so conversion is a deliberate no-op."
)

fx = queries.fx_impact()

if fx.empty:
    ui.empty_state(
        "No convertible financials",
        "No non-USD reporters in `marts.fact_financials`.",
        "run `make demo` (offline) or `make pipeline` (live).",
    )
else:
    rates = queries.fx_rate_history()
    fx_bn = fx.copy()
    fx_bn["revenue_usd_bn"] = fx_bn["revenue_usd"] / 1e9

    tickers = sorted(fx["ticker"].unique())
    scale = ui.scale_for(tickers, tickers)

    left, right = st.columns(2)
    with left:
        chart = ui.line_by(
            fx_bn,
            "fiscal_year:O",
            "revenue_usd_bn",
            "ticker",
            scale,
            "USD-normalized revenue (bn)",
            "$,.1f",
            "Fiscal year",
            height=300,
        )
        if chart is None:
            st.caption("_No convertible revenue reported._")
        else:
            st.altair_chart(chart, use_container_width=True)

    with right:
        st.altair_chart(
            alt.Chart(rates)
            .mark_line(point=alt.OverlayMarkDef(size=45), strokeWidth=2)
            .encode(
                x=alt.X("fiscal_year:O", title="Fiscal year"),
                y=alt.Y("rate_per_usd:Q", title="Units per 1 USD"),
                color=alt.Color("ticker:N", scale=scale, title=None),
                tooltip=["ticker", "fiscal_year", alt.Tooltip("rate_per_usd:Q", format=".2f")],
            )
            .properties(title="Applied year-end FX rate", height=300)
            .facet(row=alt.Row("reporting_currency:N", title=None))
            .resolve_scale(y="independent"),
            use_container_width=True,
        )

    st.caption(
        "A rising line on the right means the currency weakened against the dollar — the same "
        "local-currency revenue converts to fewer dollars."
    )
    st.markdown(
        f'<span style="color:{theme.TEXT_MUTED};font-size:.85rem">'
        f"{fx['ticker'].nunique()} non-USD reporter(s) across "
        f"{fx['reporting_currency'].nunique()} currency(ies).</span>",
        unsafe_allow_html=True,
    )
    ui.table_view(fx)

ui.footer(entry)
