#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then set -a; . ./.env; set +a; fi

TARGET="${1:-dev}"
PY="$ROOT/.venv/bin/python"
DBT="$ROOT/.venv/bin/dbt"

# `ci` is the offline fixture build and the only DuckDB target left; dev and
# prod are both Postgres and differ only in which server POSTGRES_HOST names.
case "$TARGET" in
  ci)        LOAD_TARGET=duckdb ;;
  dev|prod)  LOAD_TARGET=postgres ;;
  *) echo "unknown target '$TARGET' (dev | ci | prod)" >&2; exit 2 ;;
esac
export LOAD_TARGET

# A dev run against a server that is not up fails four steps later, inside dbt,
# with a connection error that reads like a credentials problem.
if [ "$TARGET" = "dev" ]; then
  "$PY" scripts/local_postgres.py start
fi

step() { printf "\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n" "$*"; }

step "1/4  Extract (keyless sources; gold + prices need API keys)"
if [ "${SKIP_EXTRACT:-0}" = "1" ]; then
  echo "    skipped (SKIP_EXTRACT=1)"
else
  for m in sec_edgar_client world_bank_client fx_client imf_client; do
    "$PY" -m "ingestion.$m" 2>&1 | grep -vE 'HTTP Request' | tail -2 || true
  done
  for m in gold_price_client prices_client; do
    "$PY" -m "ingestion.$m" 2>&1 | grep -vE 'HTTP Request' | tail -2 \
      || echo "    ($m unavailable — API key not set)"
  done
fi

step "2/4  Regenerate dbt seeds from companies.yml, then load raw -> ${LOAD_TARGET}"
"$PY" -m ingestion.generate_seeds
"$PY" -m ingestion.load_raw

step "3/4  Transform (dbt build --target ${TARGET})"
( cd dbt && DBT_PROFILES_DIR=. "$DBT" deps -q && DBT_PROFILES_DIR=. "$DBT" seed --target "$TARGET"   && DBT_PROFILES_DIR=. "$DBT" build --target "$TARGET" )

step "4/4  Done"
echo "    Warehouse target: ${TARGET} (${LOAD_TARGET})"
