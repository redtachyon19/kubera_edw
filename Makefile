.DEFAULT_GOAL := help
SHELL := /bin/bash
VENV  := .venv/bin
DBT   := DBT_PROFILES_DIR=. ../$(VENV)/dbt

.PHONY: help setup demo pipeline prod hub hub-dashboards orchestrate test lint verify screenshots universe company-universe backfill clean

help:  ## Show this help
	@echo "Kubera_EDW"
	@echo ""
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  First time:  make setup && make demo && make hub"

setup:  ## Install uv, Python 3.12, the venv and all dependencies (no admin password)
	bash scripts/bootstrap.sh

demo:  ## Build the warehouse from committed fixtures — NO API keys, NO network
	@echo "==> Building from committed CI fixtures (offline)"
	cd dbt && $(DBT) deps -q && $(DBT) seed --target ci && $(DBT) build --target ci
	@echo ""
	@echo "    Warehouse built at dbt/target/ci.duckdb with no external calls."
	@echo "    For live data: add keys to .env, then 'make pipeline'."

pipeline:  ## Full live pipeline into the local DuckDB warehouse (needs .env keys)
	bash scripts/pipeline.sh dev

prod:  ## Full live pipeline into hosted Postgres / Neon (needs .env credentials)
	bash scripts/pipeline.sh prod

hub:  ## Serve the research terminal at http://localhost:5173 (hub + every dashboard)
	cd dashboard_hub/hub && npm install --no-audit --no-fund && npm run dev

hub-dashboards:  ## Run only the Streamlit dashboards the hub embeds (no hub UI)
	$(VENV)/python dashboard_hub/run_local.py

orchestrate:  ## Serve the Dagster UI at http://localhost:3000
	DAGSTER_HOME=$(PWD)/dagster_home $(VENV)/dagster dev -f orchestration/dagster_pipeline.py

test:  ## Run the Python suite and every dbt test
	$(VENV)/pytest tests/ -q
	cd dbt && $(DBT) build --target dev

lint:  ## Lint and format-check
	$(VENV)/ruff check .
	$(VENV)/ruff format --check .

verify:  ## Re-check the environment (python, deps, lint, tests, dbt connection)
	bash scripts/verify.sh

universe:  ## Re-verify every company against SEC EDGAR before changing companies.yml
	$(VENV)/python scripts/verify_universe.py

company-universe:  ## Rebuild dashboard_hub/companies.json after editing sectors.json
	$(VENV)/python scripts/generate_company_universe.py

backfill:  ## Add a company to the warehouse: make backfill TICKER=NVDA (or drain the queue)
	$(VENV)/python -m ingestion.backfill $(TICKER)

screenshots:  ## Re-render the README charts from the live warehouse
	$(VENV)/python scripts/generate_screenshots.py

clean:  ## Remove build artefacts (keeps landed raw data and the venv)
	rm -rf dbt/target dbt/dbt_packages dbt/logs .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "    cleaned (data/raw and .venv untouched)"
