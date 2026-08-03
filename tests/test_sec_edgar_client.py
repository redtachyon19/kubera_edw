from __future__ import annotations

import json

import httpx
import pytest
import respx

from ingestion.sec_edgar_client import CONCEPT_TAG_MAP, XBRL_NAMESPACES, SecEdgarClient


def test_concept_tag_map_has_core_concepts() -> None:
    assert "revenue" in CONCEPT_TAG_MAP
    assert CONCEPT_TAG_MAP["net_income"][0] == "NetIncomeLoss"


def test_concept_map_covers_ifrs_for_foreign_filers() -> None:
    assert XBRL_NAMESPACES == ("us-gaap", "ifrs-full")
    assert "Revenue" in CONCEPT_TAG_MAP["revenue"]
    assert "ProfitLoss" in CONCEPT_TAG_MAP["net_income"]
    assert "ProfitLossFromOperatingActivities" in CONCEPT_TAG_MAP["operating_income"]
    assert "CostOfSales" in CONCEPT_TAG_MAP["cost_of_revenue"]


def test_missing_user_agent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SEC_EDGAR_USER_AGENT"):
        SecEdgarClient()


def test_parse_company_facts(sample_sec_company_facts: dict) -> None:
    with respx.mock:
        route = respx.get(url__startswith="https://data.sec.gov/api/xbrl/companyfacts/").mock(
            return_value=httpx.Response(200, json=sample_sec_company_facts)
        )
        with SecEdgarClient() as client:
            payload = client.fetch_company_facts("0000320193")
            landed = client._land_path("companyfacts_CIK0000320193")

    assert route.called
    assert payload["entityName"] == "Apple Inc."
    fact = payload["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]
    assert fact["val"] == 383285000000
    assert fact["form"] == "10-K"
    assert landed.exists()
    assert json.loads(landed.read_text()) == sample_sec_company_facts


def test_fetch_company_facts_zero_pads_cik(sample_sec_company_facts: dict) -> None:
    with respx.mock:
        route = respx.get(url__startswith="https://data.sec.gov/api/xbrl/companyfacts/").mock(
            return_value=httpx.Response(200, json=sample_sec_company_facts)
        )
        with SecEdgarClient() as client:
            client.fetch_company_facts("320193")

    assert "CIK0000320193.json" in str(route.calls[0].request.url)


def test_resolve_cik_zero_pads(sample_sec_ticker_map: dict) -> None:
    with respx.mock:
        respx.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json=sample_sec_ticker_map)
        )
        with SecEdgarClient() as client:
            assert client.resolve_cik("AAPL") == "0000320193"
            assert client.resolve_cik("msft") == "0000789019"


def test_resolve_cik_raises_on_miss(sample_sec_ticker_map: dict) -> None:
    with respx.mock:
        respx.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json=sample_sec_ticker_map)
        )
        with SecEdgarClient() as client, pytest.raises(LookupError, match="NOSUCH"):
            client.resolve_cik("NOSUCH")


def test_cik_for_company_prefers_pinned_value(sample_sec_ticker_map: dict) -> None:
    with respx.mock:
        ticker_route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json=sample_sec_ticker_map)
        )
        with SecEdgarClient() as client:
            cik = client.cik_for_company({"ticker": "XOM", "cik": "0000034088"})

    assert cik == "0000034088"
    assert not ticker_route.called


def test_concept_frame_falls_back_across_namespaces() -> None:
    rows = {"data": [{"cik": 901832, "val": 1000}]}
    with respx.mock:
        respx.get(url__startswith="https://data.sec.gov/api/xbrl/frames/us-gaap/").mock(
            return_value=httpx.Response(404)
        )
        respx.get(url__startswith="https://data.sec.gov/api/xbrl/frames/ifrs-full/").mock(
            return_value=httpx.Response(200, json=rows)
        )
        with SecEdgarClient() as client:
            payload = client.fetch_concept_frame("revenue", "CY2023Q4")

    assert payload["data"][0]["val"] == 1000


def test_concept_frame_unknown_concept_raises() -> None:
    with SecEdgarClient() as client, pytest.raises(KeyError, match="unknown concept"):
        client.fetch_concept_frame("not_a_concept", "CY2023Q4")
