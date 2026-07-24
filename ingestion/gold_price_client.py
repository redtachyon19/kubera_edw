"""Gold price client — LBMA daily gold fixing (USD/troy oz) as a macro/hedge benchmark.

Primary: FRED series GOLDAMGBD228NLBM (same free FRED key as US macro data). Endpoint:
  https://api.stlouisfed.org/fred/series/observations
  params: series_id=GOLDAMGBD228NLBM, api_key=..., file_type=json
Backup: metals-api.com (free tier) only if an intraday spot price is needed instead of the
daily fixing — batch/cache due to the modest monthly request cap.

Feeds fact_gold_price: a single global daily series, joined only on dim_date (§9).

Landing is raw-as-is: FRED marks missing observations with "." and those are deliberately NOT
filtered here — that cleanup belongs to the Phase-2 stg_gold__prices model.
"""

from __future__ import annotations

import logging
import os

from .base_client import BaseClient
from .config_loader import bootstrap

log = logging.getLogger(__name__)

GOLD_SERIES_ID = "GOLDAMGBD228NLBM"
DEFAULT_START = "2010-01-01"


class GoldPriceClient(BaseClient):
    source_name = "gold_price"
    base_url = "https://api.stlouisfed.org/fred"

    def fetch_gold_series(self, *, start: str | None = None, end: str | None = None) -> dict:
        """Fetch the LBMA gold fixing observations from FRED; land raw."""
        api_key = os.environ.get("FRED_API_KEY")
        if not api_key:
            raise RuntimeError(
                "FRED_API_KEY is required for the gold price series. Set it in .env."
            )

        params = {
            "series_id": GOLD_SERIES_ID,
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


def main() -> None:
    bootstrap()
    with GoldPriceClient() as client:
        client.fetch_gold_series(start=DEFAULT_START)
    log.info("done — gold series landed")


if __name__ == "__main__":
    main()
