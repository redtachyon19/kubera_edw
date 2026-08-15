"""Run the warehouse's Postgres locally, without Docker and without an admin password.

The warehouse used to be a hosted Neon instance. It is now a Postgres cluster
that lives in this repo, under `data/pgdata`, started and stopped by this
script. Nothing about the *schema* changed with the move — dbt still builds the
same `raw` → `staging` → `intermediate` → `marts` chain against a stock
PostgreSQL 16, which is the point: the same models run unchanged against a
managed server later, and the SQL stays plain enough to lift into Snowflake or
Databricks after that.

**Where the server comes from.** There is no system Postgres here, no Homebrew
and no Docker, and installing any of the three needs a password this script
should not be asking for. `pgserver` ships an actual PostgreSQL 16 build as a
Python wheel, so the binaries are already sitting in the virtualenv. This starts
them the ordinary way — `pg_ctl` against a data directory — rather than going
through `pgserver`'s own supervisor, because that supervisor only listens on a
Unix socket and stops the server when the Python process that asked for it
exits. Both are wrong here: dbt, SQLAlchemy, Dagster and Metabase are separate
processes that each expect a host and a port, and the warehouse has to outlive
whichever of them started it.

    python scripts/local_postgres.py start | stop | status | psql

`docker-compose.yml` still defines an equivalent `warehouse` service. If Docker
ever appears on this machine, that path works with no change to dbt or the hub —
both read the same `POSTGRES_*` variables.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PGDATA = REPO_ROOT / "data" / "pgdata"

# Server-side logging goes next to the cluster rather than to the terminal that
# happened to start it — `start` returns immediately and the log has to outlive
# it. This is the first place to look when a start fails.
LOG_PATH = DEFAULT_PGDATA / "server.log"

# initdb makes the bootstrap superuser; every other role is created against it.
# `postgres` is what pgserver's own initdb uses, so an existing cluster already
# has it and this stays consistent with one.
SUPERUSER = "postgres"


def _load_env() -> None:
    """Read `.env` the same way every other entry point in the repo does."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover — python-dotenv ships with the project
        return
    load_dotenv(REPO_ROOT / ".env")


def bin_dir() -> Path:
    """The PostgreSQL binaries bundled into the virtualenv by `pgserver`."""
    try:
        import pgserver
    except ImportError as exc:  # pragma: no cover — listed in requirements.txt
        raise SystemExit(
            "pgserver is not installed — run `make setup`, or `.venv/bin/pip install pgserver`."
        ) from exc

    path = Path(pgserver.__file__).parent / "pginstall" / "bin"
    if not (path / "pg_ctl").exists():
        raise SystemExit(f"pgserver is installed but has no binaries at {path}")
    return path


def pgdata() -> Path:
    configured = os.environ.get("PGDATA_DIR")
    return Path(configured) if configured else DEFAULT_PGDATA


def port() -> str:
    return os.environ.get("POSTGRES_PORT", "5432")


def _run(
    program: str, *args: str, check: bool = True, quiet: bool = False
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(bin_dir() / program), *args],
        check=check,
        capture_output=quiet,
        text=True,
    )


def _initialised() -> bool:
    return (pgdata() / "PG_VERSION").exists()


def _running() -> bool:
    result = _run("pg_ctl", "-D", str(pgdata()), "status", check=False, quiet=True)
    return result.returncode == 0


def _sql(statement: str, *, database: str = "postgres") -> str:
    """Run one statement as the superuser and hand back stdout.

    Deliberately not parameterised: the only values interpolated by callers are
    role and database names read from `.env`, which Postgres cannot parameterise
    in DDL anyway. Nothing here is reachable from a request.
    """
    result = _run(
        "psql",
        "-h",
        "localhost",
        "-p",
        port(),
        "-U",
        SUPERUSER,
        "-d",
        database,
        "-tAc",
        statement,
        quiet=True,
    )
    return result.stdout.strip()


def _ensure_role_and_database() -> None:
    """Make the `.env` role and database exist, idempotently.

    A cluster initialised here has only the bootstrap superuser and its own
    database. The rest of the repo authenticates as `POSTGRES_USER` against
    `POSTGRES_DB`, so those are created on first start and left alone after.
    """
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    database = os.environ.get("POSTGRES_DB")

    if not user or not database:
        raise SystemExit("POSTGRES_USER and POSTGRES_DB must be set in .env")

    if user != SUPERUSER:
        exists = _sql(f"select 1 from pg_roles where rolname = '{user}'")
        if not exists:
            # SUPERUSER rather than CREATEDB: dbt creates schemas, and the raw
            # loader creates them too. This is a local single-tenant warehouse,
            # not a shared server where that would be worth constraining.
            escaped = password.replace("'", "''")
            _sql(f"create role \"{user}\" with login superuser password '{escaped}'")
            print(f"    created role {user}")

    exists = _sql(f"select 1 from pg_database where datname = '{database}'")
    if not exists:
        _sql(f'create database "{database}" owner "{user}"')
        print(f"    created database {database}")


def start() -> None:
    data = pgdata()

    if not _initialised():
        print(f"==> initdb {data}")
        data.mkdir(parents=True, exist_ok=True)
        _run(
            "initdb",
            "-D",
            str(data),
            "-U",
            SUPERUSER,
            "--encoding=UTF8",
            # A deterministic collation keeps ORDER BY identical to what the
            # same models produce on a server elsewhere. The default follows
            # whatever LANG the shell happens to carry.
            "--locale=C",
        )

    if _running():
        print(f"    already running on localhost:{port()}")
        return

    print(f"==> starting postgres on localhost:{port()}")
    _run(
        "pg_ctl",
        "-D",
        str(data),
        "-l",
        str(LOG_PATH),
        # Bound to loopback. This is a developer warehouse holding no secrets
        # worth reaching over a network, and opening it to the LAN would be a
        # decision, not a default.
        "-o",
        f"-h localhost -p {port()}",
        "-w",
        "start",
    )

    _ensure_role_and_database()
    print(f"    ready — log at {LOG_PATH}")


def stop() -> None:
    if not _running():
        print("    not running")
        return
    # `fast` rolls back open transactions and shuts down rather than waiting for
    # clients to disconnect; a hub or a Dagster daemon holding a pooled
    # connection would otherwise keep the server up indefinitely.
    _run("pg_ctl", "-D", str(pgdata()), "-m", "fast", "-w", "stop")
    print("    stopped")


def status() -> None:
    if not _initialised():
        print(f"    no cluster at {pgdata()} — run `make db-up`")
        return
    if not _running():
        print(f"    cluster at {pgdata()} is stopped")
        return

    database = os.environ.get("POSTGRES_DB", "postgres")
    size = _sql(f"select pg_size_pretty(pg_database_size('{database}'))")
    print(f"    running on localhost:{port()} · {database} · {size}")


def psql() -> None:
    """An interactive shell on the warehouse, as the application role."""
    os.execv(
        str(bin_dir() / "psql"),
        [
            "psql",
            "-h",
            "localhost",
            "-p",
            port(),
            "-U",
            os.environ.get("POSTGRES_USER", SUPERUSER),
            "-d",
            os.environ.get("POSTGRES_DB", "postgres"),
        ],
    )


COMMANDS = {"start": start, "stop": stop, "status": status, "psql": psql}


def main() -> None:
    _load_env()
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    action = COMMANDS.get(command)
    if not action:
        raise SystemExit(f"usage: {Path(__file__).name} [{' | '.join(COMMANDS)}]")
    action()


if __name__ == "__main__":
    main()
