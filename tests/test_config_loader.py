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

MIN_COMPANIES = 30


def test_universe_is_populated_and_unique() -> None:
    companies = load_companies()
    assert len(companies) >= MIN_COMPANIES
    assert len(set(tickers())) == len(companies), "duplicate ticker in companies.yml"


def test_taiwan_stays_excluded() -> None:
    assert "TSM" not in tickers()


def test_every_company_has_a_pinned_cik() -> None:
    for company in load_companies():
        cik = cik_for(company)
        assert cik and len(cik) == 10 and cik.isdigit(), company["ticker"]


def test_xom_pinned_to_operating_entity() -> None:
    xom = next(c for c in load_companies() if c["ticker"] == "XOM")
    assert cik_for(xom) == "0000034088"


def test_reporting_currency_verified_against_filings() -> None:
    by_ticker = {c["ticker"]: c for c in load_companies()}
    for ticker, domestic in (("AZN", "GBP"), ("SHEL", "GBP"), ("INFY", "INR")):
        assert by_ticker[ticker]["currency"] == domestic
        assert by_ticker[ticker]["reporting_currency"] == "USD"


def test_fx_conversion_is_exercised_by_multiple_currencies() -> None:
    non_usd = [c for c in load_companies() if c["reporting_currency"] != "USD"]
    currencies = {c["reporting_currency"] for c in non_usd}
    assert len(non_usd) >= 5, "too few companies exercise currency conversion"
    assert len(currencies) >= 3, f"conversion rests on too few currencies: {currencies}"


def test_taxonomy_is_verified_not_inferred_from_filer_type() -> None:
    by_ticker = {c["ticker"]: c for c in load_companies()}
    assert by_ticker["BABA"]["filer_type"] == "20-F"
    assert by_ticker["BABA"]["xbrl_taxonomy"] == "us-gaap"
    for ticker in ("AAPL", "MSFT", "JPM", "XOM"):
        assert by_ticker[ticker]["xbrl_taxonomy"] == "us-gaap"
    for ticker in ("AZN", "SHEL", "TM", "INFY"):
        assert by_ticker[ticker]["xbrl_taxonomy"] == "ifrs-full"


def test_countries_and_currencies_avoid_the_known_coverage_gaps() -> None:
    assert "TWN" not in country_iso3_set()
    assert "TWD" not in non_usd_currencies()
    assert len(country_iso3_set()) >= 5


def test_price_tickers_include_benchmarks() -> None:
    assert benchmarks() == ["SPY", "ACWI"]
    assert len(price_tickers()) == len(tickers()) + len(benchmarks())
    assert set(benchmarks()) <= set(price_tickers())
