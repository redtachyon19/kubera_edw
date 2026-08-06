"""The Companies desk — the parts that must hold without a network call.

Everything here runs offline. The live half (Yahoo prices, statements, news) is
exercised by opening the page; what is worth pinning down in a test is the logic
that decides *which* periods and *which* listings the page draws, because those
are the places a silent data change turns into a wrong-looking table.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dashboard_hub.lib import filings, market_data, warehouse

REPO_ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = REPO_ROOT / "data" / "kubera_edw.duckdb"
needs_warehouse = pytest.mark.skipif(
    not WAREHOUSE.exists(), reason="no built warehouse — run bash scripts/pipeline.sh"
)


def test_universe_covers_every_sector_constituent() -> None:
    known = {entry["symbol"] for entry in market_data.companies()}
    wanted = {s for sector in market_data.sectors() for s in sector["symbols"]}
    assert wanted <= known, f"missing from companies.json: {sorted(wanted - known)}"


def test_universe_covers_every_holding() -> None:
    from ingestion.config_loader import load_companies

    known = {entry["symbol"] for entry in market_data.companies() if entry["warehouse"]}
    assert known == {company["ticker"] for company in load_companies()}


def test_universe_entries_are_unique_and_named() -> None:
    entries = market_data.companies()
    symbols = [entry["symbol"] for entry in entries]
    assert len(symbols) == len(set(symbols))
    # A card showing its own ticker as its name means the generator could not
    # resolve it — that is a stale file, not a listing without a name.
    unresolved = [e["symbol"] for e in entries if e["name"] == e["symbol"]]
    assert not unresolved, f"unresolved names, re-run make company-universe: {unresolved}"


def test_annual_spine_drops_interim_columns() -> None:
    """Yahoo mixes interim periods into an annual statement for some filers."""
    columns = {
        pd.Timestamp("2026-03-31"),
        pd.Timestamp("2025-09-30"),  # interim
        pd.Timestamp("2025-06-30"),  # interim
        pd.Timestamp("2025-03-31"),
        pd.Timestamp("2024-03-31"),
    }
    kept = market_data._spine(columns, annual=True)
    assert [str(stamp.date()) for stamp in kept] == [
        "2024-03-31",
        "2025-03-31",
        "2026-03-31",
    ]


def test_annual_spine_keeps_a_52_week_year_end_that_drifts() -> None:
    """A 52/53-week filer's year end moves by a few days and is still annual."""
    columns = {
        pd.Timestamp("2025-09-27"),
        pd.Timestamp("2024-09-28"),
        pd.Timestamp("2023-09-30"),
    }
    assert len(market_data._spine(columns, annual=True)) == 3


def test_quarterly_spine_keeps_every_quarter() -> None:
    columns = {pd.Timestamp(d) for d in ("2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30")}
    assert len(market_data._spine(columns, annual=False)) == 4


def test_a_period_needs_a_top_line_to_count() -> None:
    """One stray figure is padding, not a reporting period."""
    assert not market_data._reports({"interestExpense": 1.0})
    assert market_data._reports({"revenue": 1.0})
    assert market_data._reports({"totalAssets": 1.0})


def test_absent_figures_become_null_not_nan() -> None:
    """NaN is what Yahoo returns for an unreported line, and is not valid JSON."""
    assert market_data._number(float("nan")) is None
    assert market_data._number(float("inf")) is None
    assert market_data._number(None) is None
    assert market_data._number("no") is None
    assert market_data._number(3) == 3.0


def test_filed_panel_is_absent_for_an_unindexed_name() -> None:
    """A name the warehouse has never been asked for gets no filed panel.

    The subject is derived rather than hardcoded. This test named NVDA and broke
    the moment NVDA was backfilled — which is not a defect being caught, it is
    the tool working as intended. Anything can be indexed on request, so a test
    that pins one ticker as permanently absent is only measuring how recently it
    was written.
    """
    indexed = set(warehouse.holdings())
    subject = next(
        (entry["symbol"] for entry in market_data.companies() if entry["symbol"] not in indexed),
        None,
    )
    assert subject, "every browsable name is indexed — pick another fixture"

    assert market_data._filed(subject) == {"held": False, "meta": None, "years": []}


@needs_warehouse
def test_filed_panel_reads_the_marts_without_streamlit() -> None:
    assert warehouse.available()
    filed = market_data._filed("TM")
    assert filed["held"]
    assert filed["meta"]["reportingCurrency"] == "JPY"

    years = filed["years"]
    assert years, "a held name with no filed years means the join is broken"
    assert [y["fiscalYear"] for y in years] == sorted(y["fiscalYear"] for y in years)
    # The point of the panel: reported and converted are both present, and the
    # rate that links them is on the row.
    latest = next(y for y in reversed(years) if y["revenueUsd"] is not None)
    assert latest["revenue"] != latest["revenueUsd"]
    assert latest["ratePerUsd"] > 0
    # Nothing here may reach the browser as a date object or a NaN.
    json.dumps(filed)


