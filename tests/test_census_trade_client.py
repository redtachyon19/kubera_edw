"""US Census port-level trade extraction.

Two things about this source are unusual enough to pin down in tests: it answers
in arrays rather than objects, and it signals a missing key with a 302 to an HTML
page rather than a 4xx — so a bad key looks like success right up until the JSON
parse.
"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
import respx

from ingestion.census_trade_client import (
    CensusTradeClient,
    _months,
    _tidy,
    fetch_flow,
)

BASE = "https://api.census.gov/data/timeseries/intltrade"


def test_available_is_false_without_a_key(monkeypatch) -> None:
    """The whole layer switches off rather than failing the pipeline."""
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    with CensusTradeClient() as client:
        assert client.available() is False


def test_available_is_true_with_a_key(monkeypatch) -> None:
    monkeypatch.setenv("CENSUS_API_KEY", "abc123")
    with CensusTradeClient() as client:
        assert client.available() is True


def test_month_parses_array_of_arrays(monkeypatch) -> None:
    """The first row is the header; every later row is positional."""
    monkeypatch.setenv("CENSUS_API_KEY", "abc123")
    payload = [
        ["PORT", "PORT_NAME", "I_COMMODITY", "GEN_VAL_MO", "time"],
        ["2704", "Los Angeles, CA", "85", "8200000000", "2026-04"],
        ["2704", "Los Angeles, CA", "94", "1100000000", "2026-04"],
    ]
    with respx.mock:
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with CensusTradeClient() as client:
            frame = client.month("imports", "2026-04")

    assert list(frame.columns) == payload[0]
    assert len(frame) == 2
    assert frame.iloc[0]["I_COMMODITY"] == "85"


def test_month_returns_empty_on_a_non_json_body(monkeypatch) -> None:
    """Census answers a window it has no data for with HTML. That is a gap."""
    monkeypatch.setenv("CENSUS_API_KEY", "abc123")
    with respx.mock:
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(200, text="<html>no data</html>")
        )
        with CensusTradeClient() as client:
            assert client.month("imports", "1990-01").empty


def test_month_raises_when_the_key_is_rejected(monkeypatch) -> None:
    """A missing/invalid key redirects to an HTML page instead of erroring.

    Left undetected this reads as "Census has no data for every month", which is
    a far more confusing thing to debug than a rejected credential.
    """
    monkeypatch.setenv("CENSUS_API_KEY", "wrong")
    with respx.mock:
        # The real behaviour, reproduced: a 302 to an HTML page. The client
        # follows redirects, so it is the *final* URL that gives the game away.
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(
                302, headers={"Location": "https://api.census.gov/data/missing_key.html"}
            )
        )
        respx.get("https://api.census.gov/data/missing_key.html").mock(
            return_value=httpx.Response(200, text="<html>Missing Key</html>")
        )
        with CensusTradeClient() as client:
            try:
                client.month("imports", "2026-04")
            except RuntimeError as exc:
                assert "CENSUS_API_KEY" in str(exc)
            else:  # pragma: no cover
                raise AssertionError("a rejected key must raise")


def test_tidy_normalises_both_directions() -> None:
    """Imports and exports arrive under different value columns and must union."""
    imports = _tidy(
        pd.DataFrame(
            [
                {
                    "PORT": "2704",
                    "PORT_NAME": "LA",
                    "I_COMMODITY": "85",
                    "I_COMMODITY_SDESC": "Machinery",
                    "CTY_CODE": "5700",
                    "CTY_NAME": "China",
                    "GEN_VAL_MO": "100",
                    "VES_VAL_MO": "90",
                    "VES_WGT_MO": "5",
                    "CNT_VAL_MO": "80",
                }
            ]
        ),
        "imports",
        "2026-04",
    )
    exports = _tidy(
        pd.DataFrame(
            [
                {
                    "PORT": "5301",
                    "PORT_NAME": "Houston",
                    "E_COMMODITY": "27",
                    "E_COMMODITY_SDESC": "Mineral fuels",
                    "CTY_CODE": "5700",
                    "CTY_NAME": "China",
                    "ALL_VAL_MO": "200",
                    "VES_VAL_MO": "190",
                    "VES_WGT_MO": "9",
                    "CNT_VAL_MO": "10",
                }
            ]
        ),
        "exports",
        "2026-04",
    )

    assert list(imports.columns) == list(exports.columns)
    assert imports.iloc[0]["flow"] == "import"
    assert exports.iloc[0]["flow"] == "export"
    assert imports.iloc[0]["value_usd"] == 100
    assert exports.iloc[0]["value_usd"] == 200
    assert imports.iloc[0]["hs_chapter_name"] == "Machinery"


def test_tidy_keeps_the_leading_zero_on_a_chapter() -> None:
    """HS chapter 01 must not become the integer 1 — the seed joins on text."""
    frame = _tidy(
        pd.DataFrame(
            [
                {
                    "PORT": "1",
                    "PORT_NAME": "x",
                    "I_COMMODITY": "1",
                    "CTY_CODE": "1",
                    "CTY_NAME": "y",
                    "GEN_VAL_MO": "5",
                }
            ]
        ),
        "imports",
        "2026-04",
    )
    assert frame.iloc[0]["hs_chapter"] == "01"


def test_month_windows_run_to_the_present() -> None:
    windows = _months(date(2025, 11, 1), date(2026, 2, 1))
    assert windows == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_fetch_flow_skips_months_already_landed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CENSUS_API_KEY", "abc123")
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    payload = [
        ["PORT", "PORT_NAME", "I_COMMODITY", "CTY_CODE", "CTY_NAME", "GEN_VAL_MO"],
        ["2704", "Los Angeles, CA", "85", "5700", "China", "8200000000"],
    ]
    with respx.mock:
        route = respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with CensusTradeClient() as client:
            first = fetch_flow(client, "imports", start=date(2026, 1, 1), refresh_months=0)
            calls = route.call_count
            second = fetch_flow(client, "imports", start=date(2026, 1, 1), refresh_months=0)

    assert first
    assert second == {}
    assert route.call_count == calls
