"""Tests for ingestion.gold_price_client."""

from __future__ import annotations

import pytest

from ingestion.gold_price_client import GOLD_SERIES_ID, GoldPriceClient


def test_gold_series_id() -> None:
    assert GOLD_SERIES_ID == "GOLDAMGBD228NLBM"


def test_missing_fred_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FRED_API_KEY"):
        GoldPriceClient().fetch_gold_series()


@pytest.mark.skip(reason="Phase 1: implement fetch_gold_series, then assert observation parsing.")
def test_fetch_gold_series() -> None:
    ...
