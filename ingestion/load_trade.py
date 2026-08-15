"""Land the Parquet trade datasets into the warehouse's `raw` schema.

Separate from `load_raw.py` for one reason: that module builds every table as a
DataFrame in a dict and then writes the dict. That is exactly right for the
sources it handles — the largest is a few hundred thousand rows — and exactly
wrong for daily port activity, which is 5.7M rows and growing by about 64,000 a
month. Holding it in memory alongside everything else, and then inserting it a
row at a time through SQLAlchemy, turns a two-minute load into an hour.

So these stream instead. Each dataset is a directory of Parquet files written by
`portwatch_client` or `census_trade_client`, and each file is pushed straight
into Postgres with `COPY ... FROM STDIN`, which is the only bulk path Postgres
has that is not several times slower than the data deserves. DuckDB reads the
Parquet directly and needs no help at all.

Both writers replace the table wholesale. These sources are re-derived from
files on disk that are themselves idempotent, so a re-run is a rebuild rather
than a merge — there is no partial state to reconcile and nothing to
de-duplicate.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import pandas as pd

from .base_client import REPO_ROOT, raw_root

log = logging.getLogger(__name__)

RAW_SCHEMA = "raw"

# Warehouse table name -> the directory of Parquet parts that fills it.
DATASETS: dict[str, str] = {
    "portwatch_ports": "portwatch/ports",
    "portwatch_chokepoints": "portwatch/chokepoints",
    "portwatch_disruptions": "portwatch/disruptions",
    "portwatch_trade_ribbons": "portwatch/trade_ribbons",
    "portwatch_port_daily": "portwatch/port_daily",
    "portwatch_chokepoint_daily": "portwatch/chokepoint_daily",
    "census_port_trade_imports": "census_trade/imports",
    "census_port_trade_exports": "census_trade/exports",
}

# Rows per COPY batch. Large enough that the round trip is amortised, small
# enough that the CSV buffer stays well inside a few hundred megabytes.
BATCH = 200_000


def _parts(dataset: str) -> list[Path]:
    directory = raw_root() / dataset
    if not directory.exists():
        return []
    return sorted(directory.glob("*.parquet"))


def _postgres_engine():
    from sqlalchemy import create_engine

    return create_engine(
        f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@{os.environ['POSTGRES_HOST']}:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/{os.environ['POSTGRES_DB']}",
        connect_args={"sslmode": os.environ.get("PGSSLMODE", "disable")},
    )


def _copy(connection, table: str, frame: pd.DataFrame) -> None:
    """Push one batch through COPY, as CSV, over the raw psycopg2 cursor."""
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, header=False, na_rep="\\N")
    buffer.seek(0)

    columns = ", ".join(f'"{c}"' for c in frame.columns)
    cursor = connection.connection.cursor()
    cursor.copy_expert(
        f'COPY "{RAW_SCHEMA}"."{table}" ({columns}) FROM STDIN WITH (FORMAT csv, NULL \'\\N\')',
        buffer,
    )


def _write_postgres(table: str, parts: list[Path]) -> int:
    from sqlalchemy import text

    engine = _postgres_engine()
    written = 0

    with engine.begin() as connection:
        connection.execute(text(f"create schema if not exists {RAW_SCHEMA}"))

    head = pd.read_parquet(parts[0])

    # Truncate an existing table rather than replacing it. `if_exists="replace"`
    # issues a DROP, and once dbt has built `staging.stg_portwatch__*` on top of
    # these, Postgres refuses the drop — the second pipeline run fails where the
    # first succeeded. Truncate empties the table without touching the dependent
    # views, which is also what `load_raw.py` does for the same reason.
    with engine.begin() as connection:
        exists = connection.execute(
            text(
                "select 1 from information_schema.tables "
                "where table_schema = :schema and table_name = :table"
            ),
            {"schema": RAW_SCHEMA, "table": table},
        ).first()

        if exists:
            connection.execute(text(f'truncate table "{RAW_SCHEMA}"."{table}"'))

    if not exists:
        # First run: let pandas infer Postgres types from the Parquet dtypes
        # rather than hand-writing DDL per dataset.
        head.head(0).to_sql(table, engine, schema=RAW_SCHEMA, if_exists="replace", index=False)

    with engine.begin() as connection:
        for part in parts:
            frame = pd.read_parquet(part)
            if frame.empty:
                continue
            # Column order has to match the CREATE, not the file: a Parquet part
            # written by a later run can carry the same columns in a different
            # order, and COPY is positional.
            frame = frame.reindex(columns=head.columns)
            for start in range(0, len(frame), BATCH):
                _copy(connection, table, frame.iloc[start : start + BATCH])
            written += len(frame)

    engine.dispose()
    return written


def _write_duckdb(table: str, parts: list[Path]) -> int:
    import duckdb

    configured = os.environ.get("DUCKDB_PATH")
    path = Path(configured) if configured else REPO_ROOT / "data" / "kubera_edw.duckdb"
    if not path.is_absolute():
        path = REPO_ROOT / path

    connection = duckdb.connect(str(path))
    connection.execute(f"create schema if not exists {RAW_SCHEMA}")
    # `union_by_name` so parts written by different runs line up on column names
    # rather than position, matching the Postgres path above.
    glob = str(parts[0].parent / "*.parquet")
    connection.execute(
        f"create or replace table {RAW_SCHEMA}.{table} as "
        f"select * from read_parquet('{glob}', union_by_name = true)"
    )
    count = connection.execute(f"select count(*) from {RAW_SCHEMA}.{table}").fetchone()[0]
    connection.close()
    return int(count)


def load_all(target: str | None = None) -> dict[str, int]:
    target = target or os.environ.get("LOAD_TARGET", "postgres")
    write = {"postgres": _write_postgres, "duckdb": _write_duckdb}.get(target)
    if not write:
        raise ValueError(f"unknown LOAD_TARGET {target!r} (duckdb | postgres)")

    counts: dict[str, int] = {}
    for table, dataset in DATASETS.items():
        parts = _parts(dataset)
        if not parts:
            # A source that has not been extracted yet is not an error — the
            # Census layer in particular needs a key the warehouse can be built
            # without.
            log.info("%s: nothing landed at data/raw/%s — skipped", table, dataset)
            continue

        counts[table] = write(table, parts)
        log.info("%s: %s rows from %d file(s)", table, f"{counts[table]:,}", len(parts))

    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except ImportError:  # pragma: no cover — python-dotenv ships with the project
        pass
    load_all()


if __name__ == "__main__":
    main()
