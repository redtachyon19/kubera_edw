"""Add one company to the warehouse on request.

The warehouse carries 38 holdings because `companies.yml` names 38. The
Companies desk browses ten times that, reading SEC live, so the obvious question
from any name it opens is "why isn't this in the book?" — and the answer should
be a request rather than an edit to a YAML file and a full pipeline run.

This is that request. A ticker goes on a queue; a worker resolves its universe
entry, appends it, pulls its filings, and rebuilds the marts. Afterwards it is a
holding like any other: FX-normalised, tested by dbt, joined to the macro and
price marts, and available to every cross-sectional dashboard rather than only
to the one page that fetched it live.

The queue is a file rather than a table because it has to be readable before the
warehouse exists and by processes that never open it — the market API writes
requests, Dagster reads them, and neither should need a DuckDB connection to see
a status.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from . import config_loader
from .company_resolver import ResolutionError, resolve
from .config_loader import CONFIG_PATH, REPO_ROOT, load_companies

log = logging.getLogger(__name__)

QUEUE_PATH = Path(os.environ.get("BACKFILL_QUEUE", REPO_ROOT / "data" / "backfill_queue.json"))

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
OPEN_STATES = (QUEUED, RUNNING)

# One process at a time inside this interpreter. Across processes the queue is
# written whole and renamed into place, which cannot corrupt it; the residual
# race is two writers within the same millisecond losing one status update, and
# a human-triggered backfill does not run into that.
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def universe() -> set[str]:
    """Tickers currently in `companies.yml`, read fresh.

    `config_loader` memoises the parse for the length of a process, which is
    right for an extractor that runs once and exits and wrong for anything that
    outlives a backfill — the market API would go on reporting a company as
    absent for as long as it stayed up. The file is small; re-read it.
    """
    config_loader._config.cache_clear()
    return {company["ticker"] for company in load_companies()}


def records() -> list[dict]:
    """Every request ever made, oldest first."""
    try:
        with QUEUE_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []


def _write(rows: list[dict]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = QUEUE_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2)
        handle.write("\n")
    temporary.replace(QUEUE_PATH)


def find(ticker: str) -> dict | None:
    ticker = ticker.upper().strip()
    return next((row for row in records() if row["ticker"] == ticker), None)


def update(ticker: str, **fields: Any) -> dict | None:
    """Merge fields into a request, in place."""
    ticker = ticker.upper().strip()
    with _lock:
        rows = records()
        for row in rows:
            if row["ticker"] == ticker:
                row.update(fields)
                _write(rows)
                return row
    return None


def request(ticker: str, hints: dict | None = None) -> dict:
    """Queue a company for the warehouse, or return the request already open.

    Asking twice is not an error and does not queue twice — the second ask
    returns the first request, whatever state it is in. A ticker that failed can
    be asked for again, which resets it to queued.
    """
    ticker = ticker.upper().strip()
    if not ticker:
        raise ValueError("a ticker is required")

    if ticker in universe():
        return {
            "ticker": ticker,
            "status": DONE,
            "note": "already in the warehouse universe",
            "requestedAt": _now(),
        }

    with _lock:
        rows = records()
        for row in rows:
            if row["ticker"] != ticker:
                continue
            if row.get("status") in OPEN_STATES:
                return row
            row.update({"status": QUEUED, "requestedAt": _now(), "error": None})
            _write(rows)
            return row

        row = {
            "ticker": ticker,
            "status": QUEUED,
            "hints": hints or {},
            "requestedAt": _now(),
            "startedAt": None,
            "finishedAt": None,
            "error": None,
        }
        rows.append(row)
        _write(rows)
        log.info("queued %s for backfill", ticker)
        return row


def pending() -> list[dict]:
    """Requests waiting for a worker."""
    return [row for row in records() if row.get("status") == QUEUED]


def _track(ticker: str, hints: dict | None = None) -> dict:
    """Make sure this ticker has a queue row to report progress against.

    `request` deliberately refuses a company already in the universe — there is
    nothing to add. A rebuild of that company is still work worth reporting on,
    though, and without a row every status update afterwards lands nowhere and
    the run finishes with no status at all.
    """
    with _lock:
        rows = records()
        for row in rows:
            if row["ticker"] == ticker:
                return row
        row = {
            "ticker": ticker,
            "status": QUEUED,
            "hints": hints or {},
            "requestedAt": _now(),
            "startedAt": None,
            "finishedAt": None,
            "error": None,
        }
        rows.append(row)
        _write(rows)
        return row


def claim(ticker: str, *, force: bool = False) -> bool:
    """Take ownership of a queued request, atomically.

    More than one worker can be watching: the hub runs one in-process so a
    button press does something on its own, and Dagster runs the same job when
    its daemon is up. Both call this first, and only one can win a given
    request — the loser finds it already running and leaves it alone.
    """
    ticker = ticker.upper().strip()
    with _lock:
        rows = records()
        for row in rows:
            if row["ticker"] != ticker:
                continue
            if not force and row.get("status") != QUEUED:
                return False
            row.update({"status": RUNNING, "startedAt": _now(), "error": None})
            _write(rows)
            return True
    return False


def drain() -> list[dict]:
    """Run every request nobody else has taken. Returns what this worker did."""
    done = []
    for row in pending():
        ticker = row["ticker"]
        if not claim(ticker):
            continue
        done.append(run(ticker))
    return done


def hints_for(ticker: str) -> dict:
    """What the hub already knows about a listing, if its universe file is built.

    Read as data rather than imported: SEC publishes no sector and shouts its
    registrant names, so "NVIDIA CORP / Semiconductors & Related Devices" is
    what a resolution looks like without this, against "NVIDIA Corporation /
    Technology" with it.
    """
    path = REPO_ROOT / "dashboard_hub" / "companies.json"
    try:
        with path.open(encoding="utf-8") as handle:
            entries = json.load(handle)["companies"]
    except (OSError, KeyError, json.JSONDecodeError):
        return {}
    entry = next((row for row in entries if row.get("symbol") == ticker), None)
    if not entry:
        return {}
    return {
        key: entry[source]
        for key, source in (
            ("name", "name"),
            ("sector", "sector"),
            ("country", "country"),
            ("currency", "currency"),
        )
        if entry.get(source)
    }


# ── The work ─────────────────────────────────────────────────────────────────


def _append_to_universe(entry: dict[str, Any]) -> None:
    """Add one holding to `companies.yml`, keeping the file as it was written.

    Appended as text rather than dumped through PyYAML: the file is
    hand-maintained, and a round-trip would strip its comments and reorder every
    key of all 38 existing entries to satisfy one new one.
    """
    text = CONFIG_PATH.read_text(encoding="utf-8")
    if "companies:" not in text:
        raise RuntimeError(f"{CONFIG_PATH} has no companies: block to append to")

    order = (
        "ticker",
        "cik",
        "legal_name",
        "country",
        "country_iso3",
        "currency",
        "reporting_currency",
        "sector",
        "filer_type",
        "fiscal_year_end",
        "xbrl_taxonomy",
    )
    # Quote what YAML would otherwise read as a number or a date — a CIK with
    # leading zeros and a fiscal year end like 12-31 are both strings.
    quoted = {"cik", "fiscal_year_end"}
    lines = [f"\n  - ticker: {entry['ticker']}"]
    lines += [
        f'    {key}: "{entry[key]}"' if key in quoted else f"    {key}: {entry[key]}"
        for key in order
        if key != "ticker"
    ]

    CONFIG_PATH.write_text(text.rstrip("\n") + "\n" + "\n".join(lines) + "\n", encoding="utf-8")

    # Read it back rather than trust the append: a malformed universe file breaks
    # every extractor, and this is the moment to catch it.
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    if entry["ticker"] not in {row["ticker"] for row in parsed["companies"]}:
        raise RuntimeError(f"appended {entry['ticker']} but it is not in the parsed universe")
    config_loader._config.cache_clear()


def _mark_held_in_hub_universe(ticker: str, entry: dict[str, Any]) -> None:
    """Flag the new holding in the hub's browsable universe.

    `companies.json` carries a `warehouse` flag that draws the gold dot on the
    grid and decides whether the desk offers a backfill at all. Left alone it
    would still say no until someone re-ran `make company-universe`, so the
    company would sit in the book while the page offered to add it.
    """
    path = REPO_ROOT / "dashboard_hub" / "companies.json"
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return

    companies = payload.get("companies")
    if not isinstance(companies, list):
        return

    row = next((item for item in companies if item.get("symbol") == ticker), None)
    if row is None:
        # Backfilled from the search box rather than the grid: it belongs in the
        # universe now, with no editorial sector to its name.
        companies.append(
            {
                "symbol": ticker,
                "name": entry["legal_name"],
                "sector": entry["sector"],
                "industry": "",
                "country": entry["country"],
                "currency": entry["currency"],
                "exchange": "",
                "sectors": [],
                "warehouse": True,
            }
        )
        companies.sort(key=lambda item: item["symbol"])
    elif row.get("warehouse"):
        return
    else:
        row["warehouse"] = True

    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temporary.replace(path)


def _run(command: list[str], cwd: Path | None = None) -> None:
    log.info("running %s", " ".join(command))
    result = subprocess.run(  # noqa: S603 — fixed commands, no shell
        command, cwd=str(cwd) if cwd else None, capture_output=True, text=True
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-12:]
        raise RuntimeError(f"{command[0]} failed:\n" + "\n".join(tail))


def run(ticker: str, *, rebuild: bool = True) -> dict:
    """Resolve, land and build one company into the warehouse.

    Args:
        ticker: The company to add.
        rebuild: Run dbt at the end. Off for tests and for batching several
            tickers behind a single build.

    Returns:
        The finished queue record.

    Raises:
        ResolutionError: The ticker is not an SEC registrant or has no filings.
    """
    import sys

    ticker = ticker.upper().strip()
    row = _track(ticker, hints_for(ticker))
    hints = row.get("hints") or hints_for(ticker)
    claim(ticker, force=True)

    try:
        known = {company["ticker"]: company for company in load_companies()}
        if ticker in universe():
            entry = known[ticker]
            log.info("%s is already in the universe — rebuilding rather than re-adding", ticker)
        else:
            entry = resolve(ticker, hints)
            _append_to_universe(entry)

        python = sys.executable
        # Seeds carry the universe into dbt, so they move first.
        _run([python, "-m", "ingestion.generate_seeds"], cwd=REPO_ROOT)

        # Only this company's filings are fetched; everything else already landed
        # stays where it is and is re-read by the loader.
        from .sec_edgar_client import SecEdgarClient

        with SecEdgarClient() as client:
            client.fetch_company_facts(entry["cik"])

        # A new reporting currency needs its rate series before revenue_usd can
        # be computed for it.
        if entry["reporting_currency"] != "USD":
            try:
                _run([python, "-m", "ingestion.fx_client"], cwd=REPO_ROOT)
            except RuntimeError as exc:
                log.warning("FX refresh failed, USD columns may be null for %s: %s", ticker, exc)

        _run([python, "-m", "ingestion.load_raw"], cwd=REPO_ROOT)

        if rebuild:
            target = os.environ.get("DBT_TARGET", "dev")
            environment = {**os.environ, "DBT_PROFILES_DIR": "."}
            log.info("building dbt target %s", target)
            result = subprocess.run(  # noqa: S603
                [str(REPO_ROOT / ".venv" / "bin" / "dbt"), "build", "--target", target],
                cwd=str(REPO_ROOT / "dbt"),
                capture_output=True,
                text=True,
                env=environment,
            )
            if result.returncode != 0:
                tail = (result.stdout or result.stderr or "").strip().splitlines()[-15:]
                raise RuntimeError("dbt build failed:\n" + "\n".join(tail))

        _mark_held_in_hub_universe(ticker, entry)
        finished = update(ticker, status=DONE, finishedAt=_now(), error=None, entry=entry)
        log.info("backfilled %s", ticker)
        return finished or {}

    except (ResolutionError, RuntimeError, OSError) as exc:
        log.error("backfill failed for %s: %s", ticker, exc)
        return update(ticker, status=FAILED, finishedAt=_now(), error=str(exc)) or {}


def main() -> int:
    """Run every queued request, or the tickers named on the command line."""
    import argparse

    from .config_loader import bootstrap

    bootstrap()
    parser = argparse.ArgumentParser(description="Backfill a company into the warehouse.")
    parser.add_argument("tickers", nargs="*", help="tickers to add; default is the queue")
    parser.add_argument("--no-build", action="store_true", help="skip the dbt rebuild")
    args = parser.parse_args()

    wanted = [t.upper() for t in args.tickers] or [row["ticker"] for row in pending()]
    if not wanted:
        print("nothing queued")
        return 0

    failures = 0
    for index, ticker in enumerate(wanted):
        _track(ticker, hints_for(ticker))
        # One build at the end covers every ticker in the batch.
        last = index == len(wanted) - 1
        row = run(ticker, rebuild=last and not args.no_build)
        status = row.get("status")
        print(f"{ticker}: {status}" + (f" — {row.get('error')}" if status == FAILED else ""))
        failures += status == FAILED
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
