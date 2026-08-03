from __future__ import annotations

import logging

from .base_client import BaseClient
from .config_loader import api_key as get_api_key
from .config_loader import bootstrap

log = logging.getLogger(__name__)

GOLD_SERIES_ID = "GOLDAMGBD228NLBM"
GOLD_PROXY_TICKER = "GLD"
DEFAULT_START = "2010-01-01"


class GoldPriceClient(BaseClient):
    source_name = "gold_price"
    base_url = "https://api.stlouisfed.org/fred"

    def fetch_gold_series(
        self, *, start: str | None = None, end: str | None = None, series_id: str | None = None
    ) -> dict:
        api_key = get_api_key("FRED_API_KEY")
        if not api_key:
            raise RuntimeError(
                "FRED_API_KEY is not set (or is still the .env.example placeholder)."
            )

        params = {
            "series_id": series_id or GOLD_SERIES_ID,
            "api_key": api_key,
            "file_type": "json",
        }
        if start:
            params["observation_start"] = start
        if end:
            params["observation_end"] = end

        payload = self._get("/series/observations", **params).json()
        self._land("gold_lbma_fixing", payload)
        log.info("gold: %d observations", len(payload.get("observations", [])))
        return payload

    def fetch_gold_proxy(self, ticker: str = GOLD_PROXY_TICKER) -> dict:
        from .prices_client import PricesClient

        with PricesClient() as prices:
            raw = prices.fetch_daily_alpha_vantage(ticker)

        series = raw.get("Time Series (Daily)", {})
        payload = {
            "series_id": ticker,
            "source": "alpha_vantage",
            "note": (
                "SPDR Gold Shares (GLD) close, USD per share (~1/10 troy oz). Substitute for "
                "FRED GOLDAMGBD228NLBM, which no longer exists."
            ),
            "observations": [
                {"date": day, "value": bar["4. close"]} for day, bar in sorted(series.items())
            ],
        }
        self._land("gold_lbma_fixing", payload)
        log.info("gold proxy %s: %d observations", ticker, len(payload["observations"]))
        return payload


def main() -> None:
    bootstrap()
    with GoldPriceClient() as client:
        client.fetch_gold_proxy()
    log.info("done — gold benchmark landed")


if __name__ == "__main__":
    main()
