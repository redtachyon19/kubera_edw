from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

from .config_loader import bootstrap, load_companies

log = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent.parent / "dbt" / "seeds" / "seed_companies.csv"

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
