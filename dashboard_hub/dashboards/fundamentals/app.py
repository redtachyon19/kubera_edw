from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dashboard_hub.lib import queries, ui  # noqa: E402

entry = ui.boot("fundamentals")
ui.require_warehouse()

st.caption("Normalized so companies reporting in JPY and CNY are comparable with the rest.")

fund = queries.fundamentals("FY")

if fund.empty:
    ui.empty_state(
        "No financial facts",
        "`marts.fact_financials` is empty.",
        "run `make demo` (offline) or `make pipeline` (live).",
    )
else:
    tickers = sorted(fund["ticker"].unique())
    picked = st.multiselect("Companies", tickers, default=tickers[:4])
    years = st.slider(
        "Fiscal years",
        int(fund["fiscal_year"].min()),
        int(fund["fiscal_year"].max()),
        (max(int(fund["fiscal_year"].min()), 2015), int(fund["fiscal_year"].max())),
    )

    view = fund[fund["ticker"].isin(picked) & fund["fiscal_year"].between(*years)].copy()
    if view.empty:
        st.warning("No rows for that selection.")
    else:
        view["revenue_usd_bn"] = view["revenue_usd"] / 1e9
        scale = ui.scale_for(tickers, picked)

        ui.grid(
            [
                (
                    ui.line_by(
                        view, "fiscal_year:O", field, "ticker", scale, title, fmt, "Fiscal year"
                    ),
                    title,
                )
                for field, title, fmt in [
                    ("revenue_usd_bn", "Revenue (USD bn)", "$,.0f"),
                    ("revenue_growth_yoy", "Revenue growth YoY", ".0%"),
                    ("ebitda_margin", "EBITDA margin", ".0%"),
                    ("net_debt_to_ebitda", "Net debt / EBITDA", ".1f"),
                ]
            ]
        )
        ui.table_view(view)

ui.footer(entry)
