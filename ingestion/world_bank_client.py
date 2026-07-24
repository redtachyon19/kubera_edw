"""World Bank client — country-level macro indicators.

REST, no key. Pattern:
  https://api.worldbank.org/v2/country/{iso3};{iso3}/indicator/{code}?format=json&per_page=...

Indicator codes (see docs/project_spec.md §5):
  - NY.GDP.MKTP.CD      GDP (current US$)
  - NY.GDP.MKTP.KD.ZG   GDP growth (annual %)
  - FP.CPI.TOTL.ZG      Inflation, consumer prices (annual %)
  - SL.UEM.TOTL.ZS      Unemployment (% of labor force)

Note: macro figures are revised/published with a lag — record a load/version date on landing
so historical revisions don't silently overwrite what an analyst already relied on.
"""

from __future__ import annotations

from .base_client import BaseClient

INDICATORS: dict[str, str] = {
    "gdp": "NY.GDP.MKTP.CD",
    "gdp_growth_pct": "NY.GDP.MKTP.KD.ZG",
    "cpi_inflation_pct": "FP.CPI.TOTL.ZG",
    "unemployment_pct": "SL.UEM.TOTL.ZS",
}


class WorldBankClient(BaseClient):
    source_name = "world_bank"
    base_url = "https://api.worldbank.org/v2"

    def fetch_indicator(
        self, iso3_codes: list[str], indicator: str, *, start_year: int, end_year: int
    ) -> list:
        """Fetch one indicator for one or more countries over a year range; land raw.

        TODO: build path /country/{';'.join(iso3)}/indicator/{INDICATORS[indicator]},
        params format=json, per_page large; response[1] holds the data rows.
        """
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("world_bank_client: not yet implemented (Phase 1).")
