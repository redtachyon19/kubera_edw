"""Load landed raw files into the warehouse `raw` schema (the "EL" of ELT).

dbt handles transformation, not extraction or loading — this module bridges the gap between
``data/raw/*`` (landed by the ingestion clients) and the ``raw.*`` source tables that the
Phase-2 staging models read via ``{{ source('raw', ...) }}``.

Why a Python loader rather than reading files from SQL:
  - DuckDB *can* read local JSON directly, but a hosted Postgres (Neon) cannot — the server
    lives in the cloud with no access to your filesystem. Parsing here keeps the staging
    models byte-identical across both targets, so switching warehouse is one dbt flag.
  - Python's json module tolerates duplicate object keys (Alibaba's companyfacts has a
    repeated "Segment" key that makes DuckDB's read_json_auto struct inference fail outright).

Usage:
    python -m ingestion.load_raw                  # -> DuckDB (default)
    LOAD_TARGET=postgres python -m ingestion.load_raw   # -> Neon / any Postgres
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from typing import Any

import pandas as pd

from .base_client import raw_root
from .config_loader import bootstrap, load_companies

log = logging.getLogger(__name__)

RAW_SCHEMA = "raw"
#: Document-metadata taxonomy — filing boilerplate, not financial facts.
SKIP_TAXONOMIES = {"dei"}


# --------------------------------------------------------------------------- parsers
def parse_sec_facts() -> pd.DataFrame:
    """Flatten every companyfacts JSON into tidy fact rows.

    Grain: one row per company per taxonomy/concept per unit per reported period.
    """
    ticker_by_cik = {c["cik"]: c["ticker"] for c in load_companies()}
    rows: list[dict[str, Any]] = []

    for path in sorted((raw_root() / "sec_edgar").glob("companyfacts_CIK*.json")):
        payload = json.loads(path.read_text())
        cik = str(payload.get("cik", "")).zfill(10)
        for taxonomy, concepts in payload.get("facts", {}).items():
            if taxonomy in SKIP_TAXONOMIES:
                continue
            for concept, body in concepts.items():
                for unit, facts in body.get("units", {}).items():
                    for f in facts:
                        rows.append(
                            {
                                "cik": cik,
                                "ticker": ticker_by_cik.get(cik),
                                "entity_name": payload.get("entityName"),
                                "taxonomy": taxonomy,
                                "concept": concept,
                                "unit": unit,
                                "period_start": f.get("start"),
                                "period_end": f.get("end"),
                                "value": f.get("val"),
                                "fiscal_year": f.get("fy"),
                                "fiscal_period": f.get("fp"),
                                "form": f.get("form"),
                                "filed_date": f.get("filed"),
                                "frame": f.get("frame"),
                                "accession": f.get("accn"),
                            }
                        )
    return pd.DataFrame(rows)


def parse_companies() -> pd.DataFrame:
    """The coverage universe itself, as a warehouse table.

    companies.yml stays the single source of truth; loading it here (rather than duplicating
    it into a dbt seed) is what lets the SCD Type 2 snapshot detect classification changes —
    a sector reclassification or a filer-type change edits the YAML, and the next snapshot
    run closes the old row and opens a new one.
    """
    return pd.DataFrame(
        [
            {
                "ticker": c["ticker"],
                "cik": c["cik"],
                "legal_name": c["legal_name"],
                "country": c["country"],
                "country_iso3": c["country_iso3"],
                "currency": c["currency"],
                "reporting_currency": c["reporting_currency"],
                "sector": c["sector"],
                "filer_type": c["filer_type"],
                "fiscal_year_end": c["fiscal_year_end"],
                "xbrl_taxonomy": c["xbrl_taxonomy"],
            }
            for c in load_companies()
        ]
    )


def parse_world_bank() -> pd.DataFrame:
    """Flatten World Bank envelopes, carrying the load stamp for revision auditing."""
    rows: list[dict[str, Any]] = []
    for path in sorted((raw_root() / "world_bank").glob("*.json")):
        env = json.loads(path.read_text())
        for r in env.get("data", []) or []:
            rows.append(
                {
                    "indicator": env["indicator"],
                    "indicator_code": env["indicator_code"],
                    "country_iso3": r.get("countryiso3code"),
                    "country_name": (r.get("country") or {}).get("value"),
                    "year": r.get("date"),
                    "value": r.get("value"),
                    "loaded_at": env.get("loaded_at"),
                    "source_file": path.name,
                }
            )
    return pd.DataFrame(rows)


def parse_fx() -> pd.DataFrame:
    """Unpivot Frankfurter's {date: {ccy: rate}} into (date, currency, rate) rows."""
    rows: list[dict[str, Any]] = []
    for path in sorted((raw_root() / "fx").glob("timeseries_*.json")):
        payload = json.loads(path.read_text())
        base = payload.get("base", "USD")
        for rate_date, quotes in payload.get("rates", {}).items():
            for currency, rate in quotes.items():
                rows.append(
                    {
                        "rate_date": rate_date,
                        "base_currency": base,
                        "currency": currency,
                        "rate_per_base": rate,
                        "source_file": path.name,
                    }
                )
    return pd.DataFrame(rows)


