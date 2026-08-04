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


# ── Landing zone anchoring ───────────────────────────────────────────────────
# `raw_root` used to default to the relative "data/raw", which followed whatever
# directory the process started in. The hub launches its market API with
# `cwd=dashboard_hub/`, and that API's backfill worker calls straight into these
# clients — so a backfill requested from the UI landed 1.3 MB of Ferrari filings
# in `dashboard_hub/data/raw/`, where `load_raw.py` never looks. The request
# reported success, RACE joined companies.yml and the dbt seed, and the warehouse
# held zero facts for it.


def test_the_landing_zone_does_not_follow_the_working_directory(tmp_path, monkeypatch):
    from ingestion.base_client import REPO_ROOT, raw_root

    monkeypatch.delenv("RAW_DATA_DIR", raising=False)
    anchored = raw_root()

    monkeypatch.chdir(tmp_path)
    assert raw_root() == anchored, "landing zone moved with the CWD"
    assert raw_root() == REPO_ROOT / "data" / "raw"


def test_an_absolute_override_is_taken_as_given(monkeypatch, tmp_path):
    """The container sets RAW_DATA_DIR to an absolute path and means it."""
    from ingestion.base_client import raw_root

    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path / "landing"))
    assert raw_root() == tmp_path / "landing"


def test_a_relative_override_resolves_against_the_repo(monkeypatch, tmp_path):
    from ingestion.base_client import REPO_ROOT, raw_root

    monkeypatch.setenv("RAW_DATA_DIR", "scratch/raw")
    monkeypatch.chdir(tmp_path)
    assert raw_root() == REPO_ROOT / "scratch" / "raw"


def test_landed_files_go_under_the_anchored_root(tmp_path, monkeypatch):
    """The path a client actually writes to, not just the root it computes."""
    from ingestion.base_client import BaseClient

    monkeypatch.setenv("RAW_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    client = BaseClient.__new__(BaseClient)
    client.source_name = "sec_edgar"
    landed = client._land("companyfacts_CIK0001648416", {"ok": True})

    assert landed == tmp_path / "sec_edgar" / "companyfacts_CIK0001648416.json"
    assert landed.exists()
