"""Tests for ingestion.gold_price_client."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from ingestion.gold_price_client import GOLD_SERIES_ID, GoldPriceClient


def test_gold_series_id() -> None:
    assert GOLD_SERIES_ID == "GOLDAMGBD228NLBM"


def test_missing_fred_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FRED_API_KEY"):
        GoldPriceClient().fetch_gold_series()


def test_fetch_gold_series(sample_fred_observations: dict) -> None:
    with respx.mock:
        route = respx.get(
            url__startswith="https://api.stlouisfed.org/fred/series/observations"
        ).mock(return_value=httpx.Response(200, json=sample_fred_observations))
        with GoldPriceClient() as client:
            payload = client.fetch_gold_series(start="2010-01-01")
            landed = client._land_path("gold_lbma_fixing")

    assert route.called
    request_url = str(route.calls[0].request.url)
    assert f"series_id={GOLD_SERIES_ID}" in request_url
    assert "file_type=json" in request_url

    observations = payload["observations"]
    assert len(observations) == 3
    assert observations[0] == {"date": "2023-01-03", "value": "1839.10"}
    # Landing is raw-as-is: FRED's "." missing marker is preserved for stg_gold__prices to
    # clean in Phase 2, not silently dropped at extraction time.
    assert observations[2]["value"] == "."
    assert json.loads(landed.read_text())["observations"][2]["value"] == "."
