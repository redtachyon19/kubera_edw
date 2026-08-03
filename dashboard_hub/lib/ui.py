"""Chrome shared by every dashboard the hub embeds.

Each dashboard is its own Streamlit process, so without this they would each
re-implement the masthead, the empty states, the Altair theme and the house
typography. `boot()` is the one call every dashboard makes first.

Streamlit's own base theme is fixed when the process starts, so it is set to the
light stock and the dark stock is applied here as a CSS overlay. Which one to use
comes from the `?theme=` parameter the hub puts on the iframe, so an embedded
dashboard inverts along with the page around it.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from dashboard_hub import registry
from dashboard_hub.lib import theme
from dashboard_hub.lib.db import warehouse_exists, warehouse_target

_CSS = """
<style>
  /* House typography: Copperplate for engraved labels, Optima for reading. */
  .stApp, .stApp p, .stApp li, .stApp label, .stApp span, .stApp div {{
    font-family: {font};
  }}
  .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {{
    font-family: {font_display};
    font-weight: 400;
    text-transform: uppercase;
    letter-spacing: .14em;
  }}
  .stApp h1 {{ font-size: 1.6rem; }}
  .stApp h2 {{ font-size: 1.1rem; }}
  .stApp h3, .stApp h4, .stApp h5 {{ font-size: .9rem; }}

  /* Numerals stay monospaced and tabular so columns line up. */
  [data-testid="stMetricValue"], .stDataFrame, .num {{
    font-family: ui-monospace, 'SF Mono', Menlo, monospace;
    font-variant-numeric: tabular-nums;
  }}
  [data-testid="stMetricLabel"] {{
    font-family: {font_display};
    text-transform: uppercase;
    letter-spacing: .2em;
    font-size: .6rem;
  }}

  .stApp {{ background: {paper}; color: {ink}; }}
  [data-testid="stHeader"] {{ background: transparent; }}

  .k-rule {{ height: 2px; background: {accent}; width: 76px; margin: 0 0 20px; }}
  .k-eyebrow {{
    font-family: {font_display};
    text-transform: uppercase; letter-spacing: .3em; font-size: .58rem;
    color: {muted}; margin-bottom: 10px;
  }}
  .k-note {{
    border: 1px solid {rule}; border-left: 2px solid {accent};
    padding: 20px 24px; color: {secondary}; background: {surface};
  }}
</style>
"""

_DARK_OVERLAY = """
<style>
  /* Streamlit's base theme is fixed at process start, so the dark stock is an
     overlay rather than a theme switch. */
  .stApp, [data-testid="stAppViewContainer"], [data-testid="stBottomBlockContainer"] {{
    background: {paper} !important;
  }}
  .stApp, .stApp p, .stApp li, .stApp label,
  .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6 {{
    color: {ink} !important;
  }}
  [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
    color: {muted} !important;
  }}
  [data-testid="stMetricValue"] {{ color: {ink} !important; }}
  [data-testid="stExpander"], [data-testid="stExpander"] details,
  div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {{
    background: {surface} !important;
  }}
  hr, [data-testid="stExpander"] details {{ border-color: {rule} !important; }}
  code {{ background: {surface} !important; color: {secondary} !important; }}
