from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboards.streamlit_app import queries, theme  # noqa: E402
from dashboards.streamlit_app.db import (  # noqa: E402
    table_counts,
    warehouse_exists,
    warehouse_target,
)

st.set_page_config(page_title="Kubera_EDW", page_icon="📊", layout="wide")
alt.themes.register("kubera", theme.chart_theme)
alt.themes.enable("kubera")

MONEY_FMT = "$,.0f"


def table_view(df: pd.DataFrame, label: str = "View data") -> None:
    with st.expander(label):
        st.dataframe(df, use_container_width=True, hide_index=True)


def empty_state(title: str, reason: str, fix: str) -> None:
    st.info(f"**{title}**\n\n{reason}\n\n**To enable:** {fix}")


def bar_with_labels(df, x, y, color_field, title, x_title="", fmt=".0f"):
    base = alt.Chart(df).encode(
        y=alt.Y(f"{y}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=180)),
        x=alt.X(f"{x}:Q", title=x_title, axis=alt.Axis(grid=True)),
    )
    bars = base.mark_bar(cornerRadiusEnd=4).encode(
        color=alt.Color(f"{color_field}:N", scale=alt.Scale(range=theme.SERIES), legend=None),
        tooltip=list(df.columns),
    )
    labels = base.mark_text(align="left", dx=6, color=theme.TEXT_SECONDARY, fontSize=11).encode(
        text=alt.Text(f"{x}:Q", format=fmt)
    )
    return (bars + labels).properties(title=title, height=alt.Step(30))


st.title("Kubera Global Asset Management")
st.caption(
    "Enterprise data warehouse & BI. Fictional firm; real public data — "
    "no investment advice or ownership claim implied."
)

if not warehouse_exists():
    st.error("No warehouse found. Build it first:\n\n```bash\nbash scripts/pipeline.sh\n```")
    st.stop()

counts = table_counts()

with st.sidebar:
    st.subheader("Warehouse")
    st.caption(f"Target: `{warehouse_target()}`")
    for name, n in counts.items():
        st.markdown(f"{'🟢' if n else '⚪️'} `{name}` — {n:,}")
    st.divider()
    if any(n == 0 for n in counts.values()):
        st.caption(
            "Empty marts are sources still blocked on a free API key, not pipeline failures — "
            "the affected tab explains which key and why."
        )
    else:
        st.caption("All marts populated.")

tabs = st.tabs(
    [
        "Portfolio Allocation",
        "Fundamentals",
        "Market Performance",
        "FX Impact",
        "Macro Overlay",
    ]
)

with tabs[0]:
    st.subheader("Portfolio allocation")
    st.caption(
        "Diversification across country, sector and currency. **Equal-weighted**: Kubera's "
        "positions are simulated (§13) and the warehouse holds no share counts, so there are "
        "no real weights to compute — the assumption is stated rather than invented."
    )

    holdings = queries.holdings()
    c1, c2, c3 = st.columns(3)
    c1.metric("Holdings", len(holdings))
    c2.metric("Countries", holdings["country_iso3"].nunique())
    c3.metric("Reporting currencies", holdings["reporting_currency"].nunique())

    dimension = st.radio(
        "Break down by", ["Country", "Sector", "Currency", "Region"], horizontal=True
    )
    alloc = queries.allocation(dimension)
    st.altair_chart(
        bar_with_labels(
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
    table_view(alloc)

    st.markdown("##### Holdings")
    st.dataframe(holdings, use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Holding fundamentals")
    st.caption(
        "Revenue growth, profitability and leverage — all USD-normalized so companies "
        "reporting in JPY and CNY are comparable with the rest."
    )

    fund = queries.fundamentals("FY")
    if fund.empty:
        empty_state(
            "No financial facts", "fact_financials is empty.", "run `bash scripts/pipeline.sh`"
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
        view["revenue_usd_bn"] = view["revenue_usd"] / 1e9
        view["net_income_usd_bn"] = view["net_income_usd"] / 1e9

        if view.empty:
            st.warning("No rows for that selection.")
        else:
            palette = theme.colors_for(tickers)
            shown = {t: palette[t] for t in picked}
            scale = alt.Scale(domain=list(shown), range=list(shown.values()))

            def line(field, title, fmt):
                pts = view.dropna(subset=[field])
                if pts.empty:
                    return None
                return (
                    alt.Chart(pts)
                    .mark_line(point=alt.OverlayMarkDef(size=45), strokeWidth=2)
                    .encode(
                        x=alt.X("fiscal_year:O", title="Fiscal year"),
                        y=alt.Y(f"{field}:Q", title=title, axis=alt.Axis(format=fmt)),
                        color=alt.Color("ticker:N", scale=scale, title="Company"),
                        tooltip=[
                            "ticker",
                            "fiscal_year",
                            alt.Tooltip(f"{field}:Q", format=fmt, title=title),
                        ],
                    )
                    .properties(title=title, height=280)
                )

            left, right = st.columns(2)
            for col, (field, title, fmt) in zip(
                [left, right, left, right],
                [
                    ("revenue_usd_bn", "Revenue (USD bn)", "$,.0f"),
                    ("revenue_growth_yoy", "Revenue growth YoY", ".0%"),
                    ("ebitda_margin", "EBITDA margin", ".0%"),
                    ("net_debt_to_ebitda", "Net debt / EBITDA", ".1f"),
                ],
                strict=False,
            ):
                chart = line(field, title, fmt)
                with col:
                    if chart is None:
                        st.caption(f"_{title}: not reported by the selected companies._")
                    else:
                        st.altair_chart(chart, use_container_width=True)

            table_view(view)

with tabs[2]:
    st.subheader("Market performance")
    prices = queries.market_prices()
    if prices.empty:
        empty_state(
            "No price data yet",
            "`fact_market_prices` is empty, so USD total return, volatility, drawdown and "
            "benchmark-relative performance cannot be computed. This is a **blocked source, "
            "not a pipeline failure** — stooq.com moved its CSV endpoint behind a JavaScript "
            "bot check, so Alpha Vantage is now the price backend and it needs a free key.",
            "add `ALPHA_VANTAGE_API_KEY` to `.env`, then re-run `bash scripts/pipeline.sh`. "
            "The models, tests and this dashboard are already built against it.",
        )
        st.markdown(
            "**What appears here once prices land:** cumulative USD total return per holding, "
            "annualised volatility and max drawdown, and performance relative to the SPY / ACWI "
            "benchmarks already configured in `companies.yml`."
        )
    else:
        tickers = sorted(prices["ticker"].unique())
        picked = st.multiselect("Companies", tickers, default=tickers[:4], key="mkt")
        view = prices[prices["ticker"].isin(picked)].copy()
        palette = theme.colors_for(tickers)
        shown = {t: palette[t] for t in picked}
        view["cumulative_return"] = view.groupby("ticker")["daily_return"].transform(
            lambda s: (1 + s.fillna(0)).cumprod() - 1
        )
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
                color=alt.Color(
                    "ticker:N",
                    scale=alt.Scale(domain=list(shown), range=list(shown.values())),
                    title="Company",
                ),
                tooltip=["ticker", "trade_date", alt.Tooltip("cumulative_return:Q", format=".1%")],
            )
            .properties(height=340),
            use_container_width=True,
        )
        table_view(view)

with tabs[3]:
    st.subheader("FX impact on reported financials")
    st.caption(
        "How much of a holding's USD figures is the business and how much is the exchange rate. "
        "Only **Toyota (JPY)** and **Alibaba (CNY)** actually convert — AZN, SHEL and INFY are "
        "foreign issuers that file with the SEC in USD, so conversion is a deliberate no-op."
    )

    fx = queries.fx_impact()
    if fx.empty:
        empty_state(
            "No convertible financials",
            "No non-USD reporters in fact_financials.",
            "run the pipeline",
        )
    else:
        rates = queries.fx_rate_history()
        fx_bn = fx.copy()
        fx_bn["revenue_usd_bn"] = fx_bn["revenue_usd"] / 1e9
        palette = theme.colors_for(sorted(fx["ticker"].unique()))
        scale = alt.Scale(domain=list(palette), range=list(palette.values()))

        left, right = st.columns(2)
        with left:
            st.altair_chart(
                alt.Chart(fx_bn.dropna(subset=["revenue_usd_bn"]))
                .mark_line(point=alt.OverlayMarkDef(size=45), strokeWidth=2)
                .encode(
                    x=alt.X("fiscal_year:O", title="Fiscal year"),
                    y=alt.Y(
                        "revenue_usd_bn:Q", title="Revenue (USD bn)", axis=alt.Axis(format="$,.0f")
                    ),
                    color=alt.Color("ticker:N", scale=scale, title="Company"),
                    tooltip=[
                        "ticker",
                        "fiscal_year",
                        alt.Tooltip("revenue_usd_bn:Q", format="$,.1f", title="Revenue (USD bn)"),
                    ],
                )
                .properties(title="USD-normalized revenue", height=300),
                use_container_width=True,
            )
        with right:
            st.altair_chart(
                alt.Chart(rates)
                .mark_line(point=alt.OverlayMarkDef(size=45), strokeWidth=2)
                .encode(
                    x=alt.X("fiscal_year:O", title="Fiscal year"),
                    y=alt.Y("rate_per_usd:Q", title="Units per 1 USD"),
                    color=alt.Color("ticker:N", scale=scale, title="Company"),
                    tooltip=["ticker", "fiscal_year", alt.Tooltip("rate_per_usd:Q", format=".2f")],
                )
                .properties(title="Applied year-end FX rate", height=300)
                .facet(row=alt.Row("reporting_currency:N", title=None))
                .resolve_scale(y="independent"),
                use_container_width=True,
            )

        st.caption(
            "A rising line on the right means the currency weakened against the dollar — the "
            "same local-currency revenue converts to fewer dollars."
        )
        table_view(fx)

with tabs[4]:
    st.subheader("Macro overlay")
    st.caption(
        "The economic backdrop in every country the portfolio holds a position in, plus an "
        "independent IMF cross-check on the World Bank figures."
    )

    macro = queries.macro()
    if macro.empty:
        empty_state(
            "No macro data", "fact_macro_indicators is empty.", "run `bash scripts/pipeline.sh`"
        )
    else:
        countries = sorted(macro["country_iso3"].unique())
        picked = st.multiselect("Countries", countries, default=countries, key="macro")
        view = macro[macro["country_iso3"].isin(picked)]
        palette = theme.colors_for(countries)
        shown = {c: palette[c] for c in picked}
        scale = alt.Scale(domain=list(shown), range=list(shown.values()))

        def macro_line(field, title, fmt):
            pts = view.dropna(subset=[field])
            if pts.empty:
                return None
            return (
                alt.Chart(pts)
                .mark_line(point=alt.OverlayMarkDef(size=40), strokeWidth=2)
                .encode(
                    x=alt.X("calendar_year:O", title=None),
                    y=alt.Y(f"{field}:Q", title=title, axis=alt.Axis(format=fmt)),
                    color=alt.Color("country_iso3:N", scale=scale, title="Country"),
                    tooltip=[
                        "country_iso3",
                        "calendar_year",
                        alt.Tooltip(f"{field}:Q", format=fmt),
                    ],
                )
                .properties(title=title, height=280)
            )

        left, right = st.columns(2)
        for col, (field, title, fmt) in zip(
            [left, right, left, right],
            [
                ("gdp_growth_pct", "GDP growth (%)", ".1f"),
                ("cpi_inflation_pct", "CPI inflation (%)", ".1f"),
                ("unemployment_pct", "Unemployment (%)", ".1f"),
                ("gdp_growth_source_diff", "IMF minus World Bank growth (pp)", ".2f"),
            ],
            strict=False,
        ):
            chart = macro_line(field, title, fmt)
            with col:
                if chart is None:
                    st.caption(f"_{title}: no data for this selection._")
                else:
                    st.altair_chart(chart, use_container_width=True)

        st.caption(
            "The fourth panel is a data-quality check, not an economic indicator: World Bank "
            "and IMF publish independently, so a large divergence flags a figure worth verifying."
        )
        table_view(view)

        gold = queries.gold_prices()
        st.markdown("##### Gold benchmark")
        if gold.empty:
            empty_state(
                "No gold series yet",
                "`fact_gold_price` is empty, so the safe-haven overlay against portfolio "
                "returns and inflation cannot be drawn.",
                "add `FRED_API_KEY` to `.env` and re-run the pipeline.",
            )
        else:
            st.altair_chart(
                alt.Chart(gold)
                .mark_line(strokeWidth=2, color=theme.SERIES[3])
                .encode(
                    x=alt.X("price_date:T", title=None),
                    y=alt.Y("gold_price_usd:Q", title="Gold proxy (USD/share)"),
                    tooltip=["price_date", "gold_price_usd", "series_id"],
                )
                .properties(height=260),
                use_container_width=True,
            )
            table_view(gold)
