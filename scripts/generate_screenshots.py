"""Render the dashboard's charts to committed PNGs for the README.

Generated from the live warehouse rather than captured by hand: a script re-renders on demand
and cannot silently drift from the data it claims to show, which a manually-cropped screenshot
does the moment the model changes.

Usage:
    python scripts/generate_screenshots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import vl_convert as vlc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboards.streamlit_app import queries, theme  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
SCALE = 2  # retina


def save(chart: alt.Chart, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    png = vlc.vegalite_to_png(chart.to_json(), scale=SCALE)
    path = OUT / f"{name}.png"
    path.write_bytes(png)
    print(f"  {path.relative_to(OUT.parent.parent)}  ({len(png) / 1024:.0f} KB)")


def allocation_chart() -> alt.Chart:
    df = queries.allocation("Sector")
    base = alt.Chart(df).encode(
        y=alt.Y("category:N", sort="-x", title=None),
        x=alt.X("weight_pct:Q", title="% of portfolio"),
    )
    bars = base.mark_bar(cornerRadiusEnd=4).encode(
        color=alt.Color("category:N", scale=alt.Scale(range=theme.SERIES), legend=None)
    )
    labels = base.mark_text(align="left", dx=6, color=theme.TEXT_SECONDARY, fontSize=11).encode(
        text=alt.Text("weight_pct:Q", format=".1f")
    )
    return (bars + labels).properties(
        title="Portfolio allocation by sector (equal-weighted)", width=520, height=alt.Step(28)
    )


def fundamentals_chart() -> alt.Chart:
    df = queries.fundamentals("FY")
    df = df[df["fiscal_year"].between(2018, 2025)].copy()
    df["revenue_usd_bn"] = df["revenue_usd"] / 1e9
    top = (
        df.groupby("ticker")["revenue_usd_bn"]
        .max()
        .sort_values(ascending=False)
        .head(MAX_SERIES)
        .index
    )
    df = df[df["ticker"].isin(top)].dropna(subset=["revenue_usd_bn"])
    palette = theme.colors_for(sorted(top))
    return (
        alt.Chart(df)
        .mark_line(point=alt.OverlayMarkDef(size=40), strokeWidth=2)
        .encode(
            x=alt.X("fiscal_year:O", title="Fiscal year"),
            y=alt.Y("revenue_usd_bn:Q", title="Revenue (USD bn)", axis=alt.Axis(format="$,.0f")),
            color=alt.Color(
                "ticker:N",
                scale=alt.Scale(domain=list(palette), range=list(palette.values())),
                title="Company",
            ),
        )
        .properties(title="Revenue, USD-normalized — largest holdings", width=560, height=320)
    )


#: Hard cap on series in one chart. The palette has 8 slots assigned in fixed order; past that
#: hues would CYCLE and two companies would share a colour, making identity ambiguous. 18
#: companies now report in a non-USD currency, so this chart shows the largest and says so in
#: the subtitle rather than drawing a rainbow.
MAX_SERIES = 6


def fx_chart() -> alt.Chart:
    df = queries.fx_impact()
    df = df[df["fiscal_year"].between(2018, 2025)].copy()
    df["revenue_usd_bn"] = df["revenue_usd"] / 1e9
    df = df.dropna(subset=["revenue_usd_bn"])
    total = df["ticker"].nunique()
    largest = (
        df.groupby("ticker")["revenue_usd_bn"]
        .max()
        .sort_values(ascending=False)
        .head(MAX_SERIES)
        .index
    )
    df = df[df["ticker"].isin(largest)]
    palette = theme.colors_for(sorted(largest))
    return (
        alt.Chart(df)
        .mark_line(point=alt.OverlayMarkDef(size=35), strokeWidth=2)
        .encode(
            x=alt.X("fiscal_year:O", title="Fiscal year"),
            y=alt.Y("revenue_usd_bn:Q", title="Revenue (USD bn)", axis=alt.Axis(format="$,.0f")),
            color=alt.Color(
                "ticker:N",
                scale=alt.Scale(domain=list(palette), range=list(palette.values())),
                title="Company",
            ),
        )
        .properties(
            title=alt.TitleParams(
                "Companies reporting in a non-USD currency, converted to USD",
                subtitle=f"Largest {MAX_SERIES} of {total} non-USD reporters",
                subtitleColor=theme.TEXT_MUTED,
            ),
            width=560,
            height=320,
        )
    )


def macro_chart() -> alt.Chart:
    df = queries.macro()
    df = df[df["calendar_year"].between(2015, 2024)].dropna(subset=["gdp_growth_pct"])
    keep = ["USA", "CHN", "IND", "JPN", "GBR", "DEU"]  # 6 <= MAX_SERIES
    df = df[df["country_iso3"].isin(keep)]
    palette = theme.colors_for(sorted(keep))
    return (
        alt.Chart(df)
        .mark_line(point=alt.OverlayMarkDef(size=35), strokeWidth=2)
        .encode(
            x=alt.X("calendar_year:O", title=None),
            y=alt.Y("gdp_growth_pct:Q", title="GDP growth (%)"),
            color=alt.Color(
                "country_iso3:N",
                scale=alt.Scale(domain=list(palette), range=list(palette.values())),
                title="Country",
            ),
        )
        .properties(title="Macro backdrop — GDP growth by holding country", width=560, height=300)
    )


def market_chart() -> alt.Chart | None:
    df = queries.market_prices()
    if df.empty:
        return None
    top = sorted(df["ticker"].unique())[:MAX_SERIES]
    df = df[df["ticker"].isin(top)].copy()
    df["cumulative_return"] = df.groupby("ticker")["daily_return"].transform(
        lambda s: (1 + s.fillna(0)).cumprod() - 1
    )
    palette = theme.colors_for(top)
    return (
        alt.Chart(df)
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
                scale=alt.Scale(domain=list(palette), range=list(palette.values())),
                title="Company",
            ),
        )
        .properties(title="Cumulative USD total return", width=560, height=300)
    )


def main() -> None:
    alt.themes.register("kubera", theme.chart_theme)
    alt.themes.enable("kubera")
    print("Rendering charts from the live warehouse...")
    save(allocation_chart(), "01_portfolio_allocation")
    save(fundamentals_chart(), "02_fundamentals")
    save(fx_chart(), "03_fx_impact")
    save(macro_chart(), "04_macro_overlay")
    market = market_chart()
    if market is not None:
        save(market, "05_market_performance")
    else:
        print("  (market performance skipped — no price data)")


if __name__ == "__main__":
    main()
