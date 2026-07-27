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
    load_dotenv(REPO_ROOT / ".env")


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def bootstrap() -> None:
    load_env()
    configure_logging()


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


def load_companies() -> list[dict[str, Any]]:
    return list(_config()["companies"])


def benchmarks() -> list[str]:
    return list(_config()["benchmarks"]["sector_or_index"])


def tickers() -> list[str]:
    return [c["ticker"] for c in load_companies()]


def price_tickers() -> list[str]:
    return tickers() + benchmarks()


def country_iso3_set() -> set[str]:
    return {c["country_iso3"] for c in load_companies()}


def non_usd_currencies() -> set[str]:
    return {c["currency"] for c in load_companies() if c["currency"] != "USD"}


def cik_for(company: dict[str, Any]) -> str | None:
    cik = company.get("cik")
    return str(cik) if cik else None


def env(name: str, *, required: bool = False) -> str | None:
    value = os.environ.get(name)
    if required and not value:
        raise RuntimeError(f"{name} is required. Set it in .env (see .env.example).")
    return value


_PLACEHOLDER_MARKERS = ("your_", "_here", "change_me", "changeme", "xxx")


def api_key(name: str) -> str | None:
    value = (os.environ.get(name) or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return None
    return value
