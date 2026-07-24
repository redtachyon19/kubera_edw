"""Tests for ingestion.world_bank_client."""

from __future__ import annotations

import pytest

from ingestion.world_bank_client import INDICATORS


def test_indicator_codes_present() -> None:
    assert INDICATORS["gdp"] == "NY.GDP.MKTP.CD"
    assert "cpi_inflation_pct" in INDICATORS


@pytest.mark.skip(reason="Phase 1: implement fetch_indicator, then assert row parsing.")
def test_fetch_indicator_parses_rows() -> None:
    ...
