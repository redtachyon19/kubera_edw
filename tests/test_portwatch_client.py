"""IMF PortWatch extraction.

The tests worth having here are the ones that guard the things which fail
*silently*: ArcGIS paging that stops one page early, the date field that is a
string where every other ArcGIS date is epoch milliseconds, and the two columns
named after SQL keywords.
"""

from __future__ import annotations

from datetime import date

import httpx
import pandas as pd
import respx

from ingestion.portwatch_client import (
    HISTORY_START,
    PortWatchClient,
    _month_bounds,
    _months,
    _normalise,
    fetch_daily,
    fetch_reference,
)

ORG = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services"


def _page(rows: list[dict], *, more: bool = False) -> dict:
    payload: dict = {"features": [{"attributes": row} for row in rows]}
    if more:
        payload["exceededTransferLimit"] = True
    return payload


def test_walk_follows_exceeded_transfer_limit() -> None:
    """Paging must continue while the server says there is more.

    A full page is indistinguishable from a final one by row count alone, so
    `exceededTransferLimit` is the only safe end-of-walk signal. Getting this
    wrong truncates a 5.7M-row backfill quietly.
    """
    with respx.mock:
        respx.get(url__startswith=f"{ORG}/Daily_Ports_Data").mock(
            side_effect=[
                httpx.Response(200, json=_page([{"portid": "port1"}], more=True)),
                httpx.Response(200, json=_page([{"portid": "port2"}], more=True)),
                httpx.Response(200, json=_page([{"portid": "port3"}])),
            ]
        )
        with PortWatchClient() as client:
            pages = list(client.walk("Daily_Ports_Data"))

    assert [row["portid"] for page in pages for row in page] == ["port1", "port2", "port3"]


def test_walk_stops_without_the_flag() -> None:
    """No flag means the walk is done, even on a page that happens to be full."""
    with respx.mock:
        route = respx.get(url__startswith=f"{ORG}/Daily_Ports_Data").mock(
            return_value=httpx.Response(200, json=_page([{"portid": "port1"}]))
        )
        with PortWatchClient() as client:
            pages = list(client.walk("Daily_Ports_Data"))

    assert route.call_count == 1
    assert len(pages) == 1


def test_walk_raises_on_an_arcgis_error_envelope() -> None:
    """ArcGIS answers a bad query with HTTP 200 and an `error` body."""
    with respx.mock:
        respx.get(url__startswith=f"{ORG}/Daily_Ports_Data").mock(
            return_value=httpx.Response(200, json={"error": {"message": "Invalid field: nope"}})
        )
        with PortWatchClient() as client:
            try:
                list(client.walk("Daily_Ports_Data"))
            except RuntimeError as exc:
                assert "Invalid field" in str(exc)
            else:  # pragma: no cover — the assertion below reports the failure
                raise AssertionError("a 200-with-error body must raise")


def test_normalise_renames_the_sql_keyword_columns() -> None:
    """`import` and `export` are landed under names SQL can use unquoted."""
    frame = _normalise(
        pd.DataFrame([{"date": "2026-07-01", "import": 5, "export": 7, "ObjectId": 3}])
    )
    assert list(frame.columns) == ["date", "import_tons", "export_tons", "source_row_id"]


def test_normalise_lowercases_mixed_case_columns() -> None:
    """PortWatch ships `ISO3` and `vessel_count_RoRo`; the warehouse wants neither."""
    frame = _normalise(pd.DataFrame([{"ISO3": "SGP", "vessel_count_RoRo": 2}]))
    assert list(frame.columns) == ["iso3", "vessel_count_roro"]


def test_month_windows_are_contiguous_and_inclusive() -> None:
    windows = _months(date(2019, 11, 1), date(2020, 2, 15))
    assert windows == [(2019, 11), (2019, 12), (2020, 1), (2020, 2)]


def test_month_bounds_roll_over_the_year() -> None:
    assert _month_bounds(2026, 12) == ("2026-12-01", "2027-01-01")
    assert _month_bounds(2026, 1) == ("2026-01-01", "2026-02-01")


def test_history_starts_where_portwatch_does() -> None:
    assert HISTORY_START == date(2019, 1, 1)


def test_fetch_daily_skips_months_already_on_disk(tmp_path, monkeypatch) -> None:
    """A resumed backfill must not re-fetch what it already has.

    This is what makes a 1,500-request cold start restartable, and what keeps
    the weekly refresh down to a couple of dozen calls.
    """
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))

    with respx.mock:
        route = respx.get(url__startswith=f"{ORG}/Daily_Chokepoints_Data").mock(
            return_value=httpx.Response(
                200, json=_page([{"portid": "chokepoint1", "date": "2026-01-05"}])
            )
        )
        with PortWatchClient() as client:
            first = fetch_daily(
                client,
                "chokepoint_daily",
                "Daily_Chokepoints_Data",
                start=date(2026, 1, 1),
                refresh_months=0,
            )
            calls_after_first = route.call_count

            second = fetch_daily(
                client,
                "chokepoint_daily",
                "Daily_Chokepoints_Data",
                start=date(2026, 1, 1),
                refresh_months=0,
            )

    assert first
    assert second == {}, "a completed month must not be fetched twice"
    assert route.call_count == calls_after_first


def test_fetch_daily_always_refreshes_the_trailing_months(tmp_path, monkeypatch) -> None:
    """PortWatch grows the newest month after it is first written."""
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))

    with respx.mock:
        respx.get(url__startswith=f"{ORG}/Daily_Chokepoints_Data").mock(
            return_value=httpx.Response(
                200, json=_page([{"portid": "chokepoint1", "date": "2026-01-05"}])
            )
        )
        with PortWatchClient() as client:
            fetch_daily(
                client,
                "chokepoint_daily",
                "Daily_Chokepoints_Data",
                start=date(2026, 1, 1),
                refresh_months=0,
            )
            again = fetch_daily(
                client,
                "chokepoint_daily",
                "Daily_Chokepoints_Data",
                start=date(2026, 1, 1),
                refresh_months=2,
            )

    assert again, "the trailing window must be re-fetched"


def test_fetch_reference_clears_stale_parts(tmp_path, monkeypatch) -> None:
    """A shorter run must not leave the tail of a longer one behind.

    Without this, a chunked reference table that shrinks between runs is read as
    a mixture of two vintages — and nothing about the result looks wrong.
    """
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    stale = tmp_path / "portwatch" / "trade_ribbons"
    stale.mkdir(parents=True)
    (stale / "trade_ribbons.0099.parquet").write_bytes(b"not really parquet")

    with respx.mock:
        respx.get(url__startswith=f"{ORG}/spillovers_trade").mock(
            return_value=httpx.Response(200, json=_page([{"from_portid": "port1"}]))
        )
        with PortWatchClient() as client:
            fetch_reference(client, "trade_ribbons", "spillovers_trade", chunk_pages=1)

    assert not (stale / "trade_ribbons.0099.parquet").exists()
    assert (stale / "trade_ribbons.0000.parquet").exists()