def parse_gold() -> pd.DataFrame:
    """FRED observations. Values stay as text — '.' missing markers are cleaned in staging."""
    path = raw_root() / "gold_price" / "gold_lbma_fixing.json"
    if not path.exists():
        return pd.DataFrame(columns=["price_date", "value_raw", "series_id"])
    payload = json.loads(path.read_text())
    return pd.DataFrame(
        [
            {"price_date": o["date"], "value_raw": o["value"], "series_id": "GOLDAMGBD228NLBM"}
            for o in payload.get("observations", [])
        ]
    )


def parse_prices() -> pd.DataFrame:
    """Daily OHLCV from either backend (Stooq CSV or Alpha Vantage JSON)."""
    rows: list[dict[str, Any]] = []
    prices_dir = raw_root() / "prices"
    if not prices_dir.exists():
        return pd.DataFrame(
            columns=["ticker", "trade_date", "open", "high", "low", "close", "volume"]
        )

    for path in sorted(prices_dir.glob("*.csv")):  # Stooq
        for r in csv.DictReader(io.StringIO(path.read_text())):
            rows.append(
                {
                    "ticker": path.stem,
                    "trade_date": r.get("Date"),
                    "open": r.get("Open"),
                    "high": r.get("High"),
                    "low": r.get("Low"),
                    "close": r.get("Close"),
                    "volume": r.get("Volume"),
                    "source": "stooq",
                }
            )
    for path in sorted(prices_dir.glob("av_*.json")):  # Alpha Vantage
        payload = json.loads(path.read_text())
        ticker = path.stem.removeprefix("av_")
        for trade_date, bar in payload.get("Time Series (Daily)", {}).items():
            rows.append(
                {
                    "ticker": ticker,
                    "trade_date": trade_date,
                    "open": bar.get("1. open"),
                    "high": bar.get("2. high"),
                    "low": bar.get("3. low"),
                    "close": bar.get("4. close"),
                    "volume": bar.get("5. volume"),
                    "source": "alpha_vantage",
                }
            )
    return pd.DataFrame(rows)


def parse_imf() -> pd.DataFrame:
    """IMF DataMapper {values: {indicator: {iso3: {year: value}}}} -> tidy rows."""
    wanted = {c["country_iso3"] for c in load_companies()}
    rows: list[dict[str, Any]] = []
    for path in sorted((raw_root() / "imf").glob("*.json")):
        payload = json.loads(path.read_text())
        for code, by_country in (payload.get("values") or {}).items():
            for iso3, by_year in (by_country or {}).items():
                # IMF returns null for countries it lists but has no series for.
                if iso3 not in wanted or not by_year:
                    continue
                for year, value in by_year.items():
                    rows.append(
                        {
                            "indicator_code": code,
                            "country_iso3": iso3,
                            "year": year,
                            "value": value,
                            "source_file": path.name,
                        }
                    )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- warehouse
def _write_duckdb(tables: dict[str, pd.DataFrame]) -> str:
    import duckdb

    path = os.environ.get("DUCKDB_PATH", "data/kubera_edw.duckdb")
    con = duckdb.connect(path)
    con.execute(f"create schema if not exists {RAW_SCHEMA}")
    for name, df in tables.items():
        con.register("_df", df)
        con.execute(f"create or replace table {RAW_SCHEMA}.{name} as select * from _df")
        con.unregister("_df")
    con.close()
    return f"duckdb:{path}"


def _write_postgres(tables: dict[str, pd.DataFrame]) -> str:
    from sqlalchemy import create_engine, text

    host = os.environ["POSTGRES_HOST"]
    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{host}:{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ['POSTGRES_DB']}"
    )
    # Neon (and every hosted Postgres) requires TLS.
    engine = create_engine(url, connect_args={"sslmode": os.environ.get("PGSSLMODE", "require")})
    with engine.begin() as con:
        con.execute(text(f"create schema if not exists {RAW_SCHEMA}"))
    for name, df in tables.items():
        df.to_sql(name, engine, schema=RAW_SCHEMA, if_exists="replace", index=False,
                  chunksize=10_000, method="multi")
    engine.dispose()
    return f"postgres:{host}"  # host only — never log credentials


def load_all(target: str | None = None) -> dict[str, int]:
    """Parse every landed source and write it to the warehouse's raw schema."""
    target = target or os.environ.get("LOAD_TARGET", "duckdb")
    tables = {
        "companies": parse_companies(),
        "sec_edgar_facts": parse_sec_facts(),
        "world_bank_macro": parse_world_bank(),
        "fx_rates": parse_fx(),
        "gold_prices": parse_gold(),
        "market_prices": parse_prices(),
        "imf_macro": parse_imf(),
    }
    for name, df in tables.items():
        if df.empty:
            log.warning("%s: 0 rows (source not landed yet)", name)
        else:
            log.info("%s: %s rows", name, f"{len(df):,}")

    if target == "duckdb":
        dest = _write_duckdb(tables)
    elif target == "postgres":
        dest = _write_postgres(tables)
    else:
        raise ValueError(f"unknown LOAD_TARGET {target!r} (duckdb | postgres)")

    log.info("loaded %d tables into %s.%s", len(tables), dest, RAW_SCHEMA)
    return {name: len(df) for name, df in tables.items()}


def main() -> None:
    bootstrap()
    load_all()


if __name__ == "__main__":
    main()
