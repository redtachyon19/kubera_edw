from __future__ import annotations

import httpx
import pytest
import respx

from ingestion.prices_client import PricesClient

STOOQ_CHALLENGE = (
    "<!DOCTYPE html><html><body><noscript>This site requires JavaScript to verify your "
    'browser.</noscript><script>fetch("/__verify")</script></body></html>'
)


def test_stooq_lands_csv_not_json(sample_stooq_csv: str) -> None:
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
    with respx.mock:
        route = respx.get(url__startswith="https://stooq.com/q/d/l/").mock(
            return_value=httpx.Response(200, text=sample_stooq_csv)
        )
        with PricesClient() as client:
            client.fetch_daily_stooq("AAPL")
            client.fetch_daily_stooq("AAPL")
            assert route.call_count == 1

            client.fetch_daily_stooq("AAPL", force=True)
            assert route.call_count == 2


def test_stooq_detects_bot_challenge() -> None:
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


def test_alpha_vantage_uses_free_daily_endpoint() -> None:
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
    with respx.mock:
        respx.get(url__startswith="https://www.alphavantage.co/query").mock(
            return_value=httpx.Response(200, json={"Note": "call frequency limit reached"})
        )
        with PricesClient() as client:
            with pytest.raises(RuntimeError, match="Alpha Vantage Note"):
                client.fetch_daily_alpha_vantage("AAPL")
            assert not client._land_path("av_AAPL", "json").exists()


def test_alpha_vantage_detects_premium_information_response() -> None:
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
            client.fetch_daily_alpha_vantage("AAPL")
            assert route.call_count == 1
            assert client._land_path("av_AAPL", "json").exists()

    assert result["Time Series (Daily)"]["2023-01-03"]["4. close"] == "125.07"


def test_unknown_backend_raises() -> None:
    with PricesClient() as client:
        with pytest.raises(ValueError, match="unknown prices backend"):
            client.fetch_daily("AAPL", backend="nasdaq")
