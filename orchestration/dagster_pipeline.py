"""Dagster pipeline for Kubera_EDW (Phase 6).

Wires the phases into a scheduled, monitored job:
    extract (ingestion clients) -> land raw -> dbt build (staging -> marts) -> dbt test

Run locally:
    dagster dev -f orchestration/dagster_pipeline.py

TODO: flesh out assets once the ingestion clients and dbt models are implemented. The skeleton
below shows the intended asset graph and a daily schedule.
"""

# NOTE: deliberately no `from __future__ import annotations` here. Dagster resolves the
# `context` parameter's annotation at runtime; PEP 563 would turn it into a string and the
# @asset decorator would reject it.
from dagster import (
    AssetExecutionContext,
    Definitions,
    ScheduleDefinition,
    asset,
    define_asset_job,
)


# --- Extraction assets (one per source; each lands raw under data/raw/) ------------------
@asset(group_name="extract")
def sec_edgar_facts(context: AssetExecutionContext) -> None:
    """Extract SEC EDGAR company facts for the coverage universe."""
    context.log.info("TODO: SecEdgarClient — resolve CIKs, land company facts.")


@asset(group_name="extract")
def world_bank_macro(context: AssetExecutionContext) -> None:
    context.log.info("TODO: WorldBankClient — land macro indicators.")


@asset(group_name="extract")
def fx_rates(context: AssetExecutionContext) -> None:
    context.log.info("TODO: FxClient — land daily FX time series.")


@asset(group_name="extract")
def gold_prices(context: AssetExecutionContext) -> None:
    context.log.info("TODO: GoldPriceClient — land LBMA gold fixing series.")


@asset(group_name="extract")
def market_prices(context: AssetExecutionContext) -> None:
    context.log.info("TODO: PricesClient — land daily prices (Stooq/Alpha Vantage).")


# --- Transformation asset (dbt build over all landed sources) ---------------------------
@asset(
    group_name="transform",
    deps=[sec_edgar_facts, world_bank_macro, fx_rates, gold_prices, market_prices],
)
def dbt_build(context: AssetExecutionContext) -> None:
    """Run `dbt build` (staging -> intermediate -> marts) + dbt tests.

    TODO: use dagster-dbt (@dbt_assets) to model each dbt node as a first-class asset instead
    of this single shell-out placeholder.
    """
    context.log.info("TODO: invoke dbt build --target dev")


# --- Job + daily schedule ---------------------------------------------------------------
kubera_job = define_asset_job(name="kubera_refresh", selection="*")

daily_schedule = ScheduleDefinition(
    job=kubera_job,
    cron_schedule="0 6 * * *",  # 06:00 daily
)

defs = Definitions(
    assets=[
        sec_edgar_facts,
        world_bank_macro,
        fx_rates,
        gold_prices,
        market_prices,
        dbt_build,
    ],
    jobs=[kubera_job],
    schedules=[daily_schedule],
)
