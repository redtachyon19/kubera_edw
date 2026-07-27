from __future__ import annotations

import logging
from datetime import date

from .base_client import BaseClient
from .config_loader import bootstrap, non_usd_currencies

log = logging.getLogger(__name__)

DEFAULT_START = "2015-01-01"


class FxClient(BaseClient):
    source_name = "fx"
    base_url = "https://api.frankfurter.dev/v1"

    def supported_currencies(self) -> set[str]:
        return set(self._get("/currencies").json())

    def fetch_timeseries(self, base: str, symbols: list[str], start: str, end: str) -> dict:
        payload = self._get(f"/{start}..{end}", base=base, symbols=",".join(sorted(symbols))).json()
        self._land(f"timeseries_{base}_{start}_{end}", payload)
        log.info(
            "FX %s→%s: %d dates", base, ",".join(sorted(symbols)), len(payload.get("rates", {}))
        )
        return payload

    def fetch_latest(self, base: str, symbols: list[str]) -> dict:
        payload = self._get("/latest", base=base, symbols=",".join(sorted(symbols))).json()
        self._land(f"latest_{base}", payload)
        return payload


def main() -> None:
    bootstrap()
    wanted = non_usd_currencies()
    today = date.today().isoformat()

    with FxClient() as client:
        supported = client.supported_currencies()
        symbols = sorted(wanted & supported)
        missing = sorted(wanted - supported)
        if missing:
            log.warning(
                "not served by Frankfurter: %s — needs an alternate FX source (known gap)",
                ", ".join(missing),
            )
        if not symbols:
            log.warning("no supported currencies to fetch")
            return

        client.fetch_timeseries("USD", symbols, DEFAULT_START, today)
        client.fetch_latest("USD", symbols)

    log.info("done — FX landed for %s", ",".join(symbols))


if __name__ == "__main__":
    main()
