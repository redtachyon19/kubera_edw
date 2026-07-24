# scripts/

Automation for setting up and checking the local environment. No admin password required.

| Script | What it does |
|---|---|
| [`bootstrap.sh`](bootstrap.sh) | One-command setup: installs `uv` (user-space), a managed **Python 3.12**, the `.venv`, all dependencies, seeds `.env`, then runs `verify.sh`. Idempotent — safe to re-run. |
| [`verify.sh`](verify.sh) | The "green gate": checks Python version, dependency integrity (`pip check`), lint (`ruff`), tests (`pytest`), and the dbt DuckDB connection (`dbt debug`). Docker is optional (needed only from Phase 6). |

## Usage

```bash
bash scripts/bootstrap.sh      # first-time setup (or to repair the env)
source .venv/bin/activate      # then activate the venv for your shell
bash scripts/verify.sh         # re-check the environment any time
```

## Notes

- **Python** is provisioned via [`uv`](https://docs.astral.sh/uv/); nothing is installed system-wide and no `sudo` is used.
- **API keys** (`FRED_API_KEY`, `ALPHA_VANTAGE_API_KEY`) are only required for Phase 1 (extraction). Fill them into `.env` when you get there.
- **Docker** is not required for the local DuckDB critical path (Phases 0–5). Install Docker Desktop before Phase 6 (orchestration / the Postgres container).
