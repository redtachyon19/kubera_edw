from __future__ import annotations

import json
import logging
import os

from .base_client import BaseClient
from .config_loader import api_key as get_api_key
from .config_loader import bootstrap, price_tickers

log = logging.getLogger(__name__)

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
CACHE_MAX_AGE_DAYS = 1.0
EXPECTED_CSV_HEADER = "Date,Open,High,Low,Close"
STOOQ_CHALLENGE_MARKERS = ("requires JavaScript", "__verify")
DEFAULT_BACKEND = "alpha_vantage"
DAILY_REQUEST_BUDGET = int(os.environ.get("PRICES_REQUEST_BUDGET", "20"))


class PricesClient(BaseClient):
    source_name = "prices"
    base_url = "https://stooq.com"
    min_interval_s = 1.3

    def fetch_daily_stooq(self, ticker: str, *, force: bool = False) -> str:
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

    def fetch_daily_alpha_vantage(
        self,
        ticker: str,
        *,
        force: bool = False,
        adjusted: bool = False,
        outputsize: str = "compact",
    ) -> dict:
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

        for key in ("Note", "Information", "Error Message"):
            if key in payload:
                raise RuntimeError(f"Alpha Vantage {key} for {ticker!r}: {payload[key]}")
        if "Time Series (Daily)" not in payload:
            raise ValueError(f"Alpha Vantage returned no time series for {ticker!r}")

        self._land(f"av_{ticker.upper()}", payload)
        log.info("%s: %d trading days", ticker, len(payload["Time Series (Daily)"]))
        return payload

    def fetch_daily(self, ticker: str, *, backend: str = DEFAULT_BACKEND, **kwargs):
        if backend == "stooq":
            return self.fetch_daily_stooq(ticker, **kwargs)
        if backend == "alpha_vantage":
            return self.fetch_daily_alpha_vantage(ticker, **kwargs)
        raise ValueError(f"unknown prices backend {backend!r} (stooq | alpha_vantage)")


def main() -> None:
    bootstrap()
    tickers = price_tickers()
    backend = os.environ.get("PRICES_BACKEND", DEFAULT_BACKEND)

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
            except Exception as exc:  # noqa: BLE001
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