@needs_warehouse
def test_warehouse_reader_is_parameterised() -> None:
    """A ticker is a bound parameter, never interpolated into the statement."""
    assert warehouse.financials("' or 1=1 --") == []
    assert warehouse.quarterly("' or 1=1 --") == []


# ── Long-run quarterly revenue ───────────────────────────────────────────────
# The EDGAR reader is the piece most able to go quietly wrong: it classifies
# periods by arithmetic on dates and invents the quarter a 10-K filer never
# files. Both are tested on fixtures rather than over the network.


def _facts(tag: str, rows: list[dict], namespace: str = "us-gaap") -> dict:
    return {namespace: {tag: {"units": {"USD": rows}}}}


def test_periods_are_classified_by_duration_not_by_label() -> None:
    """Yahoo's frames are sparse and tags change; the dates are what is reliable."""
    facts = _facts(
        "Revenues",
        [
            {"start": "2024-01-01", "end": "2024-03-31", "val": 10, "filed": "2024-04-20"},
            {"start": "2024-01-01", "end": "2024-12-31", "val": 44, "filed": "2025-02-10"},
            {"start": "2024-01-01", "end": "2024-01-31", "val": 3, "filed": "2024-02-10"},
        ],
    )
    quarters, years, currency = filings._collect(facts, "revenue")
    assert list(quarters.values()) == [10]
    assert list(years.values()) == [44]
    assert currency == "USD"
    # A month is neither, and is dropped rather than plotted as a quarter.
    assert len(quarters) + len(years) == 2


def test_a_restated_period_takes_its_latest_filed_value() -> None:
    facts = _facts(
        "Revenues",
        [
            {"start": "2024-01-01", "end": "2024-03-31", "val": 10, "filed": "2024-04-20"},
            {"start": "2024-01-01", "end": "2024-03-31", "val": 11, "filed": "2025-02-10"},
        ],
    )
    quarters, _, _ = filings._collect(facts, "revenue")
    assert list(quarters.values()) == [11]


def test_tags_are_merged_across_a_filers_history() -> None:
    """A company moves between revenue tags; the series must not break there."""
    facts = _facts(
        "Revenues", [{"start": "2015-01-01", "end": "2015-03-31", "val": 5, "filed": "2015-04-20"}]
    )
    facts["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"] = {
        "units": {"USD": [{"start": "2024-01-01", "end": "2024-03-31", "val": 10, "filed": "x"}]}
    }
    quarters, _, _ = filings._collect(facts, "revenue")
    assert sorted(quarters.values()) == [5, 10]


def test_a_banks_revenue_is_composed_from_its_two_halves() -> None:
    """A bank has no top line; what it calls revenue is two tags added."""
    facts = {
        "us-gaap": {
            "InterestIncomeExpenseNet": {
                "units": {
                    "USD": [{"start": "2024-01-01", "end": "2024-03-31", "val": 25, "filed": "x"}]
                }
            },
            "NoninterestIncome": {
                "units": {
                    "USD": [{"start": "2024-01-01", "end": "2024-03-31", "val": 24, "filed": "x"}]
                }
            },
        }
    }
    quarters, _ = filings._bank_revenue(facts, "USD")
    assert quarters == {("2024-01-01", "2024-03-31"): 49}


def test_only_one_half_of_a_bank_is_not_revenue() -> None:
    """Net interest income alone is about half the total — worse than a gap."""
    facts = {
        "us-gaap": {
            "InterestIncomeExpenseNet": {
                "units": {
                    "USD": [{"start": "2024-01-01", "end": "2024-03-31", "val": 25, "filed": "x"}]
                }
            }
        }
    }
    assert filings._bank_revenue(facts, "USD") == ({}, {})


def test_a_filer_that_tags_its_own_total_keeps_it() -> None:
    """Bank of America publishes `Revenues`; the composite must not overwrite it.

    Mixing a filer's own definition with a computed one across periods would put
    a step in the line that no filing accounts for.
    """
    revenue = {("2024-01-01", "2024-03-31"): 31.0}
    composite = {("2024-01-01", "2024-03-31"): 30.5, ("2024-04-01", "2024-06-30"): 32.0}
    for key, value in composite.items():
        revenue.setdefault(key, value)
    assert revenue[("2024-01-01", "2024-03-31")] == 31.0, "the filer's own figure wins"
    assert revenue[("2024-04-01", "2024-06-30")] == 32.0, "the gap is filled"


def test_the_unfiled_fourth_quarter_is_derived_from_the_year() -> None:
    """Three 10-Qs and a 10-K is the whole year; the fourth quarter is the remainder."""
    quarters = {
        ("2024-01-01", "2024-03-31"): 10.0,
        ("2024-04-01", "2024-06-30"): 11.0,
        ("2024-07-01", "2024-09-30"): 12.0,
    }
    years = {("2024-01-01", "2024-12-31"): 50.0}
    filled, derived = filings._with_fourth_quarters(quarters, years)

    assert len(filled) == 4
    key = ("2024-10-01", "2024-12-31")
    assert filled[key] == 17.0
    assert derived == {key}


