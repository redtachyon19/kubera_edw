"""Market price client — daily close prices for return / volatility / drawdown KPIs.

Backends (see docs/project_spec.md §5):
  - Alpha Vantage (free key, ~25 req/day) — DEFAULT. TIME_SERIES_DAILY is the free endpoint;
    TIME_SERIES_DAILY_ADJUSTED moved to Alpha Vantage's premium tier, so `adjusted=True` is
    opt-in and will fail on a free key.
  - Stooq (no key, bulk CSV) — DEGRADED as of 2026-07: stooq.com now gates the CSV endpoint
    behind a JavaScript proof-of-work bot check, returning an HTML challenge instead of data.
    Defeating bot detection is out of scope, so Stooq is detected and reported, not bypassed.

Free-tier limits mean prices are pulled in bulk and CACHED locally, not re-fetched every run
(§11): a fetch is skipped entirely while the landed file is still fresh. At 10 tickers, one
run costs 10 of Alpha Vantage's ~25 daily requests, so caching is what keeps reruns viable.

Both backends can fail with HTTP 200 and a non-data body (Stooq's challenge page, Alpha
Vantage's {"Note"|"Information"} rate-limit messages). Those are detected and raised so a
throttle or challenge response is never cached as if it were real data.
"""

from __future__ import annotations

import json
import logging
import os

from .base_client import BaseClient
from .config_loader import api_key as get_api_key
from .config_loader import bootstrap, price_tickers

log = logging.getLogger(__name__)

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
#: Daily prices change once per trading day — re-fetch at most daily.
CACHE_MAX_AGE_DAYS = 1.0
EXPECTED_CSV_HEADER = "Date,Open,High,Low,Close"
#: Marker text in Stooq's bot-verification interstitial.
STOOQ_CHALLENGE_MARKERS = ("requires JavaScript", "__verify")
DEFAULT_BACKEND = "alpha_vantage"
#: Requests to spend on prices in a single run. Alpha Vantage's free tier allows ~25/day and the
#: universe now needs more than that, so a run takes the freshest-needed slice and leaves the
#: rest for the next one. Combined with the freshness cache this rotates coverage across runs
#: rather than failing the tail of the ticker list every time.
DAILY_REQUEST_BUDGET = int(os.environ.get("PRICES_REQUEST_BUDGET", "20"))


