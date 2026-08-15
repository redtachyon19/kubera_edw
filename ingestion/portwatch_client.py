"""IMF PortWatch — the trade desk's spine.

PortWatch estimates what moves through 2,065 ports and 28 maritime chokepoints
by inferring cargo payload from AIS draft readings across roughly 90,000 ships.
It is the only free source that gives daily port-level volume with real history,
and it is what makes the trade desk a time series rather than a snapshot.

Six datasets are landed here, and they answer different questions:

* **ports** / **chokepoints** — the reference tables. Names, ISO3, lat/lon,
  LOCODE, the port's top three industries, and its share of national maritime
  trade. The daily tables carry no geometry, so nothing can be drawn without
  joining to these.
* **port_daily** — 5.7M rows, 2019-01-01 onward, one row per port per day, split
  by vessel class (container, dry bulk, general cargo, roro, tanker) into port
  calls and into import/export metric tons. The volume series.
* **chokepoint_daily** — the same shape for Suez, Panama, Hormuz and 25 others:
  transit counts and aggregate DWT capacity.
* **trade_ribbons** — 1.59M rows of *port → partner country*, valued in US
  dollars per day and split across thirteen named industries with their HS
  sections. Both ends carry coordinates. This is the only free dataset that
  gives a drawable trade link with a real goods type attached, and it is what
  the globe's ribbons are.
* **disruptions** — polygons for events that closed or degraded a port, with
  GDACS alert levels and the list of ports each one hit.

**Two things about this source will catch you out.**

It refreshes *weekly*, on Tuesdays around 09:00 ET, despite every table being
named "Daily". The observed lag is about five days. Treat it as a trend
instrument; anything on screen that implies live telemetry is lying.

And its `date` field is typed `DateOnly` but comes back as a `"YYYY-MM-DD"`
string rather than epoch milliseconds, which is the opposite of every other
ArcGIS date field. Parsing it as epoch yields 1970.

Licence: IMF general terms — attribution required, bulk redistribution not
granted. Cached server-side and served from our own store, never proxied.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .base_client import BaseClient, raw_root

log = logging.getLogger(__name__)

ORG = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services"

# PortWatch's history starts here on every daily table.
HISTORY_START = date(2019, 1, 1)

# The server caps a page at 1,000 rows, but honours a factor of 5 on top of it.
# One request for 5,000 rows rather than five for 1,000 is the difference
# between a twenty-minute backfill and an hour and a half.
PAGE = 5_000
PAGE_FACTOR = 5

# ArcGIS offset paging is only stable under an explicit sort. Without this the
# server is free to return rows in any order per page, which silently duplicates
# some and drops others across a 1,000-page walk.
ORDER_BY = "ObjectId"

# A page that comes back empty when the count said otherwise means the walk has
# desynchronised; give up on that window rather than spin.
MAX_PAGES = 4_000


class PortWatchClient(BaseClient):
    source_name = "portwatch"
    base_url = ORG
    # No key, no quota published, but this is a public ArcGIS host doing real
    # work per request — a backfill is ~1,200 calls and there is no reason to
    # make them back to back.
    min_interval_s = 0.25

    def count(self, service: str, layer: int = 0, where: str = "1=1") -> int:
        """How many rows match, asked before a walk so progress is measurable."""
        response = self._get(
            f"/{service}/FeatureServer/{layer}/query",
            where=where,
            returnCountOnly="true",
            f="json",
        )
        return int(response.json().get("count") or 0)

    def walk(
        self,
        service: str,
        layer: int = 0,
        *,
        where: str = "1=1",
        out_fields: str = "*",
        geometry: bool = False,
    ) -> Iterator[list[dict]]:
        """Every matching row, one page at a time.

        Yields pages rather than a list because the daily tables do not fit
        comfortably in memory a year at a time, and the caller writes each page
        straight through to Parquet.
        """
        offset = 0
        for _ in range(MAX_PAGES):
            response = self._get(
                f"/{service}/FeatureServer/{layer}/query",
                where=where,
                outFields=out_fields,
                orderByFields=ORDER_BY,
                resultRecordCount=PAGE,
                maxRecordCountFactor=PAGE_FACTOR,
                resultOffset=offset,
                returnGeometry="true" if geometry else "false",
                f="json",
            )
            payload = response.json()

            if "error" in payload:
                raise RuntimeError(f"{service}: {payload['error'].get('message')}")

            features = payload.get("features") or []
            if not features:
                return

            rows = [f.get("attributes", {}) for f in features]
            if geometry:
                for row, feature in zip(rows, features, strict=True):
                    row["_geometry"] = feature.get("geometry")
            yield rows

            # `exceededTransferLimit` is the server saying "there is more".
            # Its absence is the only reliable end-of-walk signal: a final page
            # that happens to be exactly PAGE rows long is indistinguishable
            # from a full one by length alone.
            if not payload.get("exceededTransferLimit"):
                return
            offset += len(rows)

        log.warning("%s: stopped at %d pages", service, MAX_PAGES)


# ── Landing ──────────────────────────────────────────────────────────────────
# Parquet rather than the JSON the other clients land, for one reason: 5.7M rows
# of daily port activity is about 3 GB as JSON and under 100 MB as Parquet, and
# the loader can stream it a file at a time instead of holding the lot in memory.


def _dir(dataset: str) -> Path:
    path = raw_root() / "portwatch" / dataset
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Lowercase the columns and rename the two that collide with SQL keywords.

    PortWatch ships columns literally named `import` and `export`. Postgres
    tolerates both unquoted, DuckDB does not, and neither is worth quoting
    through four layers of dbt models — so they are landed as `import_tons` and
    `export_tons`, which is also what they actually are.
    """
    frame = frame.rename(columns={c: str(c).lower() for c in frame.columns})
    return frame.rename(
        columns={
            "import": "import_tons",
            "export": "export_tons",
            "objectid": "source_row_id",
        }
    )


