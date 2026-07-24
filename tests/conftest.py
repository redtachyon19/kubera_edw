"""Shared pytest fixtures — mock API responses and sample payloads.

Tests here exercise the *code* (parsing, FX normalization, error handling) against mocked HTTP
responses, so `pytest tests/` runs fast with no network and no warehouse (see project_spec.md §8).
Use `respx` to stub httpx calls.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_sec_company_facts() -> dict:
    """A minimal SEC XBRL companyfacts payload shape (trimmed) for parser tests."""
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
def sample_fx_timeseries() -> dict:
    """A minimal Frankfurter time-series payload (base USD)."""
    return {
        "base": "USD",
        "start_date": "2023-01-02",
        "end_date": "2023-01-03",
        "rates": {
            "2023-01-02": {"GBP": 0.827, "JPY": 130.9},
            "2023-01-03": {"GBP": 0.831, "JPY": 131.2},
        },
    }
