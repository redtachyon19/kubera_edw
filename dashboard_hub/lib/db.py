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
    """Postgres pools its own connections, so the engine is worth keeping.

    `pool_pre_ping` is not optional against a serverless Postgres. Neon suspends
    its compute when idle and drops the TCP connection with it, so a pooled
    handle that worked an hour ago is dead on the next query. Without the ping,
    SQLAlchemy hands out the corpse, the query fails mid-transaction, and every
    later query on that connection answers "can't reconnect until invalid
    transaction is rolled back" — which is exactly how the Macro Overlay died,
    taking the whole Streamlit process with it on a segfault.

    `pool_recycle` retires connections before the server's own idle timeout can,
    so the ping usually has nothing to catch.
    """
    from sqlalchemy import create_engine

    url = (
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@{os.environ['POSTGRES_HOST']}:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ['POSTGRES_DB']}"
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=280,
        connect_args={
            "sslmode": os.environ.get("PGSSLMODE", "require"),
            "connect_timeout": 15,
            # Keep the socket alive through a suspend rather than discovering it
            # is gone only when a query needs it.
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
        },
    )


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
        engine = _engine()
        try:
            return pd.read_sql(sql, engine)
        except Exception:
            # One failed read must not poison the pool for the rest of the
            # session. Disposing returns every connection and forces the next
            # query to dial fresh; the retry is what turns a suspended database
            # into a slow page rather than a dead dashboard.
            engine.dispose()
            return pd.read_sql(sql, engine)

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
