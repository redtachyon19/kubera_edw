"""Company logos and country flags.

Nothing here reaches the network. What matters is that a hostile or malformed
identifier cannot escape the cache directory, that a non-image response is never
cached as one, and that a stale file is refetched rather than served forever.
"""

from __future__ import annotations

import json
import time

import pytest

from dashboard_hub.lib import imagery

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 120


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(imagery, "_CACHE_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def upstream(monkeypatch):
    """Record what was requested and answer with whatever the test wants."""
    calls: list[str] = []

    def install(answer):
        def fetch(url: str):
            calls.append(url)
            return answer(url) if callable(answer) else answer

        monkeypatch.setattr(imagery, "_fetch", fetch)
        return calls

    return install


# ── Identifier hygiene ───────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["../../etc/passwd", "a/b", "AA BB", "", "x" * 200 + "/.."])
def test_a_hostile_symbol_never_reaches_the_filesystem(bad, cache, upstream):
    calls = upstream((PNG, "image/png"))
    assert imagery.logo(bad) is None
    assert calls == [], "a rejected symbol must not cause a fetch either"
    assert list(cache.iterdir()) == []


@pytest.mark.parametrize("bad", ["../DEU", "JP", "JAPAN", "", "J/N"])
def test_a_malformed_country_code_is_refused(bad, cache, upstream):
    upstream((PNG, "image/png"))
    assert imagery.flag(bad) is None


def test_a_dot_in_a_ticker_is_kept_out_of_the_filename(cache, upstream, monkeypatch):
    """`7203.T` is a real ticker; the cache key must not gain an extension."""
    upstream((PNG, "image/png"))
    monkeypatch.setattr(imagery, "_domains", lambda: {"7203.T": "global.toyota"})

    assert imagery.logo("7203.T") is not None
    assert (cache / "logo_7203_T.bin").exists()


# ── Fetching and fallback ────────────────────────────────────────────────────


def test_the_second_source_is_tried_when_the_first_has_nothing(cache, upstream, monkeypatch):
    monkeypatch.setattr(imagery, "_domains", lambda: {"JPM": "jpmorganchase.com"})
    calls = upstream(lambda url: None if "google" in url else (PNG, "image/png"))

    found = imagery.logo("JPM")
    assert found == (PNG, "image/png")
    assert len(calls) == 2, "should have fallen through to the second service"
    assert "google" in calls[0] and "duckduckgo" in calls[1]


def test_a_company_with_no_domain_has_no_logo(cache, upstream, monkeypatch):
    monkeypatch.setattr(imagery, "_domains", lambda: {})
    calls = upstream((PNG, "image/png"))

    assert imagery.logo("AAPL") is None
    assert calls == []


def test_both_sources_failing_is_a_miss_not_a_crash(cache, upstream, monkeypatch):
    monkeypatch.setattr(imagery, "_domains", lambda: {"AAPL": "apple.com"})
    upstream(None)
    assert imagery.logo("AAPL") is None


# ── What counts as an image ──────────────────────────────────────────────────


def test_an_html_error_page_is_not_cached_as_a_logo(cache, monkeypatch):
    """The favicon services answer 200 with HTML when they have nothing."""
    monkeypatch.setattr(imagery, "_domains", lambda: {"AAPL": "apple.com"})

    class _Response:
        headers = {"Content-Type": "text/html; charset=UTF-8"}

        def read(self, _n=None):
            return b"<!doctype html><title>404</title>" + b" " * 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(imagery.urllib.request, "urlopen", lambda *a, **k: _Response())

    assert imagery.logo("AAPL") is None
    assert list(cache.iterdir()) == []


def test_a_one_pixel_answer_is_refused(cache, monkeypatch):
    monkeypatch.setattr(imagery, "_domains", lambda: {"AAPL": "apple.com"})

    class _Response:
        headers = {"Content-Type": "image/gif"}

        def read(self, _n=None):
            return b"GIF89a"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(imagery.urllib.request, "urlopen", lambda *a, **k: _Response())
    assert imagery.logo("AAPL") is None


# ── Caching ──────────────────────────────────────────────────────────────────


def test_a_logo_is_fetched_once_and_then_read_from_disk(cache, upstream, monkeypatch):
    monkeypatch.setattr(imagery, "_domains", lambda: {"AAPL": "apple.com"})
    calls = upstream((PNG, "image/png"))

    assert imagery.logo("AAPL") == (PNG, "image/png")
    assert imagery.logo("AAPL") == (PNG, "image/png")
    assert len(calls) == 1, "the second call must come off disk"


def test_the_content_type_survives_the_round_trip(cache, upstream, monkeypatch):
    """JPMorgan's mark comes back as a JPEG; serving it as PNG would break it."""
    monkeypatch.setattr(imagery, "_domains", lambda: {"JPM": "jpmorganchase.com"})
    upstream((PNG, "image/jpeg"))

    imagery.logo("JPM")
    assert imagery._read("logo_JPM")[1] == "image/jpeg"


def test_a_stale_file_is_refetched(cache, upstream, monkeypatch):
    monkeypatch.setattr(imagery, "_domains", lambda: {"AAPL": "apple.com"})
    calls = upstream((PNG, "image/png"))
    imagery.logo("AAPL")

    # Push the file's mtime back beyond the TTL.
    old = time.time() - imagery.TTL - 60
    import os

    os.utime(cache / "logo_AAPL.bin", (old, old))

    imagery.logo("AAPL")
    assert len(calls) == 2


def test_a_corrupt_meta_file_is_survivable(cache, upstream, monkeypatch):
    monkeypatch.setattr(imagery, "_domains", lambda: {"AAPL": "apple.com"})
    upstream((PNG, "image/png"))
    imagery.logo("AAPL")
    (cache / "logo_AAPL.json").write_text("{ not json")

    # Falls through to a refetch rather than raising.
    assert imagery.logo("AAPL") == (PNG, "image/png")


def test_flags_are_keyed_by_iso3_and_requested_by_iso2(cache, upstream, monkeypatch):
    monkeypatch.setattr(imagery, "_iso2", lambda: {"JPN": "JP"})
    calls = upstream((PNG, "image/png"))

    assert imagery.flag("JPN") == (PNG, "image/png")
    assert calls[0].endswith("/jp.png"), "flagcdn wants a lowercase two-letter code"
    assert json.loads((cache / "flag_JPN.json").read_text())["contentType"] == "image/png"
