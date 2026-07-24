"""Configuration loading: the coverage universe (companies.yml) and local env (.env).

Every entrypoint iterates the universe through these helpers rather than hardcoding tickers,
so scaling from the locked 8-company subset to the full ~40-name universe (project_spec.md §6)
is a config edit, not a code change.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).parent / "config" / "companies.yml"
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Load repo-root .env into os.environ (does not override already-set vars).

    The clients read os.environ directly, so entrypoints call this first; without it a
    ``python -m ingestion.<client>`` run would not see keys sitting in .env.
    """
    load_dotenv(REPO_ROOT / ".env")


def configure_logging(level: int = logging.INFO) -> None:
    """Consistent, readable progress output across every extraction entrypoint."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def bootstrap() -> None:
    """Standard entrypoint preamble: load .env, then configure logging."""
    load_env()
    configure_logging()


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def load_companies() -> list[dict[str, Any]]:
    """Every company in the coverage universe, as raw config dicts."""
    return list(_config()["companies"])


def benchmarks() -> list[str]:
    """Benchmark tickers (ETFs) used for relative-performance KPIs — not held positions."""
    return list(_config()["benchmarks"]["sector_or_index"])


def tickers() -> list[str]:
    return [c["ticker"] for c in load_companies()]


def price_tickers() -> list[str]:
    """Everything needing a daily price series: held companies plus benchmarks."""
    return tickers() + benchmarks()


def country_iso3_set() -> set[str]:
    """Distinct ISO-3166 alpha-3 codes across the universe."""
    return {c["country_iso3"] for c in load_companies()}


def non_usd_currencies() -> set[str]:
    """Domestic currencies needing a USD conversion rate (drives the FX pull)."""
    return {c["currency"] for c in load_companies() if c["currency"] != "USD"}


def cik_for(company: dict[str, Any]) -> str | None:
    """The pinned CIK for a company, if scope-lock recorded one.

    Phase 0 pinned CIKs deliberately (XOM's ticker now resolves to a reorg holdco with no
    10-K history), so a pinned value always wins over ticker resolution.
    """
    cik = company.get("cik")
    return str(cik) if cik else None


def env(name: str, *, required: bool = False) -> str | None:
    """Read an env var, optionally failing loudly with a pointer to .env."""
    value = os.environ.get(name)
    if required and not value:
        raise RuntimeError(f"{name} is required. Set it in .env (see .env.example).")
    return value


#: Substrings marking a value copied from .env.example but never filled in.
_PLACEHOLDER_MARKERS = ("your_", "_here", "change_me", "changeme", "xxx")


def api_key(name: str) -> str | None:
    """Return a usable API key, or None if it is absent OR still a placeholder.

    `.env` ships from `.env.example` with values like `your_fred_key_here`, which are truthy.
    A naive `if not os.environ.get(...)` check therefore passes them straight through to the
    API, which answers 400/401 — an error that looks like an outage rather than the real cause
    (nobody filled the key in). Treating a placeholder as absent turns that into a clean,
    self-explanatory skip.
    """
    value = (os.environ.get(name) or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return None
    return value
