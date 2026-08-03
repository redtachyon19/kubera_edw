"""Turn a bare ticker into a warehouse universe entry.

`companies.yml` is hand-maintained and asks for eleven fields per holding — CIK,
legal name, filer type, taxonomy, fiscal year end, two currencies, country in
two forms. That is fine for a curated list of 38 and impossible as a prerequisite
for "add this company to the warehouse", which is one ticker's worth of intent.

Almost all of it is derivable. SEC's submissions endpoint knows the registrant's
name, its fiscal year end, and which annual form it files; its XBRL facts say
which taxonomy it tags in and which currency it reports. What EDGAR does not
carry is the market's view — sector, country of operations, trading currency —
so the caller passes those as hints and they fall back to EDGAR's own answer.

Nothing here writes anything. It returns a proposed entry for
`ingestion/backfill.py` to append, so a resolution can be inspected before the
universe changes.
"""

from __future__ import annotations

import logging
from typing import Any

from .base_client import BaseClient

log = logging.getLogger(__name__)

SUBMISSIONS = "/submissions/CIK{cik}.json"

# The annual form a registrant files says what kind of filer it is, which is the
# one field the warehouse treats as structural: a 20-F filer reports once a year
# under IFRS, a 10-K filer quarterly under US GAAP.
ANNUAL_FORMS = ("10-K", "20-F", "40-F")

# Country name -> ISO3, for the countries a US-listed issuer is likely to sit in.
# `dim_country` joins on ISO3, so an unmapped country would orphan the holding.
ISO3 = {
    "United States": "USA",
    "Canada": "CAN",
    "Mexico": "MEX",
    "Brazil": "BRA",
    "United Kingdom": "GBR",
    "Ireland": "IRL",
    "France": "FRA",
    "Germany": "DEU",
    "Netherlands": "NLD",
    "Switzerland": "CHE",
    "Spain": "ESP",
    "Italy": "ITA",
    "Sweden": "SWE",
    "Denmark": "DNK",
    "Norway": "NOR",
    "Finland": "FIN",
    "Belgium": "BEL",
    "Luxembourg": "LUX",
    "Israel": "ISR",
    "Japan": "JPN",
    "China": "CHN",
    "Hong Kong": "HKG",
    "Taiwan": "TWN",
    "South Korea": "KOR",
    "India": "IND",
    "Singapore": "SGP",
    "Australia": "AUS",
    "South Africa": "ZAF",
    "Argentina": "ARG",
    "Chile": "CHL",
    "Colombia": "COL",
    "Greece": "GRC",
    "Portugal": "PRT",
    "Austria": "AUT",
    "Poland": "POL",
    "Turkey": "TUR",
    "Indonesia": "IDN",
    "Thailand": "THA",
    "Malaysia": "MYS",
    "Philippines": "PHL",
    "Vietnam": "VNM",
    "New Zealand": "NZL",
    "Bermuda": "BMU",
    "Cayman Islands": "CYM",
    "Jersey": "JEY",
    "Cyprus": "CYP",
    "Uruguay": "URY",
    "Peru": "PER",
}


class ResolutionError(RuntimeError):
    """The ticker could not be turned into a warehouse entry."""


class CompanyResolver(BaseClient):
    """Reads SEC for everything the universe file needs about one registrant."""

    source_name = "sec_edgar"
    base_url = "https://data.sec.gov"
    # SEC asks for no more than ten requests a second and a real User-Agent.
    min_interval_s = 0.11

    def _default_headers(self) -> dict[str, str]:
        import os

        agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
        if not agent:
            raise ResolutionError(
                "SEC_EDGAR_USER_AGENT is required by SEC EDGAR. It is not an API key — "
                'it is a courtesy header you declare yourself, as "Name you@example.com". '
                "Set it in .env."
            )
        return {"User-Agent": agent, "Accept": "application/json"}

    def _ticker_map(self) -> dict[str, str]:
        payload = self._get("https://www.sec.gov/files/company_tickers.json").json()
        return {
            str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
            for row in payload.values()
            if row.get("ticker")
        }

    def cik(self, ticker: str) -> str:
        cik = self._ticker_map().get(ticker.upper().strip())
        if not cik:
            raise ResolutionError(
                f"{ticker!r} is not in SEC's ticker list. Only SEC registrants can be "
                "backfilled — a foreign listing with no US registration files nothing here."
            )
        return cik

    def submissions(self, cik: str) -> dict:
        return self._get(SUBMISSIONS.format(cik=cik)).json()

    def facts(self, cik: str) -> dict:
        return self._get(f"/api/xbrl/companyfacts/CIK{cik}.json").json().get("facts") or {}


