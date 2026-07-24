"""Tests for ingestion.world_bank_client."""

from __future__ import annotations

import json

import httpx
import respx

from ingestion.world_bank_client import INDICATORS, UNSUPPORTED_ISO3, WorldBankClient


def test_indicator_codes_present() -> None:
    assert INDICATORS["gdp"] == "NY.GDP.MKTP.CD"
    assert "cpi_inflation_pct" in INDICATORS


def test_fetch_indicator_parses_rows(sample_world_bank_response: list) -> None:
    with respx.mock:
        route = respx.get(url__startswith="https://api.worldbank.org/v2/country/").mock(
            return_value=httpx.Response(200, json=sample_world_bank_response)
        )
        with WorldBankClient() as client:
            rows = client.fetch_indicator(["USA", "GBR"], "gdp", start_year=2010, end_year=2023)

    assert route.called
    # Envelope element 1 holds the rows; element 0 is pagination metadata.
    assert len(rows) == 2
    assert {r["countryiso3code"] for r in rows} == {"USA", "GBR"}
    assert rows[0]["value"] == 27360935000000


def test_fetch_indicator_lands_with_load_provenance(sample_world_bank_response: list) -> None:
    # Macro figures get revised long after publication, so each load records when it happened
    # and lands under a date-stamped name rather than overwriting the prior version (§11).
    with respx.mock:
        respx.get(url__startswith="https://api.worldbank.org/v2/country/").mock(
            return_value=httpx.Response(200, json=sample_world_bank_response)
        )
        with WorldBankClient() as client:
            client.fetch_indicator(["USA"], "gdp", start_year=2010, end_year=2023)
            landed = sorted((client._land_path("x").parent).glob("gdp_*.json"))

    assert len(landed) == 1
    envelope = json.loads(landed[0].read_text())
    assert envelope["loaded_at"]
    assert envelope["indicator_code"] == "NY.GDP.MKTP.CD"
    assert len(envelope["data"]) == 2


def test_taiwan_is_skipped_not_fatal(sample_world_bank_response: list) -> None:
    # Taiwan has no World Bank coverage — a known Phase-0 gap that must not kill the run.
    assert "TWN" in UNSUPPORTED_ISO3
    with respx.mock:
        route = respx.get(url__startswith="https://api.worldbank.org/v2/country/").mock(
            return_value=httpx.Response(200, json=sample_world_bank_response)
        )
        with WorldBankClient() as client:
            rows = client.fetch_indicator(["USA", "TWN"], "gdp", start_year=2010, end_year=2023)

    assert rows  # still returns what it could fetch
    assert "TWN" not in str(route.calls[0].request.url)


def test_all_countries_unsupported_returns_empty() -> None:
    with respx.mock as mock:
        with WorldBankClient() as client:
            rows = client.fetch_indicator(["TWN"], "gdp", start_year=2010, end_year=2023)
    assert rows == []
    assert not mock.calls  # nothing to fetch means no request at all
