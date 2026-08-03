from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]


def _duckdb_path() -> Path:
    configured = os.environ.get("DUCKDB_PATH")
    if configured:
        return Path(configured)
    return REPO_ROOT / "data" / "kubera_edw.duckdb"


def warehouse_target() -> str:
    return "postgres" if os.environ.get("POSTGRES_HOST") else "duckdb"


@st.cache_resource(show_spinner=False)
def _engine():
    """Postgres pools its own connections, so the engine is worth keeping."""
    from sqlalchemy import create_engine

    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@{os.environ['POSTGRES_HOST']}:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ['POSTGRES_DB']}"
    )
    return create_engine(url, connect_args={"sslmode": os.environ.get("PGSSLMODE", "require")})


@st.cache_data(ttl=300, show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    """Read the marts, holding the file only for as long as the read takes.

    DuckDB is single-writer and takes a file lock, so a dashboard that keeps a
    connection open — even read-only — blocks anything trying to rebuild the
    warehouse underneath it. With four dashboards and the market API all up,
    that was every writer: a pipeline run or a backfill could not start while
    the hub was running. Results are cached for five minutes, so reconnecting
    per query costs a few milliseconds a few times an hour.
    """
    if warehouse_target() == "postgres":
        return pd.read_sql(sql, _engine())

    import duckdb

    con = duckdb.connect(str(_duckdb_path()), read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()


def warehouse_exists() -> bool:
    if warehouse_target() == "postgres":
        return True
    return _duckdb_path().exists()


@st.cache_data(ttl=300, show_spinner=False)
def table_counts() -> dict[str, int]:
    tables = [
        "dim_company",
        "dim_country",
        "dim_currency",
        "fact_financials",
        "fact_macro_indicators",
        "fact_market_prices",
        "fact_gold_price",
    ]
    counts: dict[str, int] = {}
    for table in tables:
        try:
            counts[table] = int(query(f"select count(*) as n from marts.{table}")["n"].iloc[0])
        except Exception:  # noqa: BLE001
            counts[table] = 0
    return counts
