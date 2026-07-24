"""Malformed / degenerate API responses must not crash the pipeline.

Free public APIs return shapes the docs do not describe: an empty result envelope, a payload
missing the key you indexed, an error object with HTTP 200. A pipeline that raises on any of
these is one that stops overnight and needs a human. Each case below asserts the client either
degrades to an empty result or fails with a clear, specific error — never an IndexError or
KeyError from the middle of a parser.
"""

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


# -- client-level -----------------------------------------------------------
def test_world_bank_envelope_without_rows_returns_empty() -> None:
    # A query matching nothing yields [metadata] alone, or [metadata, null] — indexing
    # blindly into element 1 would raise.
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
    # An HTML error page served with HTTP 200 must surface as a decode error, not be
    # mistaken for data.
    with respx.mock:
        respx.get(url__startswith="https://api.frankfurter.dev/v1/2023-01-02").mock(
            return_value=httpx.Response(200, text="<html>502 Bad Gateway</html>")
        )
        with FxClient() as client, pytest.raises(json.JSONDecodeError):
            client.fetch_timeseries("USD", ["GBP"], "2023-01-02", "2023-01-03")


# -- loader-level -----------------------------------------------------------
def test_loader_parsers_survive_degenerate_landed_files() -> None:
    """Landed files that are structurally valid JSON but semantically empty."""
    _write("sec_edgar/companyfacts_CIK0000320193.json", {"cik": 320193})       # no facts
    _write("world_bank/gdp_20260724.json", {"indicator": "gdp",
                                           "indicator_code": "NY.GDP.MKTP.CD",
                                           "data": None})                      # null rows
    _write("fx/timeseries_USD_a_b.json", {"base": "USD"})                       # no rates
    _write("imf/gdp_growth_pct_NGDP_RPCH.json", {})                             # no values

    assert parse_sec_facts().empty
    assert parse_world_bank().empty
    assert parse_fx().empty
    assert parse_imf().empty


def test_loader_skips_unreadable_shape_without_partial_rows() -> None:
    # A companyfacts whose units block is empty must contribute zero rows rather than a row
    # of nulls that would look like a real reported fact downstream.
    _write(
        "sec_edgar/companyfacts_CIK0000320193.json",
        {"cik": 320193, "entityName": "Apple Inc.",
         "facts": {"us-gaap": {"Revenues": {"units": {}}}}},
    )
    assert parse_sec_facts().empty