class PricesClient(BaseClient):
    source_name = "prices"
    base_url = "https://stooq.com"
    # Alpha Vantage free tier enforces ~1 request/second in addition to the ~25/day cap;
    # firing faster returns an "Information" throttle message with HTTP 200, not a 429.
    min_interval_s = 1.3

    # -- Stooq (no key; currently bot-gated) ---------------------------------
    def fetch_daily_stooq(self, ticker: str, *, force: bool = False) -> str:
        """Bulk historical daily OHLCV from Stooq (CSV, no key); land raw.

        Returns the CSV text. Skips the network entirely when a fresh landing exists.
        """
        cache = self._land_path(ticker.upper(), "csv")
        if not force and self._is_fresh(cache, CACHE_MAX_AGE_DAYS):
            log.info("%s: cached (%s) — skipping fetch", ticker, cache.name)
            return cache.read_text()

        text = self._get("/q/d/l/", s=f"{ticker.lower()}.us", i="d").text

        if any(marker in text for marker in STOOQ_CHALLENGE_MARKERS):
            raise RuntimeError(
                f"Stooq served a bot-verification challenge for {ticker!r} instead of CSV. "
                "The endpoint now requires solving a JavaScript proof-of-work; use the "
                "alpha_vantage backend instead."
            )
        if not text.startswith(EXPECTED_CSV_HEADER):
            preview = text.strip()[:120].replace("\n", " ")
            raise ValueError(f"Stooq returned no usable CSV for {ticker!r}: {preview!r}")

        self._land_text(ticker.upper(), text, "csv")
        log.info("%s: %d rows", ticker, text.count("\n") - 1)
        return text

    # -- Alpha Vantage (free key, rate-limited) ------------------------------
    def fetch_daily_alpha_vantage(
        self,
        ticker: str,
        *,
        force: bool = False,
        adjusted: bool = False,
        outputsize: str = "compact",
    ) -> dict:
        """Daily series from Alpha Vantage; land raw.

        FREE-TIER LIMITS, both learned the hard way from HTTP 200 responses carrying an
        "Information" message rather than an error status:
          * ``outputsize="full"`` (20+ years) is a PREMIUM feature for TIME_SERIES_DAILY.
            The default here is "compact" — the latest ~100 trading days, which is what a
            free key can actually retrieve.
          * ``adjusted=True`` requests TIME_SERIES_DAILY_ADJUSTED, also premium.
        """
        api_key = get_api_key("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ALPHA_VANTAGE_API_KEY is not set (or is still the .env.example placeholder). "
                "Set a real key in .env to enable price extraction."
            )

        cache = self._land_path(f"av_{ticker.upper()}", "json")
        if not force and self._is_fresh(cache, CACHE_MAX_AGE_DAYS):
            log.info("%s: cached Alpha Vantage response — skipping fetch", ticker)
            return json.loads(cache.read_text())

        function = "TIME_SERIES_DAILY_ADJUSTED" if adjusted else "TIME_SERIES_DAILY"
        payload = self._get(
            ALPHA_VANTAGE_URL,
            function=function,
            symbol=ticker.upper(),
            apikey=api_key,
            outputsize=outputsize,
        ).json()

        # Rate limits and errors arrive as HTTP 200 with an explanatory key, not a bad status.
        for key in ("Note", "Information", "Error Message"):
            if key in payload:
                raise RuntimeError(f"Alpha Vantage {key} for {ticker!r}: {payload[key]}")
        if "Time Series (Daily)" not in payload:
            raise ValueError(f"Alpha Vantage returned no time series for {ticker!r}")

        self._land(f"av_{ticker.upper()}", payload)
        log.info("%s: %d trading days", ticker, len(payload["Time Series (Daily)"]))
        return payload

    def fetch_daily(self, ticker: str, *, backend: str = DEFAULT_BACKEND, **kwargs):
        """Fetch daily prices via the selected backend."""
        if backend == "stooq":
            return self.fetch_daily_stooq(ticker, **kwargs)
        if backend == "alpha_vantage":
            return self.fetch_daily_alpha_vantage(ticker, **kwargs)
        raise ValueError(f"unknown prices backend {backend!r} (stooq | alpha_vantage)")


def main() -> None:
    """Land daily prices for every held company plus the benchmarks."""
    bootstrap()
    tickers = price_tickers()
    backend = os.environ.get("PRICES_BACKEND", DEFAULT_BACKEND)

    # Check the credential ONCE up front. Without this the per-ticker loop below would log ten
    # identical "missing key" errors and then report a misleading 0/10 partial success, rather
    # than one clear "this source is not configured".
    if backend == "alpha_vantage" and not get_api_key("ALPHA_VANTAGE_API_KEY"):
        raise RuntimeError(
            "ALPHA_VANTAGE_API_KEY is not set (or is still the .env.example placeholder). "
            "Set a real key in .env to enable price extraction."
        )

    log.info("prices backend: %s (%d tickers)", backend, len(tickers))

    ok, cached, failed, deferred = 0, 0, [], []
    spent = 0
    with PricesClient() as client:
        for ticker in tickers:
            # A cached ticker costs no request, so it never counts against the budget.
            if client._is_fresh(
                client._land_path(f"av_{ticker.upper()}", "json"), CACHE_MAX_AGE_DAYS
            ):
                cached += 1
                continue
            if backend == "alpha_vantage" and spent >= DAILY_REQUEST_BUDGET:
                deferred.append(ticker)
                continue
            try:
                client.fetch_daily(ticker, backend=backend)
                spent += 1
                ok += 1
            except Exception as exc:  # noqa: BLE001 — one bad ticker shouldn't kill the run
                spent += 1
                log.error("%s: %s", ticker, exc)
                failed.append(ticker)

    log.info(
        "done — %d fetched, %d already cached, %d deferred, %d failed (of %d tickers; budget %d)",
        ok,
        cached,
        len(deferred),
        len(failed),
        len(tickers),
        DAILY_REQUEST_BUDGET,
    )
    if deferred:
        log.warning("deferred to a later run (free-tier daily cap): %s", ", ".join(deferred))
    if failed:
        log.warning("failed tickers: %s", ", ".join(failed))


if __name__ == "__main__":
    main()