def _filer_type(submissions: dict) -> str:
    """The annual form this registrant actually files."""
    forms = (submissions.get("filings", {}).get("recent", {}) or {}).get("form", [])
    for form in forms:  # `recent` is newest-first, so the first hit is current
        if form in ANNUAL_FORMS:
            return form
    return "10-K"


def _fiscal_year_end(submissions: dict) -> str:
    """`MMDD` as EDGAR gives it, rendered the way `companies.yml` writes it."""
    raw = str(submissions.get("fiscalYearEnd") or "").strip()
    if len(raw) == 4 and raw.isdigit():
        return f"{raw[:2]}-{raw[2:]}"
    return "12-31"


def _taxonomy_and_currency(facts: dict) -> tuple[str, str]:
    """Which standard the filer tags in, and what it reports in.

    Both are read from the facts rather than assumed from the filer type: a 20-F
    filer may tag under either standard, and plenty report in USD.
    """
    taxonomy = "ifrs-full" if "ifrs-full" in facts else "us-gaap"

    counts: dict[str, int] = {}
    for tag in (facts.get(taxonomy) or {}).values():
        for unit, rows in (tag.get("units") or {}).items():
            # Currencies are three-letter codes; shares and per-share units are not.
            if len(unit) == 3 and unit.isalpha():
                counts[unit] = counts.get(unit, 0) + len(rows)
    currency = max(counts, key=lambda unit: counts[unit]) if counts else "USD"
    return taxonomy, currency


def resolve(ticker: str, hints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Propose a `companies.yml` entry for one ticker.

    Args:
        ticker: A US-listed ticker. SEC registrants only — the warehouse is built
            from filings, so a company that files nothing cannot be carried.
        hints: Optional `name`, `sector`, `country` and `currency` from the
            caller's own view of the listing, used where EDGAR has no opinion.

    Returns:
        A dict with every field `companies.yml` requires.

    Raises:
        ResolutionError: The ticker is not an SEC registrant, or SEC has no XBRL
            facts for it — a warehouse row built from nothing is worse than none.
    """
    ticker = ticker.upper().strip()
    hints = hints or {}

    with CompanyResolver() as resolver:
        cik = resolver.cik(ticker)
        submissions = resolver.submissions(cik)
        facts = resolver.facts(cik)

    if not facts:
        raise ResolutionError(
            f"SEC holds no XBRL facts for {ticker} (CIK {cik}). Nothing to build a "
            "warehouse row from."
        )

    taxonomy, reporting_currency = _taxonomy_and_currency(facts)
    country = hints.get("country") or "United States"
    entry = {
        "ticker": ticker,
        "cik": cik,
        # EDGAR's registrant name is upper case ("NVIDIA CORP"); the caller's is
        # the one a reader recognises, so it wins where there is one.
        "legal_name": hints.get("name") or str(submissions.get("name") or ticker).title(),
        "country": country,
        "country_iso3": ISO3.get(country, "USA"),
        "currency": hints.get("currency") or "USD",
        "reporting_currency": reporting_currency,
        "sector": hints.get("sector") or str(submissions.get("sicDescription") or "Unclassified"),
        "filer_type": _filer_type(submissions),
        "fiscal_year_end": _fiscal_year_end(submissions),
        "xbrl_taxonomy": taxonomy,
    }
    log.info(
        "resolved %s: CIK %s, %s, %s, reports in %s",
        ticker,
        cik,
        entry["filer_type"],
        entry["xbrl_taxonomy"],
        entry["reporting_currency"],
    )
    return entry
