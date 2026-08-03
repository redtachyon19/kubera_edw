"""Read-only warehouse access for the hub's native pages.

`lib/db.py` already reads the same marts, but it caches through Streamlit and so
only works inside a dashboard process. The market API is a plain stdlib server,
so it needs a path to the warehouse that does not import Streamlit and does not
assume a script run context.

Everything here degrades rather than raises. The Companies desk is built on live
Yahoo data and works on a clean checkout with no warehouse at all; the filed
figures are an extra panel on the 38 names Kubera actually holds, so a missing or
half-built warehouse costs that panel and nothing else.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# One reader at a time, and only for the length of a query.
#
# DuckDB is single-writer and takes a file lock: a process holding the warehouse
# open — even read-only — blocks anything that needs to write it. A long-lived
# handle here meant a backfill could never run while the hub was up, which is
# precisely when someone asks for one. So the connection is opened per query and
# closed again, and the API is a reader that is almost never actually reading.
# Opening a DuckDB file costs a few milliseconds; these are small queries behind
# a page that already waits on the network.
#
# Postgres has no such constraint, so its engine — which pools connections
# itself — is kept.
_lock = threading.Lock()
_engine: Any = None

# A rebuild holds the write lock for as long as dbt runs. Retrying briefly rides
# out the moment between two of its statements; beyond that the caller gets
# nothing back and the page says the warehouse is unavailable rather than hanging.
_LOCK_RETRIES = 3
_LOCK_BACKOFF = 0.25


def _duckdb_path() -> Path:
    configured = os.environ.get("DUCKDB_PATH")
    return Path(configured) if configured else REPO_ROOT / "data" / "kubera_edw.duckdb"


def _postgres() -> bool:
    return bool(os.environ.get("POSTGRES_HOST"))


def _connect() -> Any:
    if _postgres():
        from sqlalchemy import create_engine

        url = (
            f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:"
            f"{os.environ['POSTGRES_PASSWORD']}@{os.environ['POSTGRES_HOST']}:"
            f"{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ['POSTGRES_DB']}"
        )
        return create_engine(url, connect_args={"sslmode": os.environ.get("PGSSLMODE", "require")})

    import duckdb

    path = _duckdb_path()
    if not path.exists():
        raise FileNotFoundError(f"no warehouse at {path}")
    return duckdb.connect(str(path), read_only=True)


def _rows(sql: str, params: list[Any] | None = None) -> list[dict]:
    """Run a parameterised read, or return nothing if the warehouse is unreachable.

    Never raises: a rebuild in progress, a half-built database or no database at
    all all come back empty, and the caller draws a page without the filed panel
    rather than an error.
    """
    global _engine
    with _lock:
        if _postgres():
            try:
                from sqlalchemy import text

                if _engine is None:
                    _engine = _connect()
                bound = {str(i): value for i, value in enumerate(params or [])}
                with _engine.connect() as handle:
                    return [dict(row) for row in handle.execute(text(sql), bound).mappings()]
            except Exception:  # noqa: BLE001 — a data error must not take the page down
                _engine = None
                return []

        for attempt in range(_LOCK_RETRIES):
            connection = None
            try:
                connection = _connect()
                cursor = connection.execute(sql, params or [])
                names = [column[0] for column in cursor.description]
                return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
            except FileNotFoundError:
                # No warehouse right now — which is not the same as never. A dbt
                # rebuild replaces the file, and latching this off for the life
                # of the process meant a company backfilled through the hub
                # showed as absent until the hub was restarted. A stat per query
                # is cheaper than being wrong.
                return []
            except Exception:  # noqa: BLE001 — most often the write lock, held by a rebuild
                if attempt + 1 < _LOCK_RETRIES:
                    time.sleep(_LOCK_BACKOFF * (attempt + 1))
            finally:
                if connection is not None:
                    connection.close()
        return []


def available() -> bool:
    """True when the marts can actually be read right now."""
    return bool(_rows("select 1 as ok"))


def holdings() -> dict[str, dict]:
    """Every current holding, keyed by ticker.

    Returns:
        `{ticker: {legal_name, sector, industry, filer_type, ...}}`, empty when
        there is no warehouse.
    """
    rows = _rows(
        """
        select ticker, cik, legal_name, sector, industry, filer_type,
               country_iso3, domestic_currency, reporting_currency,
               xbrl_taxonomy, fiscal_year_end
        from marts.dim_company
        where is_current
        order by ticker
        """
    )
    return {str(row["ticker"]): row for row in rows}


def quarterly(ticker: str) -> list[dict]:
    """Filed quarterly revenue and result for one holding, oldest first.

    A 10-K filer publishes three 10-Qs and an annual report, so these rows have
    a hole where every fourth quarter should be; the caller fills it from the
    annual figure. Only used when SEC cannot be reached live — with a
    User-Agent configured, `lib/filings.py` returns a longer and denser series.
    """
    marker = ":0" if _postgres() else "?"
    return _rows(
        f"""
        select fiscal_year, period_end_date, reporting_currency,
               revenue, gross_profit, net_income
        from marts.fact_financials
        where period_type = 'Q' and revenue is not null and ticker = {marker}
        order by period_end_date
        """,
        [ticker],
    )


def financials(ticker: str) -> list[dict]:
    """Filed annual figures for one holding, oldest first.

    Both the reported and the USD-converted columns come back: for a 20-F filer
    the gap between them is the exchange rate, not the business, and the panel
    that draws this says so.
    """
    # DuckDB's Python API takes positional parameters; the ticker is never
    # interpolated into the statement.
    marker = ":0" if _postgres() else "?"
    return _rows(
        f"""
        select fiscal_year,
               period_end_date,
               reporting_currency,
               revenue,
               revenue_usd,
               gross_profit,
               operating_income,
               operating_income_usd,
               net_income,
               net_income_usd,
               ebitda,
               ebitda_usd,
               cash_and_equivalents,
               total_debt,
               net_debt,
               net_debt_usd,
               gross_margin,
               ebitda_margin,
               net_margin,
               net_debt_to_ebitda,
               rate_per_usd,
               fx_rate_carried_forward
        from marts.fact_financials
        where period_type = 'FY' and ticker = {marker}
        order by fiscal_year
        """,
        [ticker],
    )
