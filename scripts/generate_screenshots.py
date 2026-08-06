from __future__ import annotations

import json
import sys
from pathlib import Path

import altair as alt
import vl_convert as vlc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard_hub.lib import queries, theme  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
SCALE = 2


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
    keep = ["USA", "CHN", "IND", "JPN", "GBR", "DEU"]
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


# ── Card thumbnails ──────────────────────────────────────────────────────────
# The Dashboards desk draws each embedded report as a card, and a card with a
# numbered grey plate on it tells the reader nothing about what is inside.
#
# These are rendered from the chart rather than screenshotted from the running
# page, which is the better answer for something displayed at 300px: a shrunk
# capture of a Streamlit app is mostly chrome, sidebar and unreadable axis text,
# where the chart is the thing the dashboard is actually for. It also needs no
# browser, no running dashboards and no 150 MB of Chromium — it reads the
# warehouse and writes a PNG.
#
# Keyed by dashboard id so the file the hub asks for and the file this writes
# cannot drift apart. A dashboard with no entry here simply has no thumbnail and
# the card falls back to its plate.
THUMBNAILS = {
    "allocation": allocation_chart,
    "fundamentals": fundamentals_chart,
    "fx-impact": fx_chart,
    "macro-overlay": macro_chart,
}

# The card plate is 16:10, so the render matches it and nothing is cropped.
THUMB_WIDTH = 640
THUMB_HEIGHT = 400

HUB_THUMBS = (
    Path(__file__).resolve().parent.parent / "dashboard_hub" / "hub" / "public" / "thumbnails"
)


def save_thumbnail(chart: alt.Chart, dashboard_id: str) -> None:
    """Render one chart at card proportions, titleless, into the hub's assets.

    The title is dropped because the card already prints it directly underneath —
    printing it twice in two typefaces looks like a mistake.
    """
    sized = chart.properties(title="", width=THUMB_WIDTH, height=THUMB_HEIGHT)
    HUB_THUMBS.mkdir(parents=True, exist_ok=True)
    png = vlc.vegalite_to_png(sized.to_json(), scale=SCALE)
    path = HUB_THUMBS / f"{dashboard_id}.png"
    path.write_bytes(png)
    print(f"  {path.relative_to(path.parents[4])}  ({len(png) / 1024:.0f} KB)")


def _registered_dashboards() -> set[str]:
    """Every dashboard id in the registry, for the coverage warning below."""
    registry = json.loads(
        (Path(__file__).resolve().parent.parent / "dashboard_hub" / "dashboards.json").read_text()
    )
    return {
        entry["id"]
        for section in registry["sections"]
        for entry in section["dashboards"]
        if entry.get("kind") != "native" and entry.get("status") == "stub"
    }


def main() -> None:
    alt.themes.register("kubera", theme.chart_theme)
    alt.themes.enable("kubera")

    print("Rendering charts from the live warehouse...")
    save(allocation_chart(), "01_portfolio_allocation")
    save(fundamentals_chart(), "02_fundamentals")
    save(fx_chart(), "03_fx_impact")
    save(macro_chart(), "04_macro_overlay")

    print("\nRendering card thumbnails...")
    for dashboard_id, build in THUMBNAILS.items():
        save_thumbnail(build(), dashboard_id)

    # A dashboard that goes into service without a thumbnail is easy to miss —
    # its card silently keeps the plate — so say so rather than leaving it.
    missing = _registered_dashboards() - set(THUMBNAILS)
    if missing:
        print(f"\n  ! in service with no thumbnail: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
