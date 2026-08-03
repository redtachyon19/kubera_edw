from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import market_data as md  # noqa: E402

from dashboard_hub.lib import theme, ui  # noqa: E402

entry = ui.boot("stock-explorer")
st.caption(
    "Live from Yahoo Finance — any listed company, not just the 38 in the portfolio. "
    "No warehouse and no API key needed."
)

if "explorer_symbols" not in st.session_state:
    st.session_state.explorer_symbols = ["AAPL", "MSFT"]


def add(symbol: str) -> None:
    if symbol and symbol not in st.session_state.explorer_symbols:
        st.session_state.explorer_symbols.append(symbol)


# ── Search ────────────────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("##### Add a company")
    query = st.text_input(
        "Search by name or ticker",
        placeholder="apple, tesla, AAPL, 7203.T, ^GSPC …",
        label_visibility="collapsed",
    )
    if query:
        matches = md.search(query)
        if not matches:
            st.caption("No matches. Try a ticker directly, e.g. `AAPL` or `7203.T`.")
        for match in matches:
            col_a, col_b = st.columns([5, 1])
            col_a.markdown(
                f"**{match['symbol']}** — {match['name']}  \n"
                f"<span style='color:{theme.TEXT_MUTED};font-size:.78rem'>"
                f"{match['type']} · {match['exchange']}</span>",
                unsafe_allow_html=True,
            )
            already = match["symbol"] in st.session_state.explorer_symbols
            col_b.button(
                "Added" if already else "Add",
                key=f"add_{match['symbol']}",
                disabled=already,
                on_click=add,
                args=(match["symbol"],),
                use_container_width=True,
            )

# ── Controls ──────────────────────────────────────────────────────────────────
st.session_state.explorer_symbols = st.multiselect(
    "Comparing",
    options=sorted(set(st.session_state.explorer_symbols)),
    default=sorted(set(st.session_state.explorer_symbols)),
    help="Remove a company with the × on its chip.",
)

left, middle, right = st.columns([2, 2, 3])
period_label = left.radio("Period", list(md.PERIODS), index=1, horizontal=True)
show_gold = middle.toggle("Add gold", value=True, help=md.GOLD_LABEL)
mode = right.radio(
    "Scale",
    list(md.SCALES),
    horizontal=True,
    help=(
        "Rebased is the plain comparable view. Growth of 100 on a log axis is the one to use "
        "over ten years or all time, where one big winner otherwise flattens everything else."
    ),
)

symbols = list(st.session_state.explorer_symbols)
if show_gold and md.GOLD_SYMBOL not in symbols:
    symbols.append(md.GOLD_SYMBOL)

if not symbols:
    ui.empty_state(
        "Nothing selected",
        "No companies are being compared.",
        "search above and press **Add**, or switch on **Add gold**.",
    )
    st.stop()

# ── Data ──────────────────────────────────────────────────────────────────────
with st.spinner("Fetching prices…"):
    raw = md.closes(tuple(symbols), md.PERIODS[period_label])

missing = [s for s in symbols if s not in raw.columns]
if missing:
    st.warning(f"No data returned for: {', '.join(missing)}")
if raw.empty:
    st.error("No price data came back for this selection.")
    st.stop()

aligned, start, limiting = md.align(raw)
if aligned.empty or start is None:
    st.error("These series have no overlapping trading history.")
    st.stop()

label_for = {s: (md.GOLD_LABEL if s == md.GOLD_SYMBOL else s) for s in aligned.columns}

# ── Chart ─────────────────────────────────────────────────────────────────────
y_title, axis_type, transform = md.SCALES[mode]
plotted = transform(aligned)

tidy = (
    plotted.rename(columns=label_for)
    .reset_index(names="date")
    .melt("date", var_name="series", value_name="value")
)


def palette_for(labels: list[str], gold: str | None) -> dict[str, str]:
    """Gold is literally drawn in gold; every other series takes a different metal.

    The gold slot is withheld from the pool when gold is on the chart, otherwise the
    first company alphabetically would be given the identical colour.
    """
    pool = theme.SERIES[1:] if gold else theme.SERIES
    others = sorted(name for name in labels if name != gold)
    assigned = {name: pool[i % len(pool)] for i, name in enumerate(others)}
    if gold:
        assigned[gold] = theme.SERIES[0]
    return assigned


domain = [label_for[s] for s in aligned.columns]
palette = palette_for(domain, md.GOLD_LABEL if md.GOLD_SYMBOL in aligned.columns else None)

st.altair_chart(
    alt.Chart(tidy)
    .mark_line(strokeWidth=2)
    .encode(
        x=alt.X("date:T", title=None),
        y=alt.Y(
            "value:Q",
            title=y_title,
            axis=alt.Axis(format=",.0f"),
            scale=alt.Scale(zero=False, type=axis_type),
        ),
        color=alt.Color(
            "series:N",
            scale=alt.Scale(domain=domain, range=[palette[d] for d in domain]),
            title=None,
        ),
        tooltip=[
            "series",
            alt.Tooltip("date:T"),
            alt.Tooltip("value:Q", format=",.2f", title=y_title),
        ],
    )
    .properties(height=420),
    use_container_width=True,
)

note = f"Window starts {start:%d %b %Y}"
if limiting and len(aligned.columns) > 1:
    note += f", the earliest date **{label_for[limiting]}** has data for in this period"
st.caption(
    f"{note}. "
    + (
        "Each series is in its own listing currency, so absolute levels are not comparable "
        "— use a rebased scale to compare."
        if mode.startswith("Actual")
        else "All series start level at that date, so they compare directly."
    )
)

# ── Stats ─────────────────────────────────────────────────────────────────────
stats = md.summarise(aligned)
if not stats.empty:
    stats.insert(1, "currency", [md.currency_of(s) for s in stats["symbol"]])
    stats["symbol"] = stats["symbol"].map(label_for)
    st.markdown("##### Over this window")
    st.dataframe(
        stats.rename(
            columns={
                "symbol": "Series",
                "currency": "Ccy",
                "start_price": "Start",
                "end_price": "End",
                "total_return": "Total return",
                "cagr": "CAGR",
                "annualised_vol": "Ann. volatility",
                "max_drawdown": "Max drawdown",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Start": st.column_config.NumberColumn(format="%.2f"),
            "End": st.column_config.NumberColumn(format="%.2f"),
            "Total return": st.column_config.NumberColumn(format="percent"),
            "CAGR": st.column_config.NumberColumn(format="percent"),
            "Ann. volatility": st.column_config.NumberColumn(format="percent"),
            "Max drawdown": st.column_config.NumberColumn(format="percent"),
        },
    )
    st.caption(
        "Returns are in each security's own listing currency — a non-USD listing mixes "
        "business performance with the exchange rate. Prices are split- and "
        "dividend-adjusted."
    )

ui.table_view(aligned.rename(columns=label_for).reset_index(names="date"), "View price data")
ui.footer(entry)
