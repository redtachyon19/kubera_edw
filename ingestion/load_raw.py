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
SKIP_TAXONOMIES = {"dei"}


def parse_sec_facts() -> pd.DataFrame:
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
    frames: list[pd.DataFrame] = []
    for path in sorted((raw_root() / "fx").glob("timeseries_*.json")):
        payload = json.loads(path.read_text())
        base = payload.get("base", "USD")
        rows = [
            {
                "rate_date": rate_date,
                "base_currency": base,
                "currency": currency,
                "rate_per_base": rate,
                "source_file": path.name,
            }
            for rate_date, quotes in payload.get("rates", {}).items()
            for currency, rate in quotes.items()
        ]
        if rows:
            frames.append(pd.DataFrame(rows))

    if not frames:
        return _empty(["rate_date", "base_currency", "currency", "rate_per_base", "source_file"])

    combined = pd.concat(frames, ignore_index=True)
    return combined.drop_duplicates(subset=["rate_date", "currency"], keep="last").reset_index(
        drop=True
    )


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})


def parse_gold() -> pd.DataFrame:
    path = raw_root() / "gold_price" / "gold_lbma_fixing.json"
    if not path.exists():
        return _empty(["price_date", "value_raw", "series_id", "source"])
    payload = json.loads(path.read_text())
    series_id = payload.get("series_id", "unknown")
    source = payload.get("source", "fred")
    rows = [
        {
            "price_date": o["date"],
            "value_raw": o["value"],
            "series_id": series_id,
            "source": source,
        }
        for o in payload.get("observations", [])
    ]
    return (
        pd.DataFrame(rows) if rows else _empty(["price_date", "value_raw", "series_id", "source"])
    )


def parse_prices() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    price_columns = [
        "ticker",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source",
    ]
    prices_dir = raw_root() / "prices"
    if not prices_dir.exists():
        return _empty(price_columns)

    for path in sorted(prices_dir.glob("*.csv")):
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
    for path in sorted(prices_dir.glob("av_*.json")):
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
    return pd.DataFrame(rows) if rows else _empty(price_columns)


def parse_imf() -> pd.DataFrame:
    wanted = {c["country_iso3"] for c in load_companies()}
    rows: list[dict[str, Any]] = []
    for path in sorted((raw_root() / "imf").glob("*.json")):
        payload = json.loads(path.read_text())
        for code, by_country in (payload.get("values") or {}).items():
            for iso3, by_year in (by_country or {}).items():
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
    engine = create_engine(url, connect_args={"sslmode": os.environ.get("PGSSLMODE", "require")})
    with engine.begin() as con:
        con.execute(text(f"create schema if not exists {RAW_SCHEMA}"))

    for name, df in tables.items():
        with engine.begin() as con:
            exists = con.execute(
                text(
                    "select 1 from information_schema.tables "
                    "where table_schema = :s and table_name = :t"
                ),
                {"s": RAW_SCHEMA, "t": name},
            ).first()

            if exists:
                con.execute(text(f'truncate table "{RAW_SCHEMA}"."{name}"'))

        df.to_sql(
            name,
            engine,
            schema=RAW_SCHEMA,
            if_exists="append" if exists else "replace",
            index=False,
            chunksize=10_000,
            method="multi",
        )
    engine.dispose()
    return f"postgres:{host}"


def load_all(target: str | None = None) -> dict[str, int]:
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
