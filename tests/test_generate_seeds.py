from __future__ import annotations

import csv
import io

from ingestion.config_loader import load_companies
from ingestion.generate_seeds import COVERAGE_INCEPTION, SEED_PATH, build_rows, render_csv


def test_committed_seed_matches_companies_yml() -> None:
    assert SEED_PATH.exists(), "run: python -m ingestion.generate_seeds"
    assert SEED_PATH.read_text() == render_csv(), (
        "dbt/seeds/seed_companies.csv is out of sync with companies.yml — "
        "re-run `python -m ingestion.generate_seeds` and commit the result."
    )


def test_seed_covers_every_company() -> None:
    rows = build_rows()
    companies = load_companies()
    assert len(rows) == len(companies)
    assert {r["ticker"] for r in rows} == {c["ticker"] for c in companies}


def test_seed_excludes_benchmarks() -> None:
    tickers = {r["ticker"] for r in build_rows()}
    assert "SPY" not in tickers and "ACWI" not in tickers


def test_valid_from_is_fixed_not_run_clock() -> None:
    assert all(r["valid_from"] == COVERAGE_INCEPTION for r in build_rows())
    assert COVERAGE_INCEPTION == "2024-01-01"


def test_cik_leading_zeros_survive_csv_roundtrip() -> None:
    rows = list(csv.DictReader(io.StringIO(render_csv())))
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["AAPL"]["cik"] == "0000320193"
    assert by_ticker["XOM"]["cik"] == "0000034088"
    assert all(len(r["cik"]) == 10 for r in rows)


def test_seed_is_deterministically_ordered() -> None:
    tickers = [r["ticker"] for r in build_rows()]
    assert tickers == sorted(tickers)
