"""Shared HTTP base for all source clients.

Handles the concerns every free-tier API client needs: a polite User-Agent, self-throttling,
retry/backoff on transient failures, and landing raw responses to disk so the pipeline never
re-fetches unnecessarily (important for rate-limited sources like Alpha Vantage).

Subclasses implement source-specific extraction and call ``self._get(...)`` / ``self._land(...)``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

RAW_ROOT = Path(os.environ.get("RAW_DATA_DIR", "data/raw"))


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

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=30))
    def _get(self, path: str, **params: Any) -> httpx.Response:
        """GET with throttle + retry/backoff. Raises on non-2xx after retries exhausted."""
        self._throttle()
        resp = self._client.get(path, params=params or None)
        resp.raise_for_status()
        return resp

    # -- raw landing ---------------------------------------------------------
    def _land(self, name: str, payload: Any) -> Path:
        """Persist a raw response under data/raw/<source>/<name>.json and return the path."""
        out_dir = RAW_ROOT / self.source_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{name}.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return out_path

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BaseClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
