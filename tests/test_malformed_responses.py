from __future__ import annotations

import json

import httpx
import pytest
import respx

from ingestion.base_client import raw_root
from ingestion.fx_client import FxClient
from ingestion.gold_price_client import GoldPriceClient
from ingestion.load_raw import parse_fx, parse_imf, parse_sec_facts, parse_world_bank
from ingestion.sec_edgar_client import SecEdgarClient
from ingestion.world_bank_client import WorldBankClient


def _write(rel: str, payload: object) -> None:
    path = raw_root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)


def test_world_bank_envelope_without_rows_returns_empty() -> None:
    with respx.mock:
        respx.get(url__startswith="https://api.worldbank.org/v2/country/").mock(
            return_value=httpx.Response(200, json=[{"page": 1, "total": 0}])
        )
        with WorldBankClient() as client:
            assert client.fetch_indicator(["USA"], "gdp", start_year=2010, end_year=2023) == []


def test_world_bank_null_rows_returns_empty() -> None:
    with respx.mock:
        respx.get(url__startswith="https://api.worldbank.org/v2/country/").mock(
            return_value=httpx.Response(200, json=[{"page": 1}, None])
        )
        with WorldBankClient() as client:
            assert client.fetch_indicator(["USA"], "gdp", start_year=2010, end_year=2023) == []


def test_fx_response_without_rates_does_not_crash() -> None:
    with respx.mock:
        respx.get(url__startswith="https://api.frankfurter.dev/v1/2023-01-02").mock(
            return_value=httpx.Response(200, json={"base": "USD"})
        )
        with FxClient() as client:
            payload = client.fetch_timeseries("USD", ["GBP"], "2023-01-02", "2023-01-03")
    assert payload.get("rates", {}) == {}


def test_sec_companyfacts_without_facts_key_does_not_crash() -> None:
    with respx.mock:
        respx.get(url__startswith="https://data.sec.gov/api/xbrl/companyfacts/").mock(
            return_value=httpx.Response(200, json={"cik": 320193, "entityName": "Apple Inc."})
        )
        with SecEdgarClient() as client:
            payload = client.fetch_company_facts("0000320193")
    assert payload["entityName"] == "Apple Inc."


def test_gold_response_without_observations_does_not_crash() -> None:
    with respx.mock:
        respx.get(url__startswith="https://api.stlouisfed.org/fred/series/observations").mock(
            return_value=httpx.Response(200, json={"realtime_start": "2026-07-24"})
        )
        with GoldPriceClient() as client:
            payload = client.fetch_gold_series()
    assert payload.get("observations", []) == []


def test_non_json_body_raises_clearly() -> None:
    with respx.mock:
        respx.get(url__startswith="https://api.frankfurter.dev/v1/2023-01-02").mock(
            return_value=httpx.Response(200, text="<html>502 Bad Gateway</html>")
        )
        with FxClient() as client, pytest.raises(json.JSONDecodeError):
            client.fetch_timeseries("USD", ["GBP"], "2023-01-02", "2023-01-03")


def test_loader_parsers_survive_degenerate_landed_files() -> None:
    _write("sec_edgar/companyfacts_CIK0000320193.json", {"cik": 320193})
    _write(
        "world_bank/gdp_20260724.json",
        {"indicator": "gdp", "indicator_code": "NY.GDP.MKTP.CD", "data": None},
    )
    _write("fx/timeseries_USD_a_b.json", {"base": "USD"})
    _write("imf/gdp_growth_pct_NGDP_RPCH.json", {})

    assert parse_sec_facts().empty
    assert parse_world_bank().empty
    assert parse_fx().empty
    assert parse_imf().empty


def test_loader_skips_unreadable_shape_without_partial_rows() -> None:
    _write(
        "sec_edgar/companyfacts_CIK0000320193.json",
        {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {"us-gaap": {"Revenues": {"units": {}}}},
        },
    )
    assert parse_sec_facts().empty
