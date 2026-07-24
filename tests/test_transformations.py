"""Tests for pure transformation helpers (FX normalization, return math, concept mapping).

These cover logic that is easier to unit-test in Python than in dbt (e.g. edge cases in FX
normalization and daily-return calculation). Warehouse-level correctness is covered separately
by dbt-native tests under dbt/tests/.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Phase 4: add FX normalization + daily-return helpers, then test here.")
def test_local_to_usd_normalization() -> None:
    # e.g. close_local / rate_per_usd == close_usd, with forward-fill on non-trading days.
    ...


@pytest.mark.skip(reason="Phase 4: mixed quarterly/annual cadence must not be assumed uniform.")
def test_handles_annual_only_foreign_filer() -> None:
    ...
