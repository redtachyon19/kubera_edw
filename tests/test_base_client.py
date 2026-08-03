from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from ingestion.base_client import BaseClient, _is_retryable, raw_root


class _Dummy(BaseClient):
    source_name = "dummy"
    base_url = "https://example.test"


def test_land_text_writes_verbatim() -> None:
    with _Dummy() as client:
        path = client._land_text("x", "a,b\n1,2")

    assert path.suffix == ".csv"
    assert path.read_text() == "a,b\n1,2"


def test_land_json_roundtrips() -> None:
    with _Dummy() as client:
        path = client._land("y", {"k": "v"})
    assert path.suffix == ".json"
    assert '"k": "v"' in path.read_text()


def test_raw_root_follows_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "elsewhere"))
    assert raw_root() == tmp_path / "elsewhere"


def test_is_fresh_semantics(tmp_path) -> None:
    missing = tmp_path / "nope.csv"
    assert not BaseClient._is_fresh(missing)

    empty = tmp_path / "empty.csv"
    empty.write_text("")
    assert not BaseClient._is_fresh(empty)

    fresh = tmp_path / "fresh.csv"
    fresh.write_text("data")
    assert BaseClient._is_fresh(fresh)

    stale = tmp_path / "stale.csv"
    stale.write_text("data")
    old = (datetime.now() - timedelta(days=3)).timestamp()
    os.utime(stale, (old, old))
    assert not BaseClient._is_fresh(stale, max_age_days=1)
    assert BaseClient._is_fresh(stale, max_age_days=7)


def test_retry_policy_distinguishes_transient_from_permanent() -> None:
    def status_error(code: int) -> httpx.HTTPStatusError:
        request = httpx.Request("GET", "https://example.test")
        return httpx.HTTPStatusError(
            "boom", request=request, response=httpx.Response(code, request=request)
        )

    assert not _is_retryable(status_error(404))
    assert not _is_retryable(status_error(400))
    assert _is_retryable(status_error(429))
    assert _is_retryable(status_error(503))
    assert _is_retryable(httpx.ConnectTimeout("timeout"))


def test_get_does_not_retry_on_404() -> None:
    with respx.mock:
        route = respx.get("https://example.test/missing").mock(return_value=httpx.Response(404))
        with _Dummy() as client, pytest.raises(httpx.HTTPStatusError):
            client._get("/missing")

    assert route.call_count == 1


def test_get_retries_and_recovers_on_500() -> None:
    with respx.mock:
        route = respx.get("https://example.test/flaky").mock(
            side_effect=[httpx.Response(500), httpx.Response(200, json={"ok": True})]
        )
        with _Dummy() as client:
            resp = client._get("/flaky")

    assert route.call_count == 2
    assert resp.json() == {"ok": True}
