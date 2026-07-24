"""Tests for ingestion.sec_edgar_client."""

from __future__ import annotations

import pytest

from ingestion.sec_edgar_client import CONCEPT_TAG_MAP, SecEdgarClient


def test_concept_tag_map_has_core_concepts() -> None:
    # Sanity check on the concept → XBRL tag mapping that staging relies on.
    assert "revenue" in CONCEPT_TAG_MAP
    assert CONCEPT_TAG_MAP["net_income"][0] == "NetIncomeLoss"


def test_missing_user_agent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # SEC requires a User-Agent — constructing the client without one must fail loudly.
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SEC_EDGAR_USER_AGENT"):
        SecEdgarClient()


@pytest.mark.skip(reason="Phase 1: implement fetch_company_facts, then assert parsing.")
def test_parse_company_facts(sample_sec_company_facts: dict) -> None:
    ...
