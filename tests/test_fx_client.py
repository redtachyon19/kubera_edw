"""Tests for ingestion.fx_client."""

from __future__ import annotations

import pytest

from ingestion.fx_client import FxClient


def test_fx_client_defaults() -> None:
    client = FxClient()
    assert client.source_name == "fx"
    assert "frankfurter" in client.base_url
    client.close()


@pytest.mark.skip(reason="Phase 1: implement fetch_timeseries, then assert USD-base parsing.")
def test_fetch_timeseries(sample_fx_timeseries: dict) -> None:
    ...
