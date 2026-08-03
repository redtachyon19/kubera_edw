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

DEFAULT_RAW_ROOT = "data/raw"


def raw_root() -> Path:
    return Path(os.environ.get("RAW_DATA_DIR", DEFAULT_RAW_ROOT))


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or 500 <= status < 600
    return isinstance(exc, httpx.TransportError)


class BaseClient:
    source_name: str = "base"
    base_url: str = ""
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

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

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
        self._throttle()
        resp = self._client.get(path, params=params or None)
        resp.raise_for_status()
        return resp

    def _land_path(self, name: str, ext: str = "json") -> Path:
        return raw_root() / self.source_name / f"{name}.{ext}"

    def _land(self, name: str, payload: Any) -> Path:
        out_path = self._land_path(name, "json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        log.info("landed %s", out_path)
        return out_path

    def _land_text(self, name: str, text: str, ext: str = "csv") -> Path:
        out_path = self._land_path(name, ext)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text)
        log.info("landed %s", out_path)
        return out_path

    @staticmethod
    def _is_fresh(path: Path, max_age_days: float = 1.0) -> bool:
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
