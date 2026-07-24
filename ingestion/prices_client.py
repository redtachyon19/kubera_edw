"""Market price client — daily close prices for return / volatility / drawdown KPIs.

Two backends (see docs/project_spec.md §5):
  - Stooq (no key, bulk historical): https://stooq.com/q/d/l/?s={ticker}.us&i=d  -> CSV
  - Alpha Vantage (free key, low volume ~25 req/day): TIME_SERIES_DAILY_ADJUSTED

Free-tier limits mean prices should be pulled in bulk and CACHED locally, not re-fetched every
run. Default to Stooq for scale; use Alpha Vantage only where adjusted/extra fields are needed.
"""

from __future__ import annotations

import os

from .base_client import BaseClient


class PricesClient(BaseClient):
    source_name = "prices"
    base_url = "https://stooq.com"

    def fetch_daily_stooq(self, ticker: str) -> str:
        """Bulk historical daily OHLCV from Stooq (CSV, no key); land raw.

        TODO: self._get(f"/q/d/l/", s=f"{ticker.lower()}.us", i="d"); land response.text as CSV.
        """
        raise NotImplementedError

    def fetch_daily_alpha_vantage(self, ticker: str) -> dict:
        """Adjusted daily series from Alpha Vantage (free key, rate-limited); land raw."""
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is required for the Alpha Vantage backend.")
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("prices_client: not yet implemented (Phase 1).")
