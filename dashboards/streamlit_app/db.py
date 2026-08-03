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
def _connection():
    if warehouse_target() == "postgres":
        from sqlalchemy import create_engine

        url = (
            f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:"
            f"{os.environ['POSTGRES_PASSWORD']}@{os.environ['POSTGRES_HOST']}:"
            f"{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ['POSTGRES_DB']}"
        )
        return create_engine(url, connect_args={"sslmode": os.environ.get("PGSSLMODE", "require")})

    import duckdb

    return duckdb.connect(str(_duckdb_path()), read_only=True)


@st.cache_data(ttl=300, show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    con = _connection()
    if warehouse_target() == "postgres":
        return pd.read_sql(sql, con)
    return con.execute(sql).df()


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
