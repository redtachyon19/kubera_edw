"""US Census international trade, broken out by port of entry.

PortWatch tells you how much *tonnage* crossed a quay and roughly what industry
it belongs to. It cannot tell you that the container was fresh garlic rather
than machine parts, because it is inferring cargo weight from how deep a hull
sits in the water. This is the source that closes that gap, for one country.

`/porths` is US imports and exports at **port of entry × partner country × HS
commodity, monthly**. The port codes join to PortWatch's port database through
the port name, which makes it the deep-dive layer under the global ribbons: the
same quay on the same globe, but with the actual goods named instead of
estimated.

**Commodity detail is requested at HS2 — chapter level — deliberately.** The
endpoint will serve HS10 if asked, which is roughly ten thousand codes per port
per month and a response no dashboard can use. Chapters roll up cleanly into the
21 HS sections, and those roll up into exactly the thirteen industries PortWatch
already uses (see `dbt/seeds/seed_hs_industry.csv`), so the two layers colour
from one scheme rather than two that nearly agree.

**A key is now required.** The published documentation still says 500 queries
per IP per day without one; that is out of date. As of August 2026 every data
endpoint under `api.census.gov` 302-redirects to `missing_key.html` when no key
is supplied — only the `variables.json` metadata is still open. The key is free
and instant: https://api.census.gov/data/key_signup.html. Set `CENSUS_API_KEY`
in `.env`. Without it this extractor logs and returns, and the global PortWatch
layer carries the desk on its own.

Cadence: monthly, on the FT-900 release about five weeks after month end.
Annual revisions land with the April statistics, which is why recent months are
re-fetched rather than trusted once written. Licence: public domain.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .base_client import BaseClient, raw_root

log = logging.getLogger(__name__)

BASE = "https://api.census.gov/data/timeseries/intltrade"

# The endpoint carries data from 2013 onward at port level.
HISTORY_START = date(2013, 1, 1)

# The FT-900 lands about five weeks after the month it covers, and the April
# release rewrites the previous year. Re-fetching a rolling tail costs a handful
# of requests and is the only way revisions ever reach the warehouse.
REFRESH_MONTHS = 14

# Census caps a query at 50 variables. These are well inside it.
#
# GEN_VAL_MO is general imports — everything that physically arrived, which is
# the right denominator for a port. ALL_VAL_MO is its export counterpart. The
# VES_* pair isolates the waterborne share, which is what actually belongs on a
# map of ports: air freight through a "port" code is real trade but it did not
# cross a quay, and including it would inflate coastal airports into seaports.
# The `_SDESC` field carries Census's own description of each HS chapter. It is
# requested rather than kept as a hardcoded table of 97 labels here: the official
# wording is what belongs on screen, and a hand-typed copy is a transcription
# error waiting to happen.
IMPORT_FIELDS = [
    "PORT",
    "PORT_NAME",
    "I_COMMODITY",
    "I_COMMODITY_SDESC",
    "CTY_CODE",
    "CTY_NAME",
    "GEN_VAL_MO",
    "VES_VAL_MO",
    "VES_WGT_MO",
    "CNT_VAL_MO",
]

EXPORT_FIELDS = [
    "PORT",
    "PORT_NAME",
    "E_COMMODITY",
    "E_COMMODITY_SDESC",
    "CTY_CODE",
    "CTY_NAME",
    "ALL_VAL_MO",
    "VES_VAL_MO",
    "VES_WGT_MO",
    "CNT_VAL_MO",
]

FLOWS = {
    "imports": ("imports", IMPORT_FIELDS, "I_COMMODITY"),
    "exports": ("exports", EXPORT_FIELDS, "E_COMMODITY"),
}


class CensusTradeClient(BaseClient):
    source_name = "census_trade"
    base_url = BASE
    min_interval_s = 0.35
    # A month of HS2 detail across every port and partner is a large response
    # to assemble server-side; the 30s default times out on the busier months.
    timeout_s = 120.0

    def __init__(self, *, base_url: str | None = None) -> None:
        super().__init__(base_url=base_url)
        import httpx

        self._client.timeout = httpx.Timeout(self.timeout_s)
        self.api_key = os.environ.get("CENSUS_API_KEY", "").strip()

    def available(self) -> bool:
        return bool(self.api_key)

    def month(self, flow: str, when: str) -> pd.DataFrame:
        """One month of one direction, as a frame. Empty if Census has nothing.

        The response is a JSON **array of arrays** — the first row is the header
        and every later row is positional. It is not a list of objects, and code
        written against the rest of this repo's sources will assume it is.
        """
        path, fields, _ = FLOWS[flow]

        response = self._get(
            f"/{path}/porths",
            get=",".join(fields),
            COMM_LVL="HS2",
            # Detail rows only. 'CGP' rows are country *groupings* — OPEC, EU,
            # Pacific Rim — which overlap each other and the individual
            # countries, so summing a column that mixes them double-counts.
            SUMMARY_LVL="DET",
            time=when,
            key=self.api_key,
        )

        # A missing key is answered with a 302 to an HTML page rather than a 4xx,
        # so a bad key looks like success until the JSON parse fails.
        if "missing_key" in str(response.url) or "invalid_key" in str(response.url):
            raise RuntimeError("Census rejected the API key — check CENSUS_API_KEY in .env")

        try:
            payload = response.json()
        except json.JSONDecodeError:
            # Census answers a window it has no data for with an HTML error
            # page. That is a gap, not a failure.
            return pd.DataFrame()

        if not isinstance(payload, list) or len(payload) < 2:
            return pd.DataFrame()

        header, *rows = payload
        return pd.DataFrame(rows, columns=header)


# ── Landing ──────────────────────────────────────────────────────────────────

# Values arrive as strings even where they are plainly numeric, and Census uses
# a literal "-" for a suppressed or non-applicable cell rather than an empty one.
NUMERIC = {
    "GEN_VAL_MO",
    "ALL_VAL_MO",
    "VES_VAL_MO",
    "VES_WGT_MO",
    "CNT_VAL_MO",
}


def _dir(flow: str) -> Path:
    path = raw_root() / "census_trade" / flow
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tidy(frame: pd.DataFrame, flow: str, when: str) -> pd.DataFrame:
    """Normalise one month into the shape both directions share."""
    if frame.empty:
        return frame

    _, _, commodity_field = FLOWS[flow]
    frame = frame.rename(
        columns={
            commodity_field: "hs_chapter",
            f"{commodity_field}_SDESC": "hs_chapter_name",
            "GEN_VAL_MO": "value_usd",
            "ALL_VAL_MO": "value_usd",
            "VES_VAL_MO": "vessel_value_usd",
            "VES_WGT_MO": "vessel_weight_kg",
            "CNT_VAL_MO": "container_value_usd",
            "PORT": "port_code",
            "PORT_NAME": "port_name",
            "CTY_CODE": "country_code",
            "CTY_NAME": "country_name",
        }
    )

    for column in ("value_usd", "vessel_value_usd", "vessel_weight_kg", "container_value_usd"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    # HS2 codes arrive as "01".."97"; keep them as text so the leading zero
    # survives the round trip into the seed join.
    frame["hs_chapter"] = frame["hs_chapter"].astype(str).str.zfill(2)

    frame["flow"] = "import" if flow == "imports" else "export"
    frame["month"] = when
    frame["_landed_at"] = datetime.now(UTC).isoformat()

    keep = [
        "month",
        "flow",
        "port_code",
        "port_name",
        "country_code",
        "country_name",
        "hs_chapter",
        "hs_chapter_name",
        "value_usd",
        "vessel_value_usd",
        "vessel_weight_kg",
        "container_value_usd",
        "_landed_at",
    ]
    return frame[[c for c in keep if c in frame.columns]]


def _months(start: date, end: date) -> list[str]:
    out = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def fetch_flow(
    client: CensusTradeClient,
    flow: str,
    *,
    start: date = HISTORY_START,
    refresh_months: int = REFRESH_MONTHS,
) -> dict[str, int]:
    """Land every month of one direction, skipping those already complete."""
    today = datetime.now(UTC).date()
    windows = _months(start, today)
    stale = set(windows[-refresh_months:]) if refresh_months else set()

    landed: dict[str, int] = {}
    for when in windows:
        path = _dir(flow) / f"{when}.parquet"
        if path.exists() and when not in stale:
            continue

        frame = _tidy(client.month(flow, when), flow, when)
        if frame.empty:
            continue

        frame.to_parquet(path, index=False)
        landed[when] = len(frame)
        log.info("census %s %s: %d rows", flow, when, len(frame))

    return landed


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with CensusTradeClient() as client:
        if not client.available():
            log.warning(
                "CENSUS_API_KEY is not set — skipping US port-level trade.\n"
                "    Get a free key at https://api.census.gov/data/key_signup.html\n"
                "    and add CENSUS_API_KEY to .env. The global PortWatch layer\n"
                "    does not depend on it."
            )
            return

        summary: dict[str, Any] = {}
        for flow in FLOWS:
            summary[flow] = sum(fetch_flow(client, flow).values())

    path = raw_root() / "census_trade" / "_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": datetime.now(UTC).isoformat(), "datasets": summary}, indent=2)
    )
    for name, rows in summary.items():
        log.info("%-10s %s rows landed this run", name, f"{rows:,}")


if __name__ == "__main__":
    main()
