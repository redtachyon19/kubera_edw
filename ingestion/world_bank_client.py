from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from .base_client import BaseClient
from .config_loader import bootstrap, country_iso3_set

log = logging.getLogger(__name__)

INDICATORS: dict[str, str] = {
    "gdp": "NY.GDP.MKTP.CD",
    "gdp_growth_pct": "NY.GDP.MKTP.KD.ZG",
    "cpi_inflation_pct": "FP.CPI.TOTL.ZG",
    "unemployment_pct": "SL.UEM.TOTL.ZS",
}

# The World Bank has no series for Taiwan — it is not a member. Asking for it by
# code returns an error for the whole request rather than a gap in one row, so it
# is dropped before the call is built.
UNSUPPORTED_ISO3 = {"TWN"}

# `country/all` returns roughly 265 entities, of which ~50 are aggregates (world,
# income bands, regions) carrying a blank or non-country iso3.
ALL_COUNTRIES = "all"

# Whole-world pulls are large enough that a single unpaged request times out more
# often than it succeeds. Paging keeps each response small enough to land.
_PAGE_SIZE = 1000
_MAX_PAGES = 40


class WorldBankClient(BaseClient):
    source_name = "world_bank"
    base_url = "https://api.worldbank.org/v2"
    # The whole-world responses are slow to assemble server-side; the default 30s
    # is not enough for the first page of a 16-year window.
    timeout_s = 90.0

    def __init__(self, *, base_url: str | None = None) -> None:
        super().__init__(base_url=base_url)
        self._client.timeout = httpx.Timeout(self.timeout_s)

    def _pages(self, path: str, *, start_year: int, end_year: int) -> list[dict]:
        """Every row for `path`, following the World Bank's page cursor.

        Returns what it managed to collect. A page that fails after the base
        client's retries ends the walk rather than the run: a partial series is
        worth more to the warehouse than no series, and the caller records how
        far it got.
        """
        rows: list[dict] = []
        page = 1
        while page <= _MAX_PAGES:
            try:
                payload = self._get(
                    path,
                    format="json",
                    per_page=_PAGE_SIZE,
                    page=page,
                    date=f"{start_year}:{end_year}",
                ).json()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("%s page %d failed (%s) — keeping %d rows", path, page, exc, len(rows))
                break

            if not isinstance(payload, list) or len(payload) < 2:
                # The API reports its own errors as a single-element list holding
                # a `message` array, with a 200 status.
                log.warning("%s page %d returned no data block: %.200s", path, page, payload)
                break

            meta, block = payload[0] or {}, payload[1] or []
            rows.extend(block)
            if page >= int(meta.get("pages") or 1):
                break
            page += 1

        return rows

    def fetch_countries(self) -> list[dict]:
        """Land the country reference: name, region, income band, capital, coordinates.

        This is what turns a table of ISO3 codes into something that can be drawn
        — the World Bank publishes a capital-city latitude and longitude for every
        member, which is the only geographic fix the warehouse needs.
        """
        rows = self._pages_plain("/country")
        countries = [
            r
            for r in rows
            # A blank or `NA` region marks an aggregate — the world, an income
            # band, a lending group — rather than a country.
            if (r.get("region") or {}).get("id") not in (None, "", "NA")
            and r.get("longitude")
            and r.get("latitude")
        ]

        loaded_at = datetime.now(UTC)
        self._land(
            f"countries_{loaded_at:%Y%m%d}",
            {
                "loaded_at": loaded_at.isoformat(),
                "source_url": f"{self.base_url}/country",
                "aggregates_dropped": len(rows) - len(countries),
                "data": countries,
            },
        )
        log.info(
            "countries: %d of %d entities are countries with coordinates", len(countries), len(rows)
        )
        return countries

    def _pages_plain(self, path: str) -> list[dict]:
        """Page walk for endpoints that take no date window."""
        rows: list[dict] = []
        page = 1
        while page <= _MAX_PAGES:
            try:
                payload = self._get(path, format="json", per_page=_PAGE_SIZE, page=page).json()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("%s page %d failed (%s) — keeping %d rows", path, page, exc, len(rows))
                break
            if not isinstance(payload, list) or len(payload) < 2:
                log.warning("%s page %d returned no data block: %.200s", path, page, payload)
                break
            meta, block = payload[0] or {}, payload[1] or []
            rows.extend(block)
            if page >= int(meta.get("pages") or 1):
                break
            page += 1
        return rows

    def fetch_indicator(
        self,
        iso3_codes: list[str] | None,
        indicator: str,
        *,
        start_year: int,
        end_year: int,
    ) -> list:
        """Land one indicator. `iso3_codes=None` asks for every country."""
        code = INDICATORS[indicator]

        if iso3_codes is None:
            selector, supported, skipped = ALL_COUNTRIES, None, []
        else:
            supported = [c for c in iso3_codes if c not in UNSUPPORTED_ISO3]
            skipped = sorted(set(iso3_codes) - set(supported))
            if skipped:
                log.warning(
                    "no World Bank coverage for %s — skipping (known gap)", ", ".join(skipped)
                )
            if not supported:
                log.warning("no supported countries for %s; nothing to fetch", indicator)
                return []
            selector = ";".join(supported)

        path = f"/country/{selector}/indicator/{code}"
        rows = self._pages(path, start_year=start_year, end_year=end_year)

        # An entity with a blank iso3 is an aggregate (EUU, world, income bands).
        # They are kept in the landed payload — the warehouse decides what to do
        # with them — but only real countries count towards coverage.
        observed = {r.get("countryiso3code") for r in rows if r.get("value") is not None}
        observed.discard(None)
        observed.discard("")
        missing = sorted(set(supported) - observed) if supported else []
        if missing:
            log.warning(
                "%s: no values returned for %s — the series does not cover them",
                indicator,
                ", ".join(missing),
            )

        loaded_at = datetime.now(UTC)
        self._land(
            f"{indicator}_{loaded_at:%Y%m%d}",
            {
                "loaded_at": loaded_at.isoformat(),
                "indicator": indicator,
                "indicator_code": code,
                "countries": supported if supported is not None else sorted(observed),
                "requested": "all" if supported is None else "explicit",
                "skipped_countries": skipped,
                "empty_countries": missing,
                "source_url": f"{self.base_url}{path}",
                "data": rows,
            },
        )
        log.info(
            "%s: %d rows covering %d entities%s",
            indicator,
            len(rows),
            len(observed),
            "" if supported is None else f" of {len(supported)} requested",
        )
        return rows


