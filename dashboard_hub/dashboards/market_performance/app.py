from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dashboard_hub.lib import queries, ui  # noqa: E402

entry = ui.boot("market-performance")
ui.require_warehouse()

prices = queries.market_prices()

if prices.empty:
    ui.empty_state(
        "No price data yet",
        "`marts.fact_market_prices` is empty, so USD total return, volatility and drawdown "
        "cannot be computed. This is a **blocked source, not a pipeline failure** — stooq.com "
        "moved its CSV endpoint behind a JavaScript bot check, so Alpha Vantage is now the "
        "price backend and it needs a free key.",
        "add `ALPHA_VANTAGE_API_KEY` to `.env`, then re-run `make pipeline`. The models, tests "
        "and this dashboard are already built against it.",
    )
    st.markdown(
        "**What appears here once prices land:** cumulative USD total return per holding, "
        "annualised volatility and max drawdown, and performance relative to the SPY / ACWI "
        "benchmarks already configured in `companies.yml`."
    )
else:
    tickers = sorted(prices["ticker"].unique())
    picked = st.multiselect("Companies", tickers, default=tickers[:4])
    view = prices[prices["ticker"].isin(picked)].copy()

    if view.empty:
        st.warning("No rows for that selection.")
    else:
        view["cumulative_return"] = view.groupby("ticker")["daily_return"].transform(
            lambda s: (1 + s.fillna(0)).cumprod() - 1
        )
        scale = ui.scale_for(tickers, picked)

        st.altair_chart(
            alt.Chart(view)
            .mark_line(strokeWidth=2)
            .encode(
                x=alt.X("trade_date:T", title=None),
                y=alt.Y(
                    "cumulative_return:Q",
                    title="Cumulative USD return",
                    axis=alt.Axis(format=".0%"),
                ),
                color=alt.Color("ticker:N", scale=scale, title=None),
                tooltip=["ticker", "trade_date", alt.Tooltip("cumulative_return:Q", format=".1%")],
            )
            .properties(height=340),
            use_container_width=True,
        )

        stats = (
            view.groupby("ticker")["daily_return"]
            .agg(
                annualised_vol=lambda s: s.std() * (252**0.5),
                worst_day="min",
                best_day="max",
            )
            .reset_index()
        )
        st.markdown("##### Risk profile")
        st.dataframe(stats, use_container_width=True, hide_index=True)
        ui.table_view(view)

ui.footer(entry)
