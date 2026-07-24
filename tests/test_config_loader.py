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

UNIVERSE = {"AAPL", "MSFT", "JPM", "XOM", "AZN", "SHEL", "TM", "INFY", "BABA"}


def test_universe_is_the_locked_subset() -> None:
    assert len(load_companies()) == 9
    assert set(tickers()) == UNIVERSE


def test_taiwan_was_dropped() -> None:
    # TSM reports in TWD, which Frankfurter does not serve — its financials could not be
    # USD-normalized at all, so it was replaced by INFY + BABA rather than special-cased.
    assert "TSM" not in tickers()
    assert "TWN" not in country_iso3_set()
    assert "TWD" not in non_usd_currencies()


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


def test_only_two_companies_need_fx_conversion() -> None:
    # FX normalization is exercised solely by TM (JPY) and BABA (CNY); everything else
    # reports in USD. Losing either would leave the FX-contribution KPI resting on one name.
    needs_fx = {
        c["ticker"] for c in load_companies() if c["reporting_currency"] != "USD"
    }
    assert needs_fx == {"TM", "BABA"}


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


def test_countries_and_currencies_are_fully_covered() -> None:
    # Every country here has World Bank data and every currency is Frankfurter-served
    # (both verified live during the Phase-1 scope revision).
    assert country_iso3_set() == {"USA", "GBR", "JPN", "IND", "CHN"}
    assert non_usd_currencies() == {"GBP", "JPY", "INR", "CNY"}


def test_price_tickers_include_benchmarks() -> None:
    assert benchmarks() == ["SPY", "ACWI"]
    assert len(price_tickers()) == 11
    assert set(benchmarks()) <= set(price_tickers())
