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
    CHAPTERS,
    CensusTradeClient,
    _tidy,
    _window,
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


def test_chapter_parses_array_of_arrays(monkeypatch) -> None:
    """The first row is the header; every later row is positional."""
    monkeypatch.setenv("CENSUS_API_KEY", "a" * 40)
    payload = [
        ["PORT", "PORT_NAME", "I_COMMODITY", "GEN_VAL_MO", "time"],
        ["2704", "Los Angeles, CA", "85", "8200000000", "2026-04"],
        ["2704", "Los Angeles, CA", "85", "1100000000", "2026-05"],
    ]
    with respx.mock:
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with CensusTradeClient() as client:
            frame = client.chapter("imports", "85", "from 2026-01 to 2026-12")

    assert list(frame.columns) == payload[0]
    assert len(frame) == 2


def test_chapter_drops_the_echoed_filter_column(monkeypatch) -> None:
    """Census returns the filtered field twice — once from `get`, once as the filter.

    Undeduplicated, `frame["hs_chapter"]` is a two-column DataFrame rather than a
    Series and every downstream string operation raises.
    """
    monkeypatch.setenv("CENSUS_API_KEY", "a" * 40)
    payload = [
        ["PORT", "I_COMMODITY", "GEN_VAL_MO", "time", "I_COMMODITY"],
        ["2704", "27", "500", "2026-04", "27"],
    ]
    with respx.mock:
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with CensusTradeClient() as client:
            frame = client.chapter("imports", "27", "2026")

    assert list(frame.columns).count("I_COMMODITY") == 1


def test_chapter_treats_204_as_an_empty_window(monkeypatch) -> None:
    """A chapter no port handled returns 204, which is a gap and not a failure."""
    monkeypatch.setenv("CENSUS_API_KEY", "a" * 40)
    with respx.mock:
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(return_value=httpx.Response(204))
        with CensusTradeClient() as client:
            assert client.chapter("imports", "77", "2026").empty


def test_month_returns_empty_on_a_non_json_body(monkeypatch) -> None:
    """Census answers a window it has no data for with HTML. That is a gap."""
    monkeypatch.setenv("CENSUS_API_KEY", "abc123")
    with respx.mock:
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(200, text="<html>no data</html>")
        )
        with CensusTradeClient() as client:
            assert client.chapter("imports", "27", "1990").empty


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
                client.chapter("imports", "27", "2026")
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
                    "time": "2026-04",
                }
            ]
        ),
        "imports",
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
                    "time": "2026-04",
                }
            ]
        ),
        "exports",
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
                    "time": "2026-04",
                }
            ]
        ),
        "imports",
    )
    assert frame.iloc[0]["hs_chapter"] == "01"


def test_window_uses_census_range_syntax() -> None:
    """One call covers the whole history — 194 requests instead of 32,000."""
    assert _window(date(2013, 1, 1), date(2026, 8, 15)) == "from 2013-01 to 2026-08"


def test_chapter_sweep_covers_01_to_97() -> None:
    assert CHAPTERS[0] == "01" and CHAPTERS[-1] == "97" and len(CHAPTERS) == 97


def test_tidy_drops_the_all_countries_rollup() -> None:
    """Census ships a CTY_CODE='-' total beside the country rows.

    It equals their sum exactly, so leaving it in doubles every figure — which
    is invisible on inspection and wrong everywhere.
    """
    frame = _tidy(
        pd.DataFrame(
            [
                {
                    "PORT": "1",
                    "I_COMMODITY": "27",
                    "CTY_CODE": "5700",
                    "CTY_NAME": "China",
                    "GEN_VAL_MO": "60",
                    "time": "2026-04",
                },
                {
                    "PORT": "1",
                    "I_COMMODITY": "27",
                    "CTY_CODE": "4000",
                    "CTY_NAME": "France",
                    "GEN_VAL_MO": "40",
                    "time": "2026-04",
                },
                {
                    "PORT": "1",
                    "I_COMMODITY": "27",
                    "CTY_CODE": "-",
                    "CTY_NAME": "TOTAL FOR ALL COUNTRIES",
                    "GEN_VAL_MO": "100",
                    "time": "2026-04",
                },
            ]
        ),
        "imports",
    )
    assert len(frame) == 2
    assert frame["value_usd"].sum() == 100


def test_fetch_flow_lands_one_file_per_year(tmp_path, monkeypatch) -> None:
    """A single request spans years; storage splits them so refreshes stay cheap."""
    monkeypatch.setenv("CENSUS_API_KEY", "a" * 40)
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    payload = [
        ["PORT", "I_COMMODITY", "CTY_CODE", "CTY_NAME", "GEN_VAL_MO", "time"],
        ["2704", "27", "5700", "China", "100", "2024-06"],
        ["2704", "27", "5700", "China", "200", "2025-06"],
    ]
    with respx.mock:
        respx.get(url__startswith=f"{BASE}/imports/porths").mock(
            return_value=httpx.Response(200, json=payload)
        )
        with CensusTradeClient() as client:
            landed = fetch_flow(client, "imports", chapters=["27"])

    assert landed == {"27": 2}
    years = sorted(q.name for q in (tmp_path / "census_trade" / "imports").glob("*.parquet"))
    assert years == ["hs27_2024.parquet", "hs27_2025.parquet"]
