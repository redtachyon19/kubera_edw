from __future__ import annotations

import json

import httpx
import respx

from ingestion.fx_client import FxClient


def test_fx_client_defaults() -> None:
    client = FxClient()
    assert client.source_name == "fx"
    assert "frankfurter" in client.base_url
    client.close()


def test_fetch_timeseries(sample_fx_timeseries: dict) -> None:
    with respx.mock:
        route = respx.get(url__startswith="https://api.frankfurter.dev/v1/2023-01-02").mock(
            return_value=httpx.Response(200, json=sample_fx_timeseries)
        )
        with FxClient() as client:
            payload = client.fetch_timeseries("USD", ["GBP", "JPY"], "2023-01-02", "2023-01-03")
            landed = client._land_path("timeseries_USD_2023-01-02_2023-01-03")

    assert route.called
    assert payload["base"] == "USD"
    assert payload["rates"]["2023-01-02"]["GBP"] == 0.827
    assert len(payload["rates"]) == 2
    assert json.loads(landed.read_text())["base"] == "USD"


def test_fetch_latest(sample_fx_timeseries: dict) -> None:
    latest = {"base": "USD", "date": "2023-01-03", "rates": {"GBP": 0.831}}
    with respx.mock:
        respx.get(url__startswith="https://api.frankfurter.dev/v1/latest").mock(
            return_value=httpx.Response(200, json=latest)
        )
        with FxClient() as client:
            payload = client.fetch_latest("USD", ["GBP"])
            assert client._land_path("latest_USD").exists()

    assert payload["rates"]["GBP"] == 0.831


def test_supported_currencies_excludes_twd() -> None:
    with respx.mock:
        respx.get("https://api.frankfurter.dev/v1/currencies").mock(
            return_value=httpx.Response(200, json={"GBP": "British Pound", "JPY": "Japanese Yen"})
        )
        with FxClient() as client:
            supported = client.supported_currencies()

    assert {"GBP", "JPY"} <= supported
    assert "TWD" not in supported
