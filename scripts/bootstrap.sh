#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { printf "\n\033[1;34m==>\033[0m \033[1m%s\033[0m\n" "$*"; }
ok()   { printf "    \033[32m✓\033[0m %s\n" "$*"; }
note() { printf "    \033[33m•\033[0m %s\n" "$*"; }

step "1/5  Ensuring uv is installed (user-space Python & package manager)"
if command -v uv >/dev/null 2>&1; then
  ok "uv already installed ($(uv --version))"
else
  note "uv not found — installing from https://astral.sh/uv (no admin password needed)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
command -v uv >/dev/null 2>&1 || { echo "ERROR: uv install failed — see output above." >&2; exit 1; }
ok "uv ready ($(uv --version))"

step "2/5  Installing Python 3.12 and creating .venv"
uv python install 3.12
uv venv --python 3.12 .venv
export VIRTUAL_ENV="$ROOT/.venv"
export PATH="$ROOT/.venv/bin:$PATH"
ok "venv ready ($("$ROOT/.venv/bin/python" --version))"

step "3/5  Installing dependencies (first run pulls dbt, dagster, etc. — a few minutes)"
uv pip install --python "$ROOT/.venv/bin/python" --upgrade pip
uv pip install --python "$ROOT/.venv/bin/python" -r requirements.txt
ok "dependencies installed"

step "4/5  Preparing .env"
if [ -f .env ]; then
  ok ".env already exists — leaving it untouched"
else
  cp .env.example .env
  duckdb_abs="$ROOT/data/kubera_edw.duckdb"
  sed -i.bak "s|^DUCKDB_PATH=.*|DUCKDB_PATH=$duckdb_abs|" .env && rm -f .env.bak
  ok "created .env from .env.example (DUCKDB_PATH pinned to $duckdb_abs)"
fi
if grep -Eq "your_fred_key_here|your_alpha_vantage_key_here" .env 2>/dev/null; then
  note "API keys still needed in .env: FRED_API_KEY, ALPHA_VANTAGE_API_KEY"
  note "(only required for Phase 1 extraction — the rest of the pipeline runs without them)"
fi

step "5/5  Verifying the environment"
if bash scripts/verify.sh; then
  VERIFY_RC=0
else
  VERIFY_RC=$?
  note "Some verification checks did not pass (see above). Setup itself completed."
fi

step "Bootstrap complete"
ok "Activate the venv:   source .venv/bin/activate"
note "Fill the two API keys in .env when you reach Phase 1 (extraction)."
note "Install Docker Desktop before Phase 6 (orchestration / Postgres container)."
exit "${VERIFY_RC:-0}"
