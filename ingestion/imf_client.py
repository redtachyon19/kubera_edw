"""IMF client — international financial statistics (secondary / cross-check source).

The IMF retired its legacy dataservices.imf.org portal in Nov 2025 in favor of a new SDMX 3.0
API at data.imf.org. The simpler DataMapper API is the lighter option for headline indicators:
  https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3}/{iso3}
Response shape: {"values": {"<indicator>": {"<iso3>": {"<year>": value}}}}

Used to cross-check World Bank macro figures (§5/§11), not as the primary macro source — it is
deliberately non-fatal so a DataMapper outage never blocks the main pipeline.
"""

from __future__ import annotations

import logging

from .base_client import BaseClient
from .config_loader import bootstrap, country_iso3_set

log = logging.getLogger(__name__)

#: DataMapper headline indicators used as cross-checks.
INDICATORS: dict[str, str] = {
    "gdp_growth_pct": "NGDP_RPCH",
    "cpi_inflation_pct": "PCPIPCH",
}


class ImfClient(BaseClient):
    source_name = "imf"
    base_url = "https://www.imf.org/external/datamapper/api/v1"

    def fetch_indicator(self, indicator: str, iso3_codes: list[str]) -> dict:
        """Fetch a DataMapper indicator for the given countries; land raw."""
        code = INDICATORS.get(indicator, indicator)
        payload = self._get(f"/{code}/{'/'.join(iso3_codes)}").json()
        self._land(f"{indicator}_{code}", payload)
        covered = list(payload.get("values", {}).get(code, {}))
        log.info("%s (%s): coverage for %s", indicator, code, ",".join(covered) or "none")
        return payload


def main() -> None:
    """Cross-check macro indicators. Failures are logged, never fatal."""
    bootstrap()
    countries = sorted(country_iso3_set())

    with ImfClient() as client:
        for indicator in INDICATORS:
            try:
                client.fetch_indicator(indicator, countries)
            except Exception as exc:  # noqa: BLE001 — optional cross-check source
                log.warning("IMF cross-check unavailable for %s: %s", indicator, exc)

    log.info("done — IMF cross-check complete")


if __name__ == "__main__":
    main()