</style>
"""


def current_mode() -> str:
    """Which stock this page is being read on — set by the hub on the iframe URL."""
    requested = st.query_params.get("theme", theme.DEFAULT_MODE)
    return "dark" if str(requested).lower() == "dark" else "light"


def boot(dashboard_id: str) -> dict:
    """Configure the page for one dashboard and return its registry entry.

    Args:
        dashboard_id: The `id` in `dashboards.json`. Supplies the page title, the
            blurb under it and the desk accent used for every rule and heading.

    Returns:
        The registry entry, so a dashboard can read its own `marts` / `planned`
        metadata without loading the registry again.
    """
    entry = registry.get(dashboard_id)
    org = registry.org()
    mode = current_mode()
    palette = theme.palette(mode)
    accent = str(entry["accent"]) if mode == "dark" else theme.SERIES_LIGHT[0]

    st.set_page_config(
        page_title=f"{entry['title']} — {org['short']}",
        page_icon="📊",
        layout="wide",
    )

    alt.themes.register("kubera", lambda: theme.chart_theme(mode))
    alt.themes.enable("kubera")
    # Daily price series blow past Altair's 5,000-row default almost immediately —
    # ten years of five tickers is ~12,000 points. These render locally, so embed
    # the rows rather than let the chart raise.
    alt.data_transformers.disable_max_rows()

    st.markdown(
        _CSS.format(
            font=theme.FONT,
            font_display=theme.FONT_DISPLAY,
            accent=accent,
            paper=palette["paper"],
            ink=palette["text_primary"],
            secondary=palette["text_secondary"],
            muted=palette["text_muted"],
            surface=palette["surface"],
            rule=palette["gridline"],
        ),
        unsafe_allow_html=True,
    )
    if mode == "dark":
        st.markdown(
            _DARK_OVERLAY.format(
                paper=palette["paper"],
                ink=palette["text_primary"],
                secondary=palette["text_secondary"],
                muted=palette["text_muted"],
                surface=palette["surface"],
                rule=palette["baseline"],
            ),
            unsafe_allow_html=True,
        )

    st.markdown(f'<div class="k-eyebrow">{org["name"]}</div>', unsafe_allow_html=True)
    st.title(str(entry["title"]))
    st.markdown('<div class="k-rule"></div>', unsafe_allow_html=True)
    st.caption(str(entry["blurb"]))
    return entry


def series_scale_pool() -> list[str]:
    """The metal series for the stock this page is on."""
    return theme.series_for(current_mode())


def require_warehouse() -> None:
    """Stop the page with a build instruction rather than a stack trace."""
    if not warehouse_exists():
        st.error(
            f"No **{warehouse_target()}** warehouse found. Build one first:\n\n"
            "```bash\nmake demo      # offline, from committed fixtures\n"
            "make pipeline  # live data, needs .env keys\n```"
        )
        st.stop()


def table_view(df: pd.DataFrame, label: str = "View data") -> None:
    """Ship the underlying table with every chart, so any number can be checked."""
    with st.expander(label):
        st.dataframe(df, use_container_width=True, hide_index=True)


def empty_state(title: str, reason: str, fix: str) -> None:
    st.info(f"**{title}**\n\n{reason}\n\n**To enable:** {fix}")


def scale_for(all_entities: list[str], picked: list[str]) -> alt.Scale:
    """Colour follows the entity, not its position in the current selection."""
    palette = theme.colors_for(all_entities, current_mode())
    shown = {name: palette[name] for name in picked if name in palette}
    return alt.Scale(domain=list(shown), range=list(shown.values()))


def bar_with_labels(df, x, y, color_field, title, x_title="", fmt=".0f"):
    pool = series_scale_pool()
    muted = theme.palette(current_mode())["text_secondary"]
    base = alt.Chart(df).encode(
        y=alt.Y(f"{y}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=180)),
        x=alt.X(f"{x}:Q", title=x_title, axis=alt.Axis(grid=True)),
    )
    bars = base.mark_bar().encode(
        color=alt.Color(f"{color_field}:N", scale=alt.Scale(range=pool), legend=None),
        tooltip=list(df.columns),
    )
    labels = base.mark_text(align="left", dx=6, color=muted, fontSize=11).encode(
        text=alt.Text(f"{x}:Q", format=fmt)
    )
    return (bars + labels).properties(title=title, height=alt.Step(30))


def line_by(df, x, y, entity, scale, title, y_fmt=None, x_title=None, height=280):
    """A multi-series line, or None when nothing in the selection reports this field."""
    points = df.dropna(subset=[y])
    if points.empty:
        return None
    y_axis = alt.Axis(format=y_fmt) if y_fmt else alt.Undefined
    return (
        alt.Chart(points)
        .mark_line(point=alt.OverlayMarkDef(size=45), strokeWidth=2)
        .encode(
            x=alt.X(x, title=x_title),
            y=alt.Y(f"{y}:Q", title=title, axis=y_axis),
            color=alt.Color(f"{entity}:N", scale=scale, title=None),
            tooltip=[entity, x, alt.Tooltip(f"{y}:Q", format=y_fmt or ",.2f", title=title)],
        )
        .properties(title=title, height=height)
    )


def grid(specs: list, columns: int = 2) -> None:
    """Lay chart specs out in a grid, captioning any the data cannot support."""
    cols = st.columns(columns)
    for index, (chart, title) in enumerate(specs):
        with cols[index % columns]:
            if chart is None:
                st.caption(f"_{title}: not reported for this selection._")
            else:
                st.altair_chart(chart, use_container_width=True)


def footer(entry: dict) -> None:
    """Say where the numbers came from, then where the page is served."""
    marts = entry.get("marts", [])
    if marts:
        source = "Reads " + ", ".join(f"`marts.{m}`" for m in marts)
    else:
        source = entry.get("source", "No warehouse dependency")
    st.divider()
    st.caption(
        f"{source} · served under `{registry.base_path(str(entry['id']))}` "
        f"on port {entry.get('port', '—')}."
    )


def render_stub(dashboard_id: str) -> None:
    """Placeholder body for a dashboard that has not been commissioned yet.

    Kept so a new dashboard can be added to the hub — registry entry, folder, one
    call to this — and appear end to end before any charts exist.
    """
    entry = boot(dashboard_id)
    st.markdown(
        '<div class="k-note">This dashboard has not been built yet. It runs as its own '
        "service on its own port, embedded by the hub — so the charts can be added here "
        "without touching anything else.</div>",
        unsafe_allow_html=True,
    )
    st.write("")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("##### Scope")
        for item in entry.get("planned", []):
            st.markdown(f"- {item}")
    with right:
        st.markdown("##### Sources")
        marts = entry.get("marts", [])
        for mart in marts or []:
            st.markdown(f"- `marts.{mart}`")
        if not marts:
            st.markdown("_Sources not decided yet._")
    footer(entry)
