from __future__ import annotations

import pytest

from ingestion.base_client import BaseClient


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("SEC_EDGAR_USER_AGENT", "Kubera Test test@example.com")
    monkeypatch.setenv("FRED_API_KEY", "test-fred-key")
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-av-key")
    monkeypatch.setattr(BaseClient, "min_interval_s", 0.0)


@pytest.fixture
def sample_sec_company_facts() -> dict:
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "end": "2023-09-30",
                                "val": 383285000000,
                                "form": "10-K",
                                "fy": 2023,
                                "fp": "FY",
                            },
                        ]
                    }
                }
            }
        },
    }


@pytest.fixture
def sample_sec_ticker_map() -> dict:
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    }


@pytest.fixture
def sample_fx_timeseries() -> dict:
    return {
        "base": "USD",
        "start_date": "2023-01-02",
        "end_date": "2023-01-03",
        "rates": {
            "2023-01-02": {"GBP": 0.827, "JPY": 130.9},
            "2023-01-03": {"GBP": 0.831, "JPY": 131.2},
        },
    }


@pytest.fixture
def sample_world_bank_response() -> list:
    return [
        {"page": 1, "pages": 1, "per_page": 20000, "total": 2},
        [
            {
                "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
                "country": {"id": "US", "value": "United States"},
                "countryiso3code": "USA",
                "date": "2023",
                "value": 27360935000000,
            },
            {
                "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
                "country": {"id": "GB", "value": "United Kingdom"},
                "countryiso3code": "GBR",
                "date": "2023",
                "value": 3340032000000,
            },
        ],
    ]


@pytest.fixture
def sample_fred_observations() -> dict:
    return {
        "realtime_start": "2026-07-24",
        "observation_start": "2010-01-01",
        "count": 3,
        "observations": [
            {"date": "2023-01-03", "value": "1839.10"},
            {"date": "2023-01-04", "value": "1854.60"},
            {"date": "2023-01-05", "value": "."},
        ],
    }


@pytest.fixture
def sample_stooq_csv() -> str:
    return (
        "Date,Open,High,Low,Close,Volume\n"
        "2023-01-03,130.28,130.90,124.17,125.07,112117471\n"
        "2023-01-04,126.89,128.66,125.08,126.36,89113633\n"
    )
