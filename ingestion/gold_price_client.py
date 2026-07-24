"""Gold price client — LBMA daily gold fixing (USD/troy oz) as a macro/hedge benchmark.

Primary: FRED series GOLDAMGBD228NLBM (same free FRED key as US macro data). Endpoint:
  https://api.stlouisfed.org/fred/series/observations
  params: series_id=GOLDAMGBD228NLBM, api_key=..., file_type=json
Backup: metals-api.com (free tier) only if an intraday spot price is needed instead of the
daily fixing — batch/cache due to the modest monthly request cap.

Feeds fact_gold_price: a single global daily series, joined only on dim_date (§9).
"""

from __future__ import annotations

import os

from .base_client import BaseClient

GOLD_SERIES_ID = "GOLDAMGBD228NLBM"


class GoldPriceClient(BaseClient):
    source_name = "gold_price"
    base_url = "https://api.stlouisfed.org/fred"

    def fetch_gold_series(self, *, start: str | None = None, end: str | None = None) -> dict:
        """Fetch the LBMA gold fixing observations from FRED; land raw.

        TODO: require FRED_API_KEY, call /series/observations with series_id=GOLD_SERIES_ID,
        file_type=json, optional observation_start/observation_end.
        """
        api_key = os.environ.get("FRED_API_KEY")
        if not api_key:
            raise RuntimeError(
                "FRED_API_KEY is required for the gold price series. Set it in .env."
            )
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("gold_price_client: not yet implemented (Phase 1).")
