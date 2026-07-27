#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"

pass() { printf "  \033[32m✓\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$*"; FAILED=1; }
skip() { printf "  \033[33m•\033[0m %s\n" "$*"; }
FAILED=0

printf "\033[1mKubera_EDW environment verification\033[0m\n"

if [ ! -x "$PY" ]; then
  fail "no .venv found — run: bash scripts/bootstrap.sh"
  exit 1
fi

if "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 12) else 1)'; then
  pass "python $("$PY" --version | awk '{print $2}') (>= 3.12)"
else
  fail "python < 3.12"
fi

if "$PY" -m pip check >/dev/null 2>&1; then
  pass "pip check — no broken requirements"
else
  fail "pip check found broken requirements (run: .venv/bin/python -m pip check)"
fi

if "$ROOT/.venv/bin/ruff" check . >/dev/null 2>&1; then
  pass "ruff check — clean"
else
  fail "ruff check — issues (run: .venv/bin/ruff check .)"
fi

if "$ROOT/.venv/bin/pytest" tests/ -q >/tmp/kubera_pytest.log 2>&1; then
  pass "pytest — $(grep -Eo '[0-9]+ passed([,0-9a-z ]*skipped)?' /tmp/kubera_pytest.log | tail -1)"
else
  fail "pytest — failures (run: .venv/bin/pytest tests/ -v)"
fi

if ( cd dbt && DBT_PROFILES_DIR=. "$ROOT/.venv/bin/dbt" debug --target dev >/tmp/kubera_dbt.log 2>&1 ); then
  pass "dbt debug --target dev — connection OK (DuckDB)"
else
  fail "dbt debug --target dev — failed (see /tmp/kubera_dbt.log)"
fi

if command -v docker >/dev/null 2>&1; then
  if docker compose config -q >/dev/null 2>&1; then
    pass "docker compose config — valid"
  else
    fail "docker compose config — invalid"
  fi
else
  skip "docker absent — OK for now (needed for Phase 6 orchestration / Postgres)"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  printf "\033[1;32mAll checks passed.\033[0m\n"
else
  printf "\033[1;33mSome checks did not pass (see ✗ above).\033[0m\n"
fi
exit "$FAILED"
