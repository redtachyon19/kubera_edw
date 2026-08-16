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

**Requests are chunked by chapter, not by month, and this is not a free choice.**
Ask for one month across all 97 chapters and Census answers HTTP 500 after about
150 seconds — it cannot assemble that response, with or without the partner
dimension. Ask for one chapter and it is fine. Multiple chapters cannot be
bundled either: repeating `I_COMMODITY` 500s, and a comma-separated list is read
as one literal code and returns 204.

What it *will* do is serve a whole date range in a single call. One chapter
across the full thirteen years comes back in about 100 seconds — 268,000 rows
for chapter 27. So the backfill is **97 chapters × 2 directions = 194 requests**
rather than the 32,000 that month-chunking would have needed. Storage is still
per year, so a refresh re-fetches one cheap year rather than the whole history.

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
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .base_client import BaseClient, raw_root
from .config_loader import api_key, bootstrap

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
    # A full-history pull for one chapter is ~100s server-side and 18MB on the
    # wire for the big ones, so the default 30s is nowhere near enough.
    timeout_s = 300.0

    def __init__(self, *, base_url: str | None = None) -> None:
        super().__init__(base_url=base_url)
        import httpx

        self._client.timeout = httpx.Timeout(self.timeout_s)
        # Through `api_key` rather than straight off the environment, so the
        # repo's placeholder markers (`your_`, `_here`, `xxx`) count as unset.
        # A literal "your_census_key_here" left in `.env` would otherwise look
        # like a real key, get sent, and come back as a redirect to an HTML page
        # — which is a much more confusing failure than "no key".
        self.api_key = api_key("CENSUS_API_KEY") or ""

    def available(self) -> bool:
        return bool(self.api_key)

    def chapter(self, flow: str, hs_chapter: str, window: str) -> pd.DataFrame:
        """One HS chapter of one direction over `window`, as a frame.

        `window` is Census's own `time` syntax — a year (`"2025"`), a range
        (`"from 2013-01 to 2026-12"`), or a single month. One chapter at a time
        because that is the only shape the endpoint reliably serves; see the
        module docstring.

        The response is a JSON **array of arrays** — the first row is the header
        and every later row is positional. It is not a list of objects, and code
        written against the rest of this repo's sources will assume it is.
        """
        path, fields, commodity = FLOWS[flow]

        response = self._get(
            f"/{path}/porths",
            get=",".join(fields),
            COMM_LVL="HS2",
            # Detail rows only. 'CGP' rows are country *groupings* — OPEC, EU,
            # Pacific Rim — which overlap each other and the individual
            # countries, so summing a column that mixes them double-counts.
            SUMMARY_LVL="DET",
            **{commodity: hs_chapter},
            time=window,
            key=self.api_key,
        )

        # A missing key is answered with a 302 to an HTML page rather than a 4xx,
        # so a bad key looks like success until the JSON parse fails.
        if "missing_key" in str(response.url) or "invalid_key" in str(response.url):
            raise RuntimeError("Census rejected the API key — check CENSUS_API_KEY in .env")

        # 204 is Census for "that combination exists but holds nothing", which
        # is normal for a chapter no port handled in the window.
        if response.status_code == 204 or not response.content:
            return pd.DataFrame()

        try:
            payload = response.json()
        except json.JSONDecodeError:
            # Census answers a window it has no data for with an HTML error
            # page. That is a gap, not a failure.
            return pd.DataFrame()

        if not isinstance(payload, list) or len(payload) < 2:
            return pd.DataFrame()

        header, *rows = payload
        frame = pd.DataFrame(rows, columns=header)

        # Census echoes the filter back as an extra column: asking for
        # `I_COMMODITY` in `get` *and* filtering on `I_COMMODITY=27` returns two
        # columns of that name. Left alone, `frame["hs_chapter"]` is a
        # two-column DataFrame rather than a Series and every downstream string
        # operation fails. The duplicates are identical, so the first wins.
        return frame.loc[:, ~frame.columns.duplicated()]


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