def main() -> None:
    """Land every indicator for every country the World Bank publishes.

    Pulling the whole world rather than only the countries named in
    `companies.yml` is what lets the Markets desk compare a government against
    its peers instead of against the dozen that happen to have an issuer in the
    portfolio. Downstream models filter; ingestion no longer does.
    """
    bootstrap()
    portfolio = sorted(country_iso3_set())
    end_year = datetime.now(UTC).year

    landed, failed = 0, []
    with WorldBankClient() as client:
        try:
            client.fetch_countries()
        except Exception:
            log.exception("country reference failed — indicators will still be landed")
            failed.append("countries")

        for indicator in INDICATORS:
            try:
                rows = client.fetch_indicator(None, indicator, start_year=2010, end_year=end_year)
            except Exception:
                # One indicator being retired or renamed upstream should not cost
                # the run the other three.
                log.exception("%s failed — continuing with the rest", indicator)
                failed.append(indicator)
                continue
            if rows:
                landed += 1
            else:
                failed.append(indicator)

    log.info(
        "done — landed %d of %d indicators (portfolio countries: %s)%s",
        landed,
        len(INDICATORS),
        ", ".join(portfolio),
        f"; no data for {', '.join(failed)}" if failed else "",
    )
    if not landed:
        raise RuntimeError("World Bank returned nothing for any indicator")


if __name__ == "__main__":
    main()
