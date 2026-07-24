#!/usr/bin/env bash
#
# scripts/pipeline.sh — run the full pipeline: extract -> load -> transform -> test.
#
# Usage:
#   bash scripts/pipeline.sh                 # DuckDB (local, default)
#   bash scripts/pipeline.sh prod            # Neon / hosted Postgres
#   SKIP_EXTRACT=1 bash scripts/pipeline.sh  # reuse landed data, just reload + rebuild
#
# Extraction is cached: sources already landed today are not re-fetched.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET="${1:-dev}"
PY="$ROOT/.venv/bin/python"
DBT="$ROOT/.venv/bin/dbt"

case "$TARGET" in
  dev|ci) LOAD_TARGET=duckdb ;;
  prod)   LOAD_TARGET=postgres ;;
  *) echo "unknown target '$TARGET' (dev | ci | prod)" >&2; exit 2 ;;
esac
export LOAD_TARGET

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

step "2/4  Load raw -> ${LOAD_TARGET}"
"$PY" -m ingestion.load_raw

step "3/4  Transform (dbt build --target ${TARGET})"
( cd dbt && DBT_PROFILES_DIR=. "$DBT" build --target "$TARGET" )

step "4/4  Done"
echo "    Warehouse target: ${TARGET} (${LOAD_TARGET})"
