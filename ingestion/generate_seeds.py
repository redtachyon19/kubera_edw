"""Generate dbt seeds from ingestion/config/companies.yml.

Why generate rather than hand-maintain: the dimension slice must build from COMMITTED seeds
alone, with no landed data and no database — that is what lets CI build and test the
dimensions on a fresh DuckDB. But companies.yml has to stay the single source of truth, so
the seed is derived from it rather than duplicated by hand.

The generated CSV is committed. Re-run this whenever companies.yml changes; a drift test
(tests/test_generate_seeds.py) fails the build if the committed seed falls out of sync.

Usage:
    python -m ingestion.generate_seeds
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

from .config_loader import bootstrap, load_companies

log = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent.parent / "dbt" / "seeds" / "seed_companies.csv"

#: Date the portfolio is modelled as having taken these positions. Fixed and explicit so a
#: dimension rebuild reproduces the same effective_from instead of stamping the run clock —
#: history must not shift just because the warehouse was rebuilt on a different day.
COVERAGE_INCEPTION = "2024-01-01"

FIELDS = [
    "ticker",
    "cik",
    "legal_name",
    "country_name",
    "country_iso3",
    "currency_iso",
    "reporting_currency",
    "sector",
    "industry",
    "filer_type",
    "fiscal_year_end",
    "xbrl_taxonomy",
    "valid_from",
]


def build_rows() -> list[dict[str, str]]:
    """Project companies.yml into flat seed rows (held companies only, no benchmarks)."""
    rows = []
    for c in load_companies():
        rows.append(
            {
                "ticker": c["ticker"],
                "cik": c["cik"],
                "legal_name": c["legal_name"],
                "country_name": c["country"],
                "country_iso3": c["country_iso3"],
                "currency_iso": c["currency"],
                "reporting_currency": c["reporting_currency"],
                "sector": c["sector"],
                # companies.yml carries no industry yet; kept for the §9 column set.
                "industry": c.get("industry", ""),
                "filer_type": c["filer_type"],
                "fiscal_year_end": c["fiscal_year_end"],
                "xbrl_taxonomy": c["xbrl_taxonomy"],
                "valid_from": c.get("valid_from", COVERAGE_INCEPTION),
            }
        )
    return sorted(rows, key=lambda r: r["ticker"])


def render_csv() -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(build_rows())
    return buf.getvalue()


def write_seed() -> Path:
    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEED_PATH.write_text(render_csv())
    return SEED_PATH


def main() -> None:
    bootstrap()
    path = write_seed()
    log.info("wrote %s (%d companies)", path, len(build_rows()))


if __name__ == "__main__":
    main()
