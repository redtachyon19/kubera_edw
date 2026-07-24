"""Tests for ingestion.generate_seeds — and the drift guard on the committed seed."""

from __future__ import annotations

import csv
import io

from ingestion.config_loader import load_companies
from ingestion.generate_seeds import COVERAGE_INCEPTION, SEED_PATH, build_rows, render_csv


def test_committed_seed_matches_companies_yml() -> None:
    """The committed seed must equal what companies.yml generates.

    dbt builds the dimensions from the committed CSV, so if someone edits companies.yml
    without re-running `python -m ingestion.generate_seeds`, the warehouse would quietly model
    a stale universe. This is the guard that makes that impossible to miss.
    """
    assert SEED_PATH.exists(), "run: python -m ingestion.generate_seeds"
    assert SEED_PATH.read_text() == render_csv(), (
        "dbt/seeds/seed_companies.csv is out of sync with companies.yml — "
        "re-run `python -m ingestion.generate_seeds` and commit the result."
    )


def test_seed_covers_every_company() -> None:
    rows = build_rows()
    assert len(rows) == len(load_companies()) == 9
    assert {r["ticker"] for r in rows} == {
        "AAPL", "MSFT", "JPM", "XOM", "AZN", "SHEL", "TM", "INFY", "BABA",
    }


def test_seed_excludes_benchmarks() -> None:
    # SPY and ACWI are index proxies for relative-performance KPIs, not held positions,
    # so they must never enter the company dimension.
    tickers = {r["ticker"] for r in build_rows()}
    assert "SPY" not in tickers and "ACWI" not in tickers


def test_valid_from_is_fixed_not_run_clock() -> None:
    # The whole point: effective_from must be reproducible across rebuilds.
    assert all(r["valid_from"] == COVERAGE_INCEPTION for r in build_rows())
    assert COVERAGE_INCEPTION == "2024-01-01"


def test_cik_leading_zeros_survive_csv_roundtrip() -> None:
    rows = list(csv.DictReader(io.StringIO(render_csv())))
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["AAPL"]["cik"] == "0000320193"
    # XOM stays pinned to the operating entity, not the reorg holdco.
    assert by_ticker["XOM"]["cik"] == "0000034088"
    assert all(len(r["cik"]) == 10 for r in rows)


def test_seed_is_deterministically_ordered() -> None:
    # Stable ordering keeps the committed file diff-free when unrelated edits happen.
    tickers = [r["ticker"] for r in build_rows()]
    assert tickers == sorted(tickers)
