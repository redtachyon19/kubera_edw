from __future__ import annotations

import logging
from datetime import UTC, datetime

from .base_client import BaseClient
from .config_loader import bootstrap, country_iso3_set

log = logging.getLogger(__name__)

INDICATORS: dict[str, str] = {
    "gdp": "NY.GDP.MKTP.CD",
    "gdp_growth_pct": "NY.GDP.MKTP.KD.ZG",
    "cpi_inflation_pct": "FP.CPI.TOTL.ZG",
    "unemployment_pct": "SL.UEM.TOTL.ZS",
}

UNSUPPORTED_ISO3 = {"TWN"}


class WorldBankClient(BaseClient):
    source_name = "world_bank"
    base_url = "https://api.worldbank.org/v2"

    def fetch_indicator(
        self, iso3_codes: list[str], indicator: str, *, start_year: int, end_year: int
    ) -> list:
        code = INDICATORS[indicator]
        supported = [c for c in iso3_codes if c not in UNSUPPORTED_ISO3]
        skipped = sorted(set(iso3_codes) - set(supported))
        if skipped:
            log.warning("no World Bank coverage for %s — skipping (known gap)", ", ".join(skipped))
        if not supported:
            log.warning("no supported countries for %s; nothing to fetch", indicator)
            return []

        path = f"/country/{';'.join(supported)}/indicator/{code}"
        payload = self._get(
            path, format="json", per_page=20000, date=f"{start_year}:{end_year}"
        ).json()

        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        rows = rows or []

        loaded_at = datetime.now(UTC)
        self._land(
            f"{indicator}_{loaded_at:%Y%m%d}",
            {
                "loaded_at": loaded_at.isoformat(),
                "indicator": indicator,
                "indicator_code": code,
                "countries": supported,
                "skipped_countries": skipped,
                "source_url": f"{self.base_url}{path}",
                "data": rows,
            },
        )
        log.info("%s: %d rows for %s", indicator, len(rows), ",".join(supported))
        return rows


def main() -> None:
    bootstrap()
    countries = sorted(country_iso3_set())
    end_year = datetime.now(UTC).year

    with WorldBankClient() as client:
        for indicator in INDICATORS:
            client.fetch_indicator(countries, indicator, start_year=2010, end_year=end_year)

    log.info("done — landed %d indicators", len(INDICATORS))


if __name__ == "__main__":
    main()
