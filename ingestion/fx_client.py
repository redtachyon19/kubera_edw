"""FX client — historical & current exchange rates for USD normalization.

Primary: Frankfurter (no key) — https://api.frankfurter.dev/v1/
  - Latest:     /latest?base=USD&symbols=GBP,JPY,TWD
  - Historical: /YYYY-MM-DD?base=USD&symbols=...
  - Time series:/YYYY-MM-DD..YYYY-MM-DD?base=USD&symbols=...
Fallback: exchangerate.host (free key).

Every non-USD holding needs a daily USD rate to compute USD-normalized returns and to split
return into "business" vs "FX contribution" (KPI framework §10).
"""

from __future__ import annotations

from .base_client import BaseClient


class FxClient(BaseClient):
    source_name = "fx"
    base_url = "https://api.frankfurter.dev/v1"

    def fetch_timeseries(self, base: str, symbols: list[str], start: str, end: str) -> dict:
        """Daily FX time series base→symbols over [start, end]; land raw.

        TODO: self._get(f"/{start}..{end}", base=base, symbols=",".join(symbols)).
        """
        raise NotImplementedError

    def fetch_latest(self, base: str, symbols: list[str]) -> dict:
        """Latest FX rates base→symbols; land raw."""
        raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit("fx_client: not yet implemented (Phase 1).")