def _write(dataset: str, name: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    frame = _normalise(pd.DataFrame(rows))
    frame["_landed_at"] = datetime.now(UTC).isoformat()
    frame.to_parquet(_dir(dataset) / f"{name}.parquet", index=False)
    return len(frame)


def fetch_reference(
    client: PortWatchClient,
    dataset: str,
    service: str,
    *,
    geometry: bool = False,
    chunk_pages: int = 0,
) -> int:
    """A table PortWatch republishes whole, so it is replaced whole.

    `chunk_pages` flushes to a numbered part file every N pages instead of
    accumulating. The ribbon table is 1.59M rows — held as Python dicts that is
    several gigabytes of interpreter overhead for data that is ~40 MB on disk,
    and it would be the peak memory of the entire pipeline for no reason.
    """
    for stale in _dir(dataset).glob(f"{dataset}*.parquet"):
        # Part counts shrink as well as grow. Without this, a run that lands
        # fewer parts than the last one leaves the tail of the old set behind
        # and the loader reads a mix of two vintages.
        stale.unlink()

    rows: list[dict] = []
    written = 0
    part = 0

    for index, page in enumerate(client.walk(service, where="1=1", geometry=geometry), 1):
        rows.extend(page)
        if chunk_pages and index % chunk_pages == 0:
            written += _write(dataset, f"{dataset}.{part:04d}", rows)
            rows, part = [], part + 1
            log.info("%s: %d rows so far", dataset, written)

    if rows:
        written += _write(dataset, f"{dataset}.{part:04d}" if chunk_pages else dataset, rows)

    log.info("%s: %d rows", dataset, written)
    return written


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start.isoformat(), end.isoformat()


def fetch_daily(
    client: PortWatchClient,
    dataset: str,
    service: str,
    *,
    start: date = HISTORY_START,
    refresh_months: int = 2,
) -> dict[str, int]:
    """Land a daily table month by month, skipping months already complete.

    Windowing by month rather than paging one 5.7M-row walk end to end is what
    makes a backfill resumable: an interrupted run loses at most one month, and
    a re-run costs nothing for the months already on disk. It also keeps every
    `resultOffset` small — ArcGIS gets progressively slower at deep offsets, and
    a single walk would be doing offset arithmetic past five million.

    The last `refresh_months` are always re-fetched. PortWatch publishes weekly
    with a lag of several days, so the newest month on disk is invariably a
    partial month that will have grown since it was written.
    """
    today = datetime.now(UTC).date()
    windows = _months(start, today)
    stale_from = windows[-refresh_months:] if refresh_months else []

    landed: dict[str, int] = {}
    for year, month in windows:
        name = f"{year:04d}-{month:02d}"
        path = _dir(dataset) / f"{name}.parquet"

        if path.exists() and (year, month) not in stale_from:
            continue

        low, high = _month_bounds(year, month)
        where = f"date>=DATE '{low}' AND date<DATE '{high}'"

        rows: list[dict] = []
        for page in client.walk(service, where=where):
            rows.extend(page)

        if not rows:
            # Months past the end of published data are simply absent. Writing
            # an empty file would make them look complete and stop the next run
            # from picking them up once PortWatch catches up.
            continue

        landed[name] = _write(dataset, name, rows)
        log.info("%s %s: %d rows", dataset, name, landed[name])

    return landed


def _manifest(datasets: dict[str, Any]) -> Path:
    """Record what this run landed, so Dagster and `make verify` can report it."""
    path = raw_root() / "portwatch" / "_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"fetched_at": datetime.now(UTC).isoformat(), "datasets": datasets},
            indent=2,
        )
    )
    return path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary: dict[str, Any] = {}

    with PortWatchClient() as client:
        # Reference first: a daily table landed against ports we cannot place on
        # a globe is not usable, and these are three quick calls.
        summary["ports"] = fetch_reference(client, "ports", "PortWatch_ports_database")
        summary["chokepoints"] = fetch_reference(
            client, "chokepoints", "PortWatch_chokepoints_database"
        )
        summary["disruptions"] = fetch_reference(
            client, "disruptions", "portwatch_disruptions_database"
        )

        # The ribbons. 1.59M rows, but a static snapshot rather than a series —
        # PortWatch republishes it whole, so it is replaced whole.
        summary["trade_ribbons"] = fetch_reference(
            client, "trade_ribbons", "spillovers_trade", chunk_pages=20
        )

        summary["chokepoint_daily"] = sum(
            fetch_daily(client, "chokepoint_daily", "Daily_Chokepoints_Data").values()
        )
        summary["port_daily"] = sum(fetch_daily(client, "port_daily", "Daily_Ports_Data").values())

    _manifest(summary)
    for name, rows in summary.items():
        log.info("%-18s %s rows landed this run", name, f"{rows:,}")


if __name__ == "__main__":
    main()