def test_a_complete_year_derives_nothing() -> None:
    quarters = {
        ("2024-01-01", "2024-03-31"): 10.0,
        ("2024-04-01", "2024-06-30"): 11.0,
        ("2024-07-01", "2024-09-30"): 12.0,
        ("2024-10-01", "2024-12-31"): 17.0,
    }
    filled, derived = filings._with_fourth_quarters(quarters, {("2024-01-01", "2024-12-31"): 50.0})
    assert filled == quarters
    assert derived == set()


def test_a_gap_too_wide_to_be_a_quarter_is_not_invented() -> None:
    """Two published quarters and a year would imply a six-month "quarter"."""
    quarters = {
        ("2024-01-01", "2024-03-31"): 10.0,
        ("2024-04-01", "2024-06-30"): 11.0,
        ("2024-07-01", "2024-09-30"): 12.0,
    }
    # A year ending far past the last quarter leaves a span no quarter could fill.
    filled, derived = filings._with_fourth_quarters(quarters, {("2024-01-01", "2025-06-30"): 80.0})
    assert derived == set()
    assert filled == quarters


def test_edgar_is_skipped_without_a_user_agent(monkeypatch) -> None:
    """SEC requires an identifying User-Agent; without one the page uses Yahoo."""
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    assert not filings.available()
    assert filings.series("AAPL") == {
        "quarterly": [],
        "annual": [],
        "currency": "",
        "derived": 0,
        "cik": None,
    }


def test_one_currency_is_chosen_for_the_whole_series() -> None:
    """A filer can publish the same line in two currencies; only one is a series.

    Toyota's facts carry twenty-seven years of revenue in JPY and four years of
    the same line in USD, filed alongside for US readers. Mixing them puts ¥19T
    next to $191B on one axis.
    """
    facts = {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "JPY": [
                        {"start": "2024-01-01", "end": "2024-12-31", "val": 45e12, "filed": "x"},
                        {"start": "2023-01-01", "end": "2023-12-31", "val": 37e12, "filed": "x"},
                    ],
                    "USD": [
                        {"start": "2012-01-01", "end": "2012-12-31", "val": 2.2e11, "filed": "x"},
                    ],
                }
            }
        }
    }
    # JPY carries the most recent facts, so JPY is what the series is in.
    _, years, currency = filings._collect(facts, "revenue")
    assert currency == "JPY"
    assert sorted(years.values()) == [37e12, 45e12]


def test_other_lines_join_revenue_on_the_period_end() -> None:
    """Lines are often tagged with start dates a day or two apart."""
    revenue = {("2024-01-01", "2024-12-31"): 100.0}
    income = {("2024-01-02", "2024-12-31"): 12.0}
    gross = {("2024-01-03", "2024-12-31"): 40.0}
    points = filings._points(revenue, income, gross, set(), annual=True)
    assert points == [
        {
            "end": "2024-12-31",
            "label": "2024",
            "revenue": 100.0,
            "grossProfit": 40.0,
            "netIncome": 12.0,
            "derived": False,
        }
    ]


def test_overlapping_periods_of_one_cadence_are_dropped() -> None:
    """A changed year end leaves two "annual" periods a few months apart."""
    keys = [
        ("2023-01-01", "2023-12-31"),
        ("2024-04-01", "2025-03-31"),
        ("2024-01-01", "2024-12-31"),  # overlaps the one after it
    ]
    kept = filings._spaced(keys, filings.YEAR_DAYS[0])
    assert [key[1] for key in kept] == ["2023-12-31", "2025-03-31"]


@needs_warehouse
def test_warehouse_quarters_fill_their_missing_fourth() -> None:
    """The offline path derives the same quarter EDGAR's does."""
    points = market_data._warehouse_quarters("AAPL")
    assert len(points) > 40, "the marts should carry a decade of quarters"
    assert [p["end"] for p in points] == sorted(p["end"] for p in points)
    assert any(point["derived"] for point in points), "no fourth quarter was derived"
    assert all(point["revenue"] is not None for point in points)


@needs_warehouse
def test_a_listing_without_quarters_still_gets_a_history(monkeypatch) -> None:
    """A 20-F filer reports once a year; annual is the highest frequency it has.

    With EDGAR unreachable this falls to the warehouse, which is the same test
    of the fallback chain without depending on the network.
    """
    monkeypatch.delenv("SEC_EDGAR_USER_AGENT", raising=False)
    history = market_data.revenue_history("TM")

    assert history["files"], "a filer the warehouse holds must not read as unfiled"
    assert len(history["annual"]["points"]) >= 5
    assert history["default"] == "annual", "five quarters must not beat a decade of years"
    assert history["annual"]["source"]


def test_a_listing_that_files_nothing_says_so() -> None:
    """An index or a currency has no revenue, which is not the same as a failure."""
    history = market_data.revenue_history("")
    assert history["files"] is False
    assert history["quarterly"]["points"] == []