def _tidy(frame: pd.DataFrame, flow: str) -> pd.DataFrame:
    """Normalise a response into the shape both directions share.

    The month comes off each row's own `time` field rather than being stamped on
    from the request, because a request now spans many months at once.
    """
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
            "time": "month",
        }
    )

    for column in ("value_usd", "vessel_value_usd", "vessel_weight_kg", "container_value_usd"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    # HS2 codes arrive as "01".."97"; keep them as text so the leading zero
    # survives the round trip into the seed join.
    frame["hs_chapter"] = frame["hs_chapter"].astype(str).str.zfill(2)

    frame["flow"] = "import" if flow == "imports" else "export"
    frame["_landed_at"] = datetime.now(UTC).isoformat()

    # Drop Census's roll-up rows, on BOTH dimensions. Despite SUMMARY_LVL=DET the
    # response carries a "TOTAL FOR ALL COUNTRIES" line per port (CTY_CODE='-')
    # and a "TOTAL FOR ALL PORTS" line per country (PORT='-'), each exactly the
    # sum of the detail beside it. New York 2013-01: 16 country rows and the
    # total both come to $135,222,629. June 2025 chapter 27: the all-ports row
    # alone is 50% of the sum. Left in, the annual totals came out at 1.92x the
    # published FT-900 — wrong everywhere, and not obviously so.
    frame = frame[(frame["country_code"] != "-") & (frame["port_code"] != "-")]

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


# HS chapters run 01–97. 77 is reserved and never returns anything; it is left in
# the sweep rather than special-cased, because an empty answer costs one cheap
# request and a hardcoded exception list rots the moment the HS is revised.
CHAPTERS = [f"{n:02d}" for n in range(1, 98)]


def _window(start: date, end: date) -> str:
    """Census `time` syntax for a span. One call can cover the whole history."""
    return f"from {start:%Y-%m} to {end:%Y-%m}"


def fetch_chapter(
    client: CensusTradeClient,
    flow: str,
    hs_chapter: str,
    *,
    start: date,
    end: date,
) -> int:
    """Land one chapter over a span, split into one Parquet file per year.

    Requesting and storing are deliberately different granularities. The request
    is as wide as Census will serve — the whole history in one call, which is
    what keeps the backfill to 194 requests instead of 32,000. Storage is per
    year, so the monthly refresh re-fetches a single cheap year and overwrites
    one file rather than rewriting thirteen years of history.
    """
    frame = _tidy(client.chapter(flow, hs_chapter, _window(start, end)), flow)
    if frame.empty:
        return 0

    written = 0
    for year, part in frame.groupby(frame["month"].str.slice(0, 4)):
        path = _dir(flow) / f"hs{hs_chapter}_{year}.parquet"
        part.to_parquet(path, index=False)
        written += len(part)
    return written


def fetch_flow(
    client: CensusTradeClient,
    flow: str,
    *,
    start: date = HISTORY_START,
    refresh_months: int = REFRESH_MONTHS,
    chapters: list[str] | None = None,
) -> dict[str, int]:
    """Land every chapter of one direction.

    A chapter already on disk is refetched only for the years the refresh window
    touches — Census revises recent months, and the April release rewrites the
    previous year, so the trailing window has to be re-read rather than trusted.
    A chapter with nothing on disk is pulled over its full history.
    """
    today = datetime.now(UTC).date()

    # Step back `refresh_months` whole months, then widen to that year's start —
    # storage is per year, so the smallest thing worth re-fetching is a year.
    total = today.year * 12 + (today.month - 1) - refresh_months
    refresh_from = date(total // 12, 1, 1)

    landed: dict[str, int] = {}
    for hs_chapter in chapters or CHAPTERS:
        landed_years = sorted(_dir(flow).glob(f"hs{hs_chapter}_*.parquet"))

        # Never fetched: take the whole history in one call. Already held: only
        # re-read the years the revision window can still move.
        window_start = start if not landed_years else refresh_from
        rows = fetch_chapter(client, flow, hs_chapter, start=window_start, end=today)

        if rows:
            landed[hs_chapter] = rows
            log.info(
                "census %s ch%s: %s rows from %s",
                flow,
                hs_chapter,
                f"{rows:,}",
                window_start.year,
            )

    return landed


def main() -> None:
    # Loads `.env` and configures logging, exactly as every other extractor's
    # entry point does. Without it `python -m ingestion.census_trade_client`
    # starts with an empty environment, finds no key, and skips the whole source
    # while reporting success — which is a silent no-op, not a failure.
    bootstrap()

    # httpx logs every request line at INFO, and Census takes its key as a
    # query parameter rather than a header — so the default logging writes the
    # secret into stdout and into Dagster's captured run logs. Nothing here
    # needs per-request logging; this client reports per chapter instead.
    logging.getLogger("httpx").setLevel(logging.WARNING)

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
            log.info("census %s: sweeping %d HS chapters", flow, len(CHAPTERS))
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
