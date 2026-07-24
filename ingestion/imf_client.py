"""IMF client — international financial statistics (secondary / cross-check source).

The IMF retired its legacy dataservices.imf.org portal in Nov 2025 in favor of a new SDMX 3.0
API at data.imf.org. The simpler DataMapper API is a lighter option for headline indicators:
  https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3}
Confirm current REST docs before building (docs/project_spec.md §5.1).

Used mainly to cross-check World Bank macro figures, not as the primary macro source.
"""

from __future__ import annotations

from .base_client import BaseClient


class ImfClient(BaseClient):
    source_name = "imf"
    base_url = "https://www.imf.org/external/datamapper/api/v1"

    def fetch_indicator(self, indicator: str, iso3_codes: list[str]) -> dict:
        """Fetch a DataMapper indicator for the given countries; land raw.

        TODO: confirm endpoint shape on the current DataMapper/SDMX docs, then implement.
        """
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("imf_client: not yet implemented (Phase 1, optional cross-check).")
