"""Gold price client — the cross-cutting safe-haven benchmark (§9, §10).

SOURCE CHANGE (verified 2026-07-24). The spec's primary source, FRED series
GOLDAMGBD228NLBM (LBMA daily gold fixing), NO LONGER EXISTS: the API answers

    400 {"error_code":400,"error_message":"Bad Request.  The series does not exist."}

with a valid key, and a FRED series search for "gold price" returns only volatility indices
(GVZCLS) and producer/import price INDICES — no spot USD/oz series at all. FRED appears to have
dropped the precious-metals price series over licensing.

Backends now, in order:
  1. GLD (SPDR Gold Shares) via Alpha Vantage — DEFAULT. A tradeable gold proxy holding
     physical bullion, roughly 1/10 troy oz per share. Uses the Alpha Vantage key already
     configured for prices, so it needs no extra signup. It tracks gold rather than BEING the
     fixing, which is the honest trade for a benchmark overlay.
  2. A FRED series id — kept because the code path is still correct and FRED may restore a
     series, or a different one may be wanted. Pass ``series_id`` explicitly.
  3. metals-api.com — the spec's documented backup for true spot; needs METALS_API_KEY.

Whatever the backend, the landed payload keeps FRED's ``{"observations": [{date, value}]}``
shape so the Phase-2 staging model does not care which one produced it.
"""

from __future__ import annotations

import logging

from .base_client import BaseClient
from .config_loader import api_key as get_api_key
from .config_loader import bootstrap

log = logging.getLogger(__name__)

#: Retired by FRED — retained so the failure is self-documenting rather than mysterious.
GOLD_SERIES_ID = "GOLDAMGBD228NLBM"
#: Default backend: gold ETF proxy via Alpha Vantage.
GOLD_PROXY_TICKER = "GLD"
DEFAULT_START = "2010-01-01"


class GoldPriceClient(BaseClient):
    source_name = "gold_price"
    base_url = "https://api.stlouisfed.org/fred"

    def fetch_gold_series(
        self, *, start: str | None = None, end: str | None = None, series_id: str | None = None
    ) -> dict:
        """Fetch a FRED gold series. Requires FRED_API_KEY and a series that still exists.

        Retained for completeness; ``GOLD_SERIES_ID`` itself is retired (see module docstring).
        """
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
        """Fetch the gold ETF proxy and land it in the FRED observations shape.

        Normalizing here rather than in staging keeps the backend swap invisible to dbt: the
        staging model reads the same ``observations`` array whichever source produced it.
        """
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
