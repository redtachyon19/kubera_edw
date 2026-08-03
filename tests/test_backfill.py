"""Adding a company to the warehouse on request.

The queue and the universe edit are tested here; the build itself is not, since
it is three subprocesses and a dbt run. What matters at this level is that a
request cannot be lost, cannot be duplicated, and cannot leave `companies.yml`
in a state the extractors will not parse.
"""

from __future__ import annotations

import pytest
import yaml

from ingestion import backfill, config_loader


def _without(text: str, ticker: str) -> str:
    """Drop one holding from a universe file, block and all."""
    lines = text.splitlines(keepends=True)
    out, skipping = [], False
    for line in lines:
        if line.startswith("  - ticker:"):
            skipping = line.split(":", 1)[1].strip() == ticker
        if not skipping:
            out.append(line)
    return "".join(out)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    """A queue and a universe file of this test's own."""
    monkeypatch.setattr(backfill, "QUEUE_PATH", tmp_path / "queue.json")

    # A universe without the test's subject, whatever the real file holds today —
    # NVDA is exactly the kind of name someone backfills for real.
    source = config_loader.CONFIG_PATH.read_text()
    universe = tmp_path / "companies.yml"
    universe.write_text(_without(source, "NVDA"))
    monkeypatch.setattr(config_loader, "CONFIG_PATH", universe)
    monkeypatch.setattr(backfill, "CONFIG_PATH", universe)
    config_loader._config.cache_clear()
    yield tmp_path
    config_loader._config.cache_clear()


NVDA = {
    "ticker": "NVDA",
    "cik": "0001045810",
    "legal_name": "NVIDIA Corporation",
    "country": "United States",
    "country_iso3": "USA",
    "currency": "USD",
    "reporting_currency": "USD",
    "sector": "Technology",
    "filer_type": "10-K",
    "fiscal_year_end": "01-31",
    "xbrl_taxonomy": "us-gaap",
}


def test_a_request_is_queued_once(queue) -> None:
    first = backfill.request("NVDA")
    again = backfill.request("nvda")  # case is not a different company
    assert first["status"] == backfill.QUEUED
    assert again["requestedAt"] == first["requestedAt"]
    assert len(backfill.records()) == 1


def test_a_held_company_is_not_queued(queue) -> None:
    row = backfill.request("AAPL")
    assert row["status"] == backfill.DONE
    assert backfill.records() == [], "an existing holding must not join the queue"


def test_a_failed_request_can_be_asked_for_again(queue) -> None:
    backfill.request("NVDA")
    backfill.update("NVDA", status=backfill.FAILED, error="SEC timed out")
    assert backfill.pending() == []

    retried = backfill.request("NVDA")
    assert retried["status"] == backfill.QUEUED
    assert retried["error"] is None
    assert len(backfill.records()) == 1, "a retry is the same request, not a second one"


def test_pending_covers_only_untouched_requests(queue) -> None:
    backfill.request("NVDA")
    backfill.request("AMD")
    backfill.update("AMD", status=backfill.RUNNING)
    assert [row["ticker"] for row in backfill.pending()] == ["NVDA"]


def test_appending_keeps_the_universe_parseable(queue) -> None:
    before = len(config_loader.load_companies())
    backfill._append_to_universe(NVDA)

    after = config_loader.load_companies()
    assert len(after) == before + 1
    row = next(company for company in after if company["ticker"] == "NVDA")
    assert row == NVDA


def test_the_appended_cik_and_year_end_stay_strings(queue) -> None:
    """Unquoted, YAML reads 0001045810 as an int and 01-31 as a date."""
    backfill._append_to_universe(NVDA)
    with config_loader.CONFIG_PATH.open() as handle:
        parsed = yaml.safe_load(handle)

    row = next(company for company in parsed["companies"] if company["ticker"] == "NVDA")
    assert row["cik"] == "0001045810", "leading zeros are part of a CIK"
    assert isinstance(row["fiscal_year_end"], str)


def test_appending_leaves_every_existing_holding_untouched(queue) -> None:
    """The file is hand-maintained; a backfill adds to it and rewrites nothing."""
    before = config_loader.CONFIG_PATH.read_text()
    backfill._append_to_universe(NVDA)
    after = config_loader.CONFIG_PATH.read_text()
    assert after.startswith(before.rstrip("\n"))


def test_the_universe_is_re_read_rather_than_memoised(queue) -> None:
    """A long-lived process must see a backfill another process just made."""
    assert "NVDA" not in backfill.universe()
    backfill._append_to_universe(NVDA)
    assert "NVDA" in backfill.universe()
