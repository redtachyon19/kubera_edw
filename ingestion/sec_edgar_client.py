"""SEC EDGAR client — company filings & XBRL financial facts.

Endpoints (see docs/project_spec.md §5.1):
  - Submissions:  https://data.sec.gov/submissions/CIK##########.json
  - Company facts: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
  - XBRL Frames:  https://data.sec.gov/api/xbrl/frames/us-gaap/<Concept>/USD/CY####Q#.json

Notes:
  - No API key, but a descriptive User-Agent header IS required (SEC_EDGAR_USER_AGENT).
  - Self-throttle to ~10 req/s.
  - XBRL tagging is not uniform across filers/years — the same economic concept can appear
    under different tags. Concept mapping/fallback logic belongs here (documented, not hidden).
    Foreign private issuers (20-F) use ifrs-full tags rather than us-gaap.
"""

from __future__ import annotations

import os

from .base_client import BaseClient

# Concept → candidate XBRL tags, in priority order. Extend as coverage grows.
CONCEPT_TAG_MAP: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    # TODO: cost_of_revenue, total_debt, cash_and_equivalents, headcount ...
}


class SecEdgarClient(BaseClient):
    source_name = "sec_edgar"
    base_url = "https://data.sec.gov"
    min_interval_s = 0.11  # ~9 req/s, under the ~10 req/s self-throttle guideline

    def _default_headers(self) -> dict[str, str]:
        ua = os.environ.get("SEC_EDGAR_USER_AGENT")
        if not ua:
            raise RuntimeError(
                "SEC_EDGAR_USER_AGENT is required by SEC EDGAR. Set it in .env "
                '(format: "Name you@example.com").'
            )
        return {"User-Agent": ua, "Accept": "application/json"}

    def resolve_cik(self, ticker: str) -> str:
        """Resolve a ticker to a zero-padded 10-digit CIK via the SEC ticker map.

        TODO: fetch https://www.sec.gov/files/company_tickers.json once, cache, and look up.
        Fail loudly on miss rather than guessing.
        """
        raise NotImplementedError

    def fetch_company_facts(self, cik: str) -> dict:
        """GET companyfacts for a CIK, land raw, return parsed JSON.

        TODO: call self._get(f"/api/xbrl/companyfacts/CIK{cik}.json"), self._land(...).
        """
        raise NotImplementedError

    def fetch_concept_frame(self, concept: str, period: str) -> dict:
        """XBRL Frames: one concept across all filers for a period (e.g. 'CY2023Q4').

        TODO: iterate CONCEPT_TAG_MAP[concept] tags until one returns data.
        """
        raise NotImplementedError


if __name__ == "__main__":
    # TODO: load ingestion/config/companies.yml, resolve CIKs, land company facts.
    raise SystemExit("sec_edgar_client: not yet implemented (Phase 1).")
