import logging
import os
import shutil
import sys
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetOut,
    Backoff,
    DefaultScheduleStatus,
    Definitions,
    MetadataValue,
    Output,
    RetryPolicy,
    RunFailureSensorContext,
    ScheduleDefinition,
    asset,
    define_asset_job,
    multi_asset,
    run_failure_sensor,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from ingestion import (
    fx_client,
    generate_seeds,
    gold_price_client,
    imf_client,
    load_raw,
    prices_client,
    sec_edgar_client,
    world_bank_client,
)
from ingestion.config_loader import load_env

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = REPO_ROOT / "dbt"

RAW_TABLES = [
    "sec_edgar_facts",
    "world_bank_macro",
    "fx_rates",
    "gold_prices",
    "market_prices",
    "imf_macro",
]

NETWORK_RETRY = RetryPolicy(max_retries=3, delay=30, backoff=Backoff.EXPONENTIAL)

load_env()


def _dbt_executable() -> str:
    candidate = Path(sys.executable).parent / "dbt"
    if candidate.exists():
        return str(candidate)
    return shutil.which("dbt") or "dbt"


dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR)
dbt_project.prepare_if_dev()


def _run_extractor(context: AssetExecutionContext, module, source_name: str) -> dict:
    from ingestion.base_client import raw_root

    try:
        module.main()
        status = "ok"
    except RuntimeError as exc:
        context.log.warning("%s unavailable: %s", source_name, exc)
        status = f"skipped: {exc}"

    landing_dir = raw_root() / source_name
    landed = sorted(landing_dir.glob("*")) if landing_dir.exists() else []
    total_bytes = sum(f.stat().st_size for f in landed)
    context.add_output_metadata(
        {
            "status": MetadataValue.text(status),
            "files_landed": MetadataValue.int(len(landed)),
            "bytes_landed": MetadataValue.int(total_bytes),
            "landing_dir": MetadataValue.path(str(landing_dir)),
        }
    )
    return {"status": status, "files": len(landed)}


@asset(group_name="extract", retry_policy=NETWORK_RETRY, compute_kind="python")
def sec_edgar_source(context: AssetExecutionContext) -> None:
    """SEC EDGAR companyfacts for every company in the coverage universe."""
    _run_extractor(context, sec_edgar_client, "sec_edgar")


@asset(group_name="extract", retry_policy=NETWORK_RETRY, compute_kind="python")
def world_bank_source(context: AssetExecutionContext) -> None:
    """World Bank country-year macro indicators."""
    _run_extractor(context, world_bank_client, "world_bank")


@asset(group_name="extract", retry_policy=NETWORK_RETRY, compute_kind="python")
def fx_source(context: AssetExecutionContext) -> None:
    """Daily USD-base FX rates from Frankfurter."""
    _run_extractor(context, fx_client, "fx")


@asset(group_name="extract", retry_policy=NETWORK_RETRY, compute_kind="python")
def imf_source(context: AssetExecutionContext) -> None:
    """IMF DataMapper indicators — a cross-check on World Bank, never the primary source."""
    _run_extractor(context, imf_client, "imf")


@asset(group_name="extract", retry_policy=NETWORK_RETRY, compute_kind="python")
def gold_price_source(context: AssetExecutionContext) -> None:
    """LBMA gold fixing from FRED. Requires FRED_API_KEY."""
    _run_extractor(context, gold_price_client, "gold_price")


@asset(group_name="extract", retry_policy=NETWORK_RETRY, compute_kind="python")
def market_price_source(context: AssetExecutionContext) -> None:
    """Daily prices. Requires ALPHA_VANTAGE_API_KEY (Stooq is bot-gated)."""
    _run_extractor(context, prices_client, "prices")


@asset(group_name="load", compute_kind="python")
def dbt_seed_files(context: AssetExecutionContext) -> None:
    """Regenerate dbt seeds from companies.yml so the universe stays single-sourced."""
    path = generate_seeds.write_seed()
    context.add_output_metadata(
        {
            "seed_path": MetadataValue.path(str(path)),
            "companies": MetadataValue.int(len(generate_seeds.build_rows())),
        }
    )


@multi_asset(
    outs={name: AssetOut(key=AssetKey(name), is_required=False) for name in RAW_TABLES},
    deps=[
        sec_edgar_source,
        world_bank_source,
        fx_source,
        imf_source,
        gold_price_source,
        market_price_source,
        dbt_seed_files,
    ],
    group_name="load",
    compute_kind="python",
)
def raw_tables(context: AssetExecutionContext):
    """Parse landed files into the warehouse `raw` schema — the EL step dbt does not do.

    Emits one asset per raw table so the dbt sources reading them have real upstream lineage.
    """
    counts = load_raw.load_all()
    context.log.info("loaded %s", {k: v for k, v in counts.items() if v})

    for table in RAW_TABLES:
        rows = counts.get(table, 0)
        if not rows:
            context.log.warning("%s: 0 rows (source blocked or empty)", table)
        yield Output(
            value=None,
            output_name=table,
            metadata={
                "rows": MetadataValue.int(rows),
                "status": MetadataValue.text("loaded" if rows else "empty"),
            },
        )


class KuberaDbtTranslator(DagsterDbtTranslator):
    def get_asset_key(self, dbt_resource_props):
        if dbt_resource_props["resource_type"] == "source":
            return AssetKey(dbt_resource_props["name"])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=KuberaDbtTranslator(),
)
def kubera_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()


@run_failure_sensor(description="Log details of any failed run for alerting/triage.")
def kubera_run_failure_sensor(context: RunFailureSensorContext):
    run = context.dagster_run
    logging.getLogger(__name__).error(
        "Dagster run FAILED — job=%s run_id=%s reason=%s",
        run.job_name,
        run.run_id,
        context.failure_event.message,
    )


kubera_job = define_asset_job(
    name="kubera_refresh",
    selection="*",
    description="Full refresh: extract every source, load raw, then build and test the warehouse.",
)

daily_schedule = ScheduleDefinition(
    job=kubera_job,
    cron_schedule="0 6 * * *",
    default_status=DefaultScheduleStatus.STOPPED,
    description="Daily warehouse refresh.",
)

defs = Definitions(
    assets=[
        sec_edgar_source,
        world_bank_source,
        fx_source,
        imf_source,
        gold_price_source,
        market_price_source,
        dbt_seed_files,
        raw_tables,
        kubera_dbt_assets,
    ],
    jobs=[kubera_job],
    schedules=[daily_schedule],
    sensors=[kubera_run_failure_sensor],
    resources={
        "dbt": DbtCliResource(
            project_dir=dbt_project,
            profiles_dir=DBT_DIR,
            dbt_executable=_dbt_executable(),
            target=os.environ.get("DBT_TARGET", "dev"),
        )
    },
)
