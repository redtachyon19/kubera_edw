"""House palette and Altair theme, in both stocks.

The hub is engraved stationery — bone stock and black ink by default, invertible
to black stock and bone ink. A dashboard is told which stock it is being read on
via a `?theme=` query parameter, so everything here takes a `mode` and the
module-level constants are simply the default mode resolved once.

Series colours stay inside the gold / silver / bronze family in both stocks.
Because they cannot be separated by hue, they are separated by lightness and by
the warm/cool axis instead — which means a chart with more than about five
series is harder to read here than a rainbow scale would be. That is the
deliberate cost of keeping the metals.
"""

from __future__ import annotations

import os

# Deep metals: legible as ink on bone stock.
SERIES_LIGHT = [
    "#8a6a12",  # gold
    "#97561d",  # bronze
    "#5f676c",  # steel
    "#6b4420",  # deep bronze
    "#b08f28",  # antique gold
    "#7d8890",  # silver
    "#6f5514",  # dark gold
    "#3f4a52",  # gunmetal
]

# Bright metals: legible on black stock.
SERIES_DARK = [
    "#e2b84f",  # gold
    "#cd7f32",  # bronze
    "#cfd8de",  # silver
    "#9c6b3f",  # deep bronze
    "#f0dfa4",  # champagne
    "#8a9196",  # pewter
    "#b8912e",  # antique gold
    "#6e7b85",  # gunmetal
]

_LIGHT = {
    "series": SERIES_LIGHT,
    "surface": "#ffffff",
    "paper": "#faf9f5",
    "text_primary": "#0a0a0a",
    "text_secondary": "#33322e",
    "text_muted": "#6f6c63",
    "gridline": "#eae7de",
    "baseline": "#b9b4a7",
    "diverging_mid": "#f0efec",
}

_DARK = {
    "series": SERIES_DARK,
    "surface": "#121211",
    "paper": "#0a0a0a",
    "text_primary": "#f7f4ec",
    "text_secondary": "#cdc9be",
    "text_muted": "#8e8a7f",
    "gridline": "#232220",
    "baseline": "#3d3b36",
    "diverging_mid": "#383835",
}

# House default is the light stock — the American Psycho card, not the terminal.
DEFAULT_MODE = os.environ.get("KUBERA_CHART_MODE", "light").lower()


def palette(mode: str | None = None) -> dict:
    """Every colour for one stock. `mode` is "light" or "dark"."""
    return _DARK if (mode or DEFAULT_MODE).lower() == "dark" else _LIGHT


def series_for(mode: str | None = None) -> list[str]:
    return palette(mode)["series"]


# Copperplate for engraved labels; Optima/Palatino for everything else.
FONT_DISPLAY = "Copperplate, 'Copperplate Gothic Light', Optima, 'Palatino Linotype', serif"
FONT = "Optima, 'Palatino Linotype', Palatino, Georgia, serif"

SEQUENTIAL = ["#f7ecc9", "#eeda9d", "#e2c470", "#d4ad48", "#b8912e", "#96741f", "#6f5514"]

# Semantic, and deliberately outside the metal family — a failing check should
# not read as just another series colour.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# ── Default-mode constants, kept so callers that do not care about mode work. ──
_D = palette()
IS_DARK = DEFAULT_MODE == "dark"
SERIES = _D["series"]
SURFACE = _D["surface"]
TEXT_PRIMARY = _D["text_primary"]
TEXT_SECONDARY = _D["text_secondary"]
TEXT_MUTED = _D["text_muted"]
GRIDLINE = _D["gridline"]
BASELINE = _D["baseline"]
DIVERGING = ["#6f5514", "#b08f28", _D["diverging_mid"], "#7d8890", "#3f4a52"]


def chart_theme(mode: str | None = None) -> dict:
    """Altair config for one stock — transparent plot, hairline axes, engraved titles."""
    p = palette(mode)
    return {
        "config": {
            "background": p["surface"],
            "font": FONT,
            "view": {"stroke": "transparent"},
            "axis": {
                "domainColor": p["baseline"],
                "gridColor": p["gridline"],
                "gridWidth": 1,
                "labelColor": p["text_muted"],
                "labelFontSize": 11,
                "tickColor": p["baseline"],
                "titleColor": p["text_secondary"],
                "titleFont": FONT_DISPLAY,
                "titleFontSize": 10,
                "titleFontWeight": "normal",
            },
            "legend": {
                "labelColor": p["text_secondary"],
                "labelFontSize": 11,
                "titleColor": p["text_muted"],
                "titleFont": FONT_DISPLAY,
                "titleFontSize": 10,
                "symbolType": "square",
            },
            "title": {
                "color": p["text_primary"],
                "font": FONT_DISPLAY,
                "fontSize": 12,
                "fontWeight": "normal",
                "anchor": "start",
                "subtitleColor": p["text_muted"],
            },
        }
    }


def colors_for(entities: list[str], mode: str | None = None) -> dict[str, str]:
    """Colour follows the entity, not its position in the current selection."""
    pool = series_for(mode)
    return {name: pool[i % len(pool)] for i, name in enumerate(sorted(entities))}
