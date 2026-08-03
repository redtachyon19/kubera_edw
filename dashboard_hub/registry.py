"""Read `dashboards.json` — the single source of truth for the hub.

The file is organised the way the UI is: a list of sections (the top-bar tabs),
each holding one or more dashboards. The same file drives three things that would
otherwise drift apart — the Streamlit processes `run_local.py` spawns, the Vite dev
proxy table, and the hub's navigation. Adding a dashboard means editing this file
and creating its folder under `dashboard_hub/dashboards/`; nothing else.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROOT_DIR.parent
REGISTRY_PATH = ROOT_DIR / "dashboards.json"


@lru_cache(maxsize=1)
def registry() -> dict[str, Any]:
    with REGISTRY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def org() -> dict[str, str]:
    return registry()["org"]


def theme() -> dict[str, Any]:
    return registry().get("theme", {})


def sections() -> list[dict[str, Any]]:
    """The top-bar tabs, each with its own dashboards."""
    return registry()["sections"]


def dashboards() -> list[dict[str, Any]]:
    """Every dashboard across every section, each tagged with its section."""
    flat: list[dict[str, Any]] = []
    for section in sections():
        for entry in section["dashboards"]:
            flat.append({**entry, "section_slug": section["slug"], "accent": section["accent"]})
    return flat


def servable() -> list[dict[str, Any]]:
    """Dashboards with their own Streamlit process — the rest are nav slots for now."""
    return [entry for entry in dashboards() if entry.get("status") == "stub"]


def get(dashboard_id: str) -> dict[str, Any]:
    for entry in dashboards():
        if entry["id"] == dashboard_id:
            return entry
    known = ", ".join(entry["id"] for entry in dashboards())
    raise KeyError(f"Unknown dashboard id {dashboard_id!r}. Known ids: {known}")


def base_path(dashboard_id: str) -> str:
    """The sub-path a dashboard is served under, e.g. `/d/fundamentals`."""
    return f"{registry()['basePrefix'].rstrip('/')}/{dashboard_id}"


def dashboard_dir(entry: dict[str, Any]) -> Path:
    return ROOT_DIR / "dashboards" / str(entry["module"])
