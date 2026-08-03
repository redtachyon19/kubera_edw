from __future__ import annotations

import json
from pathlib import Path

from ingestion.base_client import raw_root
from ingestion.load_raw import (
    parse_fx,
    parse_gold,
    parse_imf,
    parse_prices,
    parse_sec_facts,
    parse_world_bank,
)


def _write(rel: str, payload: object) -> Path:
    path = raw_root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)
    return path


def test_parse_sec_facts_flattens_and_skips_dei(sample_sec_company_facts: dict) -> None:
    payload = dict(sample_sec_company_facts)
    payload["facts"] = dict(payload["facts"])
    payload["facts"]["dei"] = {
        "EntityCommonStockSharesOutstanding": {
            "units": {"shares": [{"end": "2023-09-30", "val": 1}]}
        }
    }
    _write("sec_edgar/companyfacts_CIK0000320193.json", payload)

    df = parse_sec_facts()
    assert set(df["taxonomy"]) == {"us-gaap"}
    row = df.iloc[0]
    assert row["cik"] == "0000320193"
    assert row["concept"] == "Revenues"
    assert row["unit"] == "USD"
    assert row["value"] == 383285000000
    assert row["form"] == "10-K"


def test_parse_sec_facts_handles_duplicate_keys() -> None:
    raw_json = """
    {"cik": 1577552, "entityName": "Alibaba",
     "facts": {"us-gaap": {"Revenues": {"units": {"CNY": [
        {"end": "2024-03-31", "val": 941168000000, "form": "20-F", "fy": 2024, "fp": "FY",
         "Segment": "a", "Segment": "b"}]}}}}}
    """
    _write("sec_edgar/companyfacts_CIK0001577552.json", raw_json)
    df = parse_sec_facts()
    assert len(df) == 1
    assert df.iloc[0]["unit"] == "CNY"


def test_parse_fx_unpivots_nested_rates(sample_fx_timeseries: dict) -> None:
    _write("fx/timeseries_USD_2023-01-02_2023-01-03.json", sample_fx_timeseries)
    df = parse_fx()
    assert len(df) == 4
    assert set(df["currency"]) == {"GBP", "JPY"}
    assert set(df["base_currency"]) == {"USD"}
    gbp = df[(df.rate_date == "2023-01-02") & (df.currency == "GBP")].iloc[0]
    assert gbp["rate_per_base"] == 0.827


def test_parse_world_bank_carries_load_provenance() -> None:
    _write(
        "world_bank/gdp_20260724.json",
        {
            "loaded_at": "2026-07-24T00:00:00+00:00",
            "indicator": "gdp",
            "indicator_code": "NY.GDP.MKTP.CD",
            "data": [
                {
                    "countryiso3code": "USA",
                    "country": {"value": "United States"},
                    "date": "2023",
                    "value": 27360935000000,
                }
            ],
        },
    )
    df = parse_world_bank()
    assert len(df) == 1
    assert df.iloc[0]["loaded_at"] == "2026-07-24T00:00:00+00:00"
    assert df.iloc[0]["country_iso3"] == "USA"


def test_parse_gold_preserves_missing_markers(sample_fred_observations: dict) -> None:
    _write("gold_price/gold_lbma_fixing.json", sample_fred_observations)
    df = parse_gold()
    assert len(df) == 3
    assert df[df.price_date == "2023-01-05"].iloc[0]["value_raw"] == "."


def test_parse_imf_tolerates_null_country_series() -> None:
    _write(
        "imf/gdp_growth_pct_NGDP_RPCH.json",
        {"values": {"NGDP_RPCH": {"USA": {"2023": 2.9}, "GBR": None}}},
    )
    df = parse_imf()
    assert len(df) == 1
    assert df.iloc[0]["country_iso3"] == "USA"


def test_parsers_return_empty_frames_when_nothing_landed() -> None:
    assert parse_gold().empty
    assert parse_prices().empty
