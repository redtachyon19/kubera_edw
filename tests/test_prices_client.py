"""Tests for ingestion.prices_client (Alpha Vantage + Stooq backends)."""

from __future__ import annotations

import httpx
import pytest
import respx

from ingestion.prices_client import PricesClient

STOOQ_CHALLENGE = (
    "<!DOCTYPE html><html><body><noscript>This site requires JavaScript to verify your "
    'browser.</noscript><script>fetch("/__verify")</script></body></html>'
)


# -- Stooq ------------------------------------------------------------------
def test_stooq_lands_csv_not_json(sample_stooq_csv: str) -> None:
    # CSV must land verbatim as .csv — JSON-encoding the body would break the Phase-2
    # staging model that reads it with read_csv.
    with respx.mock:
        respx.get(url__startswith="https://stooq.com/q/d/l/").mock(
            return_value=httpx.Response(200, text=sample_stooq_csv)
        )
        with PricesClient() as client:
            text = client.fetch_daily_stooq("AAPL")
            landed = client._land_path("AAPL", "csv")
            json_path = client._land_path("AAPL", "json")

    assert text == sample_stooq_csv
    assert landed.exists() and not json_path.exists()
    assert landed.read_text().startswith("Date,Open,High,Low,Close")


def test_stooq_honors_cache_on_second_call(sample_stooq_csv: str) -> None:
    # Free-tier quotas make re-fetching unchanged data the main way to break a run.
    with respx.mock:
        route = respx.get(url__startswith="https://stooq.com/q/d/l/").mock(
            return_value=httpx.Response(200, text=sample_stooq_csv)
        )
        with PricesClient() as client:
            client.fetch_daily_stooq("AAPL")
            client.fetch_daily_stooq("AAPL")  # cached — must not hit the network
            assert route.call_count == 1

            client.fetch_daily_stooq("AAPL", force=True)  # explicit refresh still works
            assert route.call_count == 2


def test_stooq_detects_bot_challenge() -> None:
    # As of 2026-07 Stooq answers with a JS proof-of-work interstitial (HTTP 200, HTML body).
    # It must be reported clearly, never cached as if it were a price series.
    with respx.mock:
        respx.get(url__startswith="https://stooq.com/q/d/l/").mock(
            return_value=httpx.Response(200, text=STOOQ_CHALLENGE)
        )
        with PricesClient() as client:
            with pytest.raises(RuntimeError, match="bot-verification challenge"):
                client.fetch_daily_stooq("AAPL")
            assert not client._land_path("AAPL", "csv").exists()


def test_stooq_rejects_non_csv_body() -> None:
    with respx.mock:
        respx.get(url__startswith="https://stooq.com/q/d/l/").mock(
            return_value=httpx.Response(200, text="Exceeded the daily hits limit")
        )
        with PricesClient() as client:
            with pytest.raises(ValueError, match="no usable CSV"):
                client.fetch_daily_stooq("AAPL")
            assert not client._land_path("AAPL", "csv").exists()


# -- Alpha Vantage ----------------------------------------------------------
def test_alpha_vantage_uses_free_daily_endpoint() -> None:
    # TIME_SERIES_DAILY_ADJUSTED is premium-only; the default must stay on the free endpoint.
    payload = {"Time Series (Daily)": {"2023-01-03": {"4. close": "125.07"}}}
    with respx.mock:
        route = respx.get(url__startswith="https://www.alphavantage.co/query").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with PricesClient() as client:
            client.fetch_daily_alpha_vantage("AAPL")

    url = str(route.calls[0].request.url)
    assert "function=TIME_SERIES_DAILY&" in url or url.endswith("function=TIME_SERIES_DAILY")
    assert "TIME_SERIES_DAILY_ADJUSTED" not in url


def test_alpha_vantage_detects_rate_limit_note() -> None:
    # Alpha Vantage signals throttling with HTTP 200 + a "Note"/"Information" key.
    with respx.mock:
        respx.get(url__startswith="https://www.alphavantage.co/query").mock(
            return_value=httpx.Response(200, json={"Note": "call frequency limit reached"})
        )
        with PricesClient() as client:
            with pytest.raises(RuntimeError, match="Alpha Vantage Note"):
                client.fetch_daily_alpha_vantage("AAPL")
            assert not client._land_path("av_AAPL", "json").exists()


def test_alpha_vantage_detects_premium_information_response() -> None:
    # Requesting the premium adjusted endpoint on a free key returns "Information".
    with respx.mock:
        respx.get(url__startswith="https://www.alphavantage.co/query").mock(
            return_value=httpx.Response(200, json={"Information": "premium endpoint"})
        )
        with PricesClient() as client:
            with pytest.raises(RuntimeError, match="Alpha Vantage Information"):
                client.fetch_daily_alpha_vantage("AAPL", adjusted=True)


def test_alpha_vantage_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    with PricesClient() as client:
        with pytest.raises(RuntimeError, match="ALPHA_VANTAGE_API_KEY"):
            client.fetch_daily_alpha_vantage("AAPL")


def test_alpha_vantage_lands_and_caches() -> None:
    payload = {"Time Series (Daily)": {"2023-01-03": {"4. close": "125.07"}}}
    with respx.mock:
        route = respx.get(url__startswith="https://www.alphavantage.co/query").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with PricesClient() as client:
            result = client.fetch_daily_alpha_vantage("AAPL")
            client.fetch_daily_alpha_vantage("AAPL")  # cached — protects the ~25/day quota
            assert route.call_count == 1
            assert client._land_path("av_AAPL", "json").exists()

    assert result["Time Series (Daily)"]["2023-01-03"]["4. close"] == "125.07"


# -- backend dispatch -------------------------------------------------------
def test_unknown_backend_raises() -> None:
    with PricesClient() as client:
        with pytest.raises(ValueError, match="unknown prices backend"):
            client.fetch_daily("AAPL", backend="nasdaq")
