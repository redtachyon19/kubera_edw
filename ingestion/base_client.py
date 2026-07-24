"""Shared HTTP base for all source clients.

Handles the concerns every free-tier API client needs: a polite User-Agent, self-throttling,
retry/backoff on transient failures, and landing raw responses to disk so the pipeline never
re-fetches unnecessarily (important for rate-limited sources like Alpha Vantage).

Subclasses implement source-specific extraction and call ``self._get(...)`` / ``self._land(...)``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

#: Default landing root. Resolved per-call via ``raw_root()`` so tests (and callers) can
#: redirect it by setting RAW_DATA_DIR without re-importing this module.
DEFAULT_RAW_ROOT = "data/raw"


def raw_root() -> Path:
    """Directory where raw responses are landed (override with the RAW_DATA_DIR env var)."""
    return Path(os.environ.get("RAW_DATA_DIR", DEFAULT_RAW_ROOT))


def _is_retryable(exc: BaseException) -> bool:
    """Retry transient failures only.

    Backing off on a 404 or a malformed request just burns the retry budget (and, on
    rate-limited sources, the daily quota) to arrive at the same error. Retry timeouts,
    connection resets, 5xx, and 429; surface every other 4xx immediately.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    return isinstance(exc, httpx.TransportError)


class BaseClient:
    #: Subclasses set this — used for the raw-landing subfolder and log context.
    source_name: str = "base"
    #: Base URL for the API.
    base_url: str = ""
    #: Minimum seconds between requests (self-throttle for sources without a hard limit).
    min_interval_s: float = 0.15

    def __init__(self, *, base_url: str | None = None) -> None:
        self.base_url = base_url or self.base_url
        self._last_request_ts = 0.0
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=self._default_headers(),
            timeout=30.0,
            follow_redirects=True,
        )

    # -- overridable hooks ---------------------------------------------------
    def _default_headers(self) -> dict[str, str]:
        """Default headers. SEC EDGAR overrides this to inject the required User-Agent."""
        return {"Accept": "application/json"}

    # -- request plumbing ----------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_request_ts = time.monotonic()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, max=30),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _get(self, path: str, **params: Any) -> httpx.Response:
        """GET with throttle + retry/backoff on transient failures.

        ``path`` may be relative (resolved against ``base_url``) or an absolute URL, which
        httpx uses as-is — needed where a source spans hosts (e.g. SEC's ticker map lives on
        www.sec.gov while the data APIs live on data.sec.gov).
        """
        self._throttle()
        resp = self._client.get(path, params=params or None)
        resp.raise_for_status()
        return resp

    # -- raw landing ---------------------------------------------------------
    def _land_path(self, name: str, ext: str = "json") -> Path:
        """Path a landed file would occupy: ``<raw_root>/<source>/<name>.<ext>``."""
        return raw_root() / self.source_name / f"{name}.{ext}"

    def _land(self, name: str, payload: Any) -> Path:
        """Persist a raw response under data/raw/<source>/<name>.json and return the path."""
        out_path = self._land_path(name, "json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        log.info("landed %s", out_path)
        return out_path

    def _land_text(self, name: str, text: str, ext: str = "csv") -> Path:
        """Persist a raw text/CSV response verbatim (no JSON encoding).

        Sources that return CSV must land as CSV — wrapping the body in a JSON string would
        break the Phase-2 staging models that read it with ``read_csv``.
        """
        out_path = self._land_path(name, ext)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text)
        log.info("landed %s", out_path)
        return out_path

    # -- caching -------------------------------------------------------------
    @staticmethod
    def _is_fresh(path: Path, max_age_days: float = 1.0) -> bool:
        """True if ``path`` exists, is non-empty, and was modified within ``max_age_days``.

        Free-tier quotas (Alpha Vantage's ~25 req/day especially) make re-fetching unchanged
        data the main way to break a pipeline run, so every rate-limited fetch gates on this.
        """
        if not path.exists() or path.stat().st_size == 0:
            return False
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        return datetime.now(UTC) - modified < timedelta(days=max_age_days)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BaseClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
