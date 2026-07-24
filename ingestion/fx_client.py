"""FX client — historical & current exchange rates for USD normalization.

Primary: Frankfurter (no key) — https://api.frankfurter.dev/v1/
  - Latest:      /latest?base=USD&symbols=GBP,JPY
  - Historical:  /YYYY-MM-DD?base=USD&symbols=...
  - Time series: /YYYY-MM-DD..YYYY-MM-DD?base=USD&symbols=...

Every non-USD holding needs a daily USD rate to compute USD-normalized returns and to split
return into "business" vs "FX contribution" (KPI framework §10).

Known gap (Phase 0): Frankfurter serves the ~30 ECB reference currencies, which exclude TWD.
Unsupported symbols are filtered out with a warning so the run still produces the rates it can;
TSM's TWD→USD normalization needs an alternate source before Phase 4.
"""

from __future__ import annotations

import logging
from datetime import date

from .base_client import BaseClient
from .config_loader import bootstrap, non_usd_currencies

log = logging.getLogger(__name__)

#: Start of the FX history pulled by the entrypoint (covers the price history window).
DEFAULT_START = "2015-01-01"


class FxClient(BaseClient):
    source_name = "fx"
    base_url = "https://api.frankfurter.dev/v1"

    def supported_currencies(self) -> set[str]:
        """Currency codes Frankfurter actually serves."""
        return set(self._get("/currencies").json())

    def fetch_timeseries(self, base: str, symbols: list[str], start: str, end: str) -> dict:
        """Daily FX time series base→symbols over [start, end]; land raw."""
        payload = self._get(f"/{start}..{end}", base=base, symbols=",".join(sorted(symbols))).json()
        self._land(f"timeseries_{base}_{start}_{end}", payload)
        log.info(
            "FX %s→%s: %d dates", base, ",".join(sorted(symbols)), len(payload.get("rates", {}))
        )
        return payload

    def fetch_latest(self, base: str, symbols: list[str]) -> dict:
        """Latest FX rates base→symbols; land raw."""
        payload = self._get("/latest", base=base, symbols=",".join(sorted(symbols))).json()
        self._land(f"latest_{base}", payload)
        return payload


def main() -> None:
    """Land the daily USD-base FX history for every non-USD currency in the universe."""
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
