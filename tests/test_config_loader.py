"""Tests for ingestion.config_loader — the coverage universe contract.

These assert the scope lock stays intact, since every downstream phase keys off it.
"""

from __future__ import annotations

from ingestion.config_loader import (
    benchmarks,
    cik_for,
    country_iso3_set,
    load_companies,
    non_usd_currencies,
    price_tickers,
    tickers,
)

# Deliberately NOT a frozen ticker list. The universe is expected to grow (9 -> 38 in
# Phase 8), so these tests assert the RULES the universe must satisfy rather than its exact
# membership — a hardcoded list only ever fails for the wrong reason on a scale-out.
MIN_COMPANIES = 30


def test_universe_is_populated_and_unique() -> None:
    companies = load_companies()
    assert len(companies) >= MIN_COMPANIES
    assert len(set(tickers())) == len(companies), "duplicate ticker in companies.yml"


def test_taiwan_stays_excluded() -> None:
    # TSM reports in TWD, which Frankfurter does not serve, and Taiwan has no World Bank
    # macro — so its financials cannot be USD-normalized at all. Re-verified at scale-out.
    assert "TSM" not in tickers()


def test_every_company_has_a_pinned_cik() -> None:
    for company in load_companies():
        cik = cik_for(company)
        assert cik and len(cik) == 10 and cik.isdigit(), company["ticker"]


def test_xom_pinned_to_operating_entity() -> None:
    # The XOM ticker now maps to a reorg holdco (0002115436) with no 10-K/XBRL history.
    xom = next(c for c in load_companies() if c["ticker"] == "XOM")
    assert cik_for(xom) == "0000034088"


def test_reporting_currency_verified_against_filings() -> None:
    # Verified from each company's actual XBRL monetary units. Foreign domicile does NOT
    # imply foreign reporting currency: AZN/SHEL/INFY all file with the SEC in USD, so
    # treating their domestic currency as the reporting one would double-convert Phase 4.
    by_ticker = {c["ticker"]: c for c in load_companies()}
    for ticker, domestic in (("AZN", "GBP"), ("SHEL", "GBP"), ("INFY", "INR")):
        assert by_ticker[ticker]["currency"] == domestic
        assert by_ticker[ticker]["reporting_currency"] == "USD"


def test_fx_conversion_is_exercised_by_multiple_currencies() -> None:
    """FX normalization must not rest on a single company or currency.

    At the 9-company scope only TM (JPY) and BABA (CNY) converted, which made the whole
    FX-contribution capability fragile — dropping either would have removed it.
    """
    non_usd = [c for c in load_companies() if c["reporting_currency"] != "USD"]
    currencies = {c["reporting_currency"] for c in non_usd}
    assert len(non_usd) >= 5, "too few companies exercise currency conversion"
    assert len(currencies) >= 3, f"conversion rests on too few currencies: {currencies}"


def test_taxonomy_is_verified_not_inferred_from_filer_type() -> None:
    # BABA is the counterexample: a 20-F filer tagging under us-gaap. Any staging logic that
    # derives taxonomy from filer_type would silently find nothing for it.
    by_ticker = {c["ticker"]: c for c in load_companies()}
    assert by_ticker["BABA"]["filer_type"] == "20-F"
    assert by_ticker["BABA"]["xbrl_taxonomy"] == "us-gaap"
    # US domestic filers are still uniformly us-gaap.
    for ticker in ("AAPL", "MSFT", "JPM", "XOM"):
        assert by_ticker[ticker]["xbrl_taxonomy"] == "us-gaap"
    # And the remaining foreign issuers are ifrs-full.
    for ticker in ("AZN", "SHEL", "TM", "INFY"):
        assert by_ticker[ticker]["xbrl_taxonomy"] == "ifrs-full"


def test_countries_and_currencies_avoid_the_known_coverage_gaps() -> None:
    """Taiwan/TWD are the verified coverage gaps: no World Bank macro, no Frankfurter rate.

    Any company reintroducing them cannot be USD-normalized or given macro context, so the
    universe must stay clear of them however it grows.
    """
    assert "TWN" not in country_iso3_set()
    assert "TWD" not in non_usd_currencies()
    assert len(country_iso3_set()) >= 5


def test_price_tickers_include_benchmarks() -> None:
    assert benchmarks() == ["SPY", "ACWI"]
    assert len(price_tickers()) == len(tickers()) + len(benchmarks())
    assert set(benchmarks()) <= set(price_tickers())
