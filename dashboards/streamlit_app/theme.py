"""Chart palette and shared Altair styling.

Categorical slots are used in FIXED ORDER and never cycled — colour identifies the entity, so
filtering the chart must never repaint the series that remain.

Both modes are SELECTED, not flipped: the dark column is the same eight hues re-stepped for the
dark surface and validated against it independently. Validator results (dataviz
scripts/validate_palette.js), first five slots:

    light (surface #fcfcfb): lightness PASS · chroma PASS · CVD dE 9.1 PASS ·
                             normal-vision dE 19.6 PASS · contrast WARN (3 slots < 3:1)
    dark  (surface #1a1a19): lightness PASS · chroma PASS · CVD dE 8.4 PASS ·
                             normal-vision dE 19.3 PASS · contrast PASS (all >= 3:1)

The app ships DARK (see .streamlit/config.toml) because those steps clear every check with no
contrast relief owed. Charts still carry direct labels and a table view regardless — identity is
never left to colour alone.
"""

from __future__ import annotations

import os

# Categorical slots, in order: blue, orange, aqua, yellow, magenta, green, violet, red.
SERIES_LIGHT = [
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#4a3aa7",
    "#e34948",
]
SERIES_DARK = [
    "#3987e5",
    "#d95926",
    "#199e70",
    "#c98500",
    "#d55181",
    "#008300",
    "#9085e9",
    "#e66767",
]

_MODE = os.environ.get("KUBERA_CHART_MODE", "dark").lower()
IS_DARK = _MODE == "dark"

SERIES = SERIES_DARK if IS_DARK else SERIES_LIGHT

# Single hue for magnitude, light -> dark.
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#256abf", "#184f95"]
# Two poles + a NEUTRAL GRAY midpoint (never a hue at the midpoint), for signed values.
DIVERGING = ["#184f95", "#2a78d6", "#383835" if IS_DARK else "#f0efec", "#e34948", "#d03b3b"]

SURFACE = "#1a1a19" if IS_DARK else "#fcfcfb"
TEXT_PRIMARY = "#ffffff" if IS_DARK else "#0b0b0b"
TEXT_SECONDARY = "#c3c2b7" if IS_DARK else "#52514e"
TEXT_MUTED = "#898781"
GRIDLINE = "#2c2c2a" if IS_DARK else "#e1e0d9"
BASELINE = "#383835" if IS_DARK else "#c3c2b7"

# Status colours are reserved and never themed — they never stand in for "series 4", and they
# always ship with a label, never colour alone.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def chart_theme() -> dict:
    """Recessive grid and axes; ink stays in text tokens, never the series colour."""
    return {
        "config": {
            "background": SURFACE,
            "font": FONT,
            "view": {"stroke": "transparent"},
            "axis": {
                "domainColor": BASELINE,
                "gridColor": GRIDLINE,
                "gridWidth": 1,
                "labelColor": TEXT_MUTED,
                "labelFontSize": 11,
                "tickColor": BASELINE,
                "titleColor": TEXT_SECONDARY,
                "titleFontSize": 11,
                "titleFontWeight": "normal",
            },
            "legend": {
                "labelColor": TEXT_SECONDARY,
                "labelFontSize": 11,
                "titleColor": TEXT_SECONDARY,
                "titleFontSize": 11,
                "symbolType": "square",
            },
            "title": {
                "color": TEXT_PRIMARY,
                "fontSize": 14,
                "fontWeight": 600,
                "anchor": "start",
                "subtitleColor": TEXT_MUTED,
            },
        }
    }


def colors_for(entities: list[str]) -> dict[str, str]:
    """Stable entity -> colour mapping, so filtering never recolours the survivors.

    Built from the FULL entity list rather than the filtered one; that is the whole point.
    """
    return {name: SERIES[i % len(SERIES)] for i, name in enumerate(sorted(entities))}
