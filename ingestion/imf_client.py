from __future__ import annotations

import logging

from .base_client import BaseClient
from .config_loader import bootstrap, country_iso3_set

log = logging.getLogger(__name__)

INDICATORS: dict[str, str] = {
    "gdp_growth_pct": "NGDP_RPCH",
    "cpi_inflation_pct": "PCPIPCH",
}


class ImfClient(BaseClient):
    source_name = "imf"
    base_url = "https://www.imf.org/external/datamapper/api/v1"

    def fetch_indicator(self, indicator: str, iso3_codes: list[str]) -> dict:
        code = INDICATORS.get(indicator, indicator)
        payload = self._get(f"/{code}/{'/'.join(iso3_codes)}").json()
        self._land(f"{indicator}_{code}", payload)
        covered = list(payload.get("values", {}).get(code, {}))
        log.info("%s (%s): coverage for %s", indicator, code, ",".join(covered) or "none")
        return payload


def main() -> None:
    bootstrap()
    countries = sorted(country_iso3_set())

    with ImfClient() as client:
        for indicator in INDICATORS:
            try:
                client.fetch_indicator(indicator, countries)
            except Exception as exc:  # noqa: BLE001
                log.warning("IMF cross-check unavailable for %s: %s", indicator, exc)

    log.info("done — IMF cross-check complete")


if __name__ == "__main__":
    main()
