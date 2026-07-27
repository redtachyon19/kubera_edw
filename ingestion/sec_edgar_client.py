"""SEC EDGAR client — company filings & XBRL financial facts.

Endpoints (see docs/project_spec.md §5.1):
  - Ticker map:    https://www.sec.gov/files/company_tickers.json
  - Submissions:   https://data.sec.gov/submissions/CIK##########.json
  - Company facts: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
  - XBRL Frames:   https://data.sec.gov/api/xbrl/frames/<ns>/<Concept>/USD/CY####Q#.json

Notes:
  - No API key, but a descriptive User-Agent header IS required (SEC_EDGAR_USER_AGENT).
  - Self-throttle to ~10 req/s.
  - XBRL tagging is not uniform across filers/years — the same economic concept appears under
    different tags, and the four 20-F filers (AZN, SHEL, TM, TSM) use the ifrs-full taxonomy
    rather than us-gaap. Both the tag list and the namespace are therefore tried in order;
    this mapping is explicit and documented rather than buried in a transform (§11).
"""

from __future__ import annotations

import json
import logging
import os

from .base_client import BaseClient
from .config_loader import bootstrap, cik_for, load_companies

log = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

#: XBRL namespaces tried in order: us-gaap for domestic 10-K filers, ifrs-full for the
#: foreign private issuers filing 20-F.
XBRL_NAMESPACES = ("us-gaap", "ifrs-full")

# Concept → candidate XBRL tags, in priority order (us-gaap first, ifrs-full parallels after).
CONCEPT_TAG_MAP: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        # ifrs-full parallels
        "Revenue",
        "RevenueFromContractsWithCustomers",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        # ifrs-full parallel
        "CostOfSales",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        # ifrs-full parallel
        "ProfitLossFromOperatingActivities",
    ],
    "net_income": [
        "NetIncomeLoss",
        # ifrs-full parallel (also valid us-gaap in some filings)
        "ProfitLoss",
    ],
    "total_debt": [
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        # ifrs-full parallel
        "Borrowings",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        # ifrs-full parallel
        "CashAndCashEquivalents",
    ],
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

    # -- ticker → CIK --------------------------------------------------------
    def _ticker_map(self) -> dict[str, str]:
        """Ticker → zero-padded CIK, from SEC's company_tickers.json (cached 7 days)."""
        cache = self._land_path("company_tickers")
        if self._is_fresh(cache, max_age_days=7):
            payload = json.loads(cache.read_text())
        else:
            payload = self._get(TICKER_MAP_URL).json()
            self._land("company_tickers", payload)
        # Payload is {"0": {"cik_str": 320193, "ticker": "AAPL", "title": ...}, ...}
        return {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in payload.values()}

    def resolve_cik(self, ticker: str) -> str:
        """Resolve a ticker to a zero-padded 10-digit CIK. Raises on miss — never guesses.

        Note this resolves whatever entity SEC currently maps the ticker to, which is not
        always the entity holding the financial history (XOM now maps to a reorg holdco with
        no 10-K). Prefer a scope-locked CIK from companies.yml where one exists.
        """
        mapping = self._ticker_map()
        cik = mapping.get(ticker.upper())
        if not cik:
            raise LookupError(f"ticker {ticker!r} not found in SEC company_tickers.json")
        return cik

    def cik_for_company(self, company: dict) -> str:
        """Pinned CIK from companies.yml if present, else resolve from the ticker."""
        pinned = cik_for(company)
        if pinned:
            return pinned
        log.warning("no pinned CIK for %s — falling back to ticker resolution", company["ticker"])
        return self.resolve_cik(company["ticker"])

    # -- financial facts -----------------------------------------------------
    def fetch_company_facts(self, cik: str) -> dict:
        """GET companyfacts for a CIK, land raw, return parsed JSON."""
        cik = str(cik).zfill(10)
        payload = self._get(f"/api/xbrl/companyfacts/CIK{cik}.json").json()
        self._land(f"companyfacts_CIK{cik}", payload)
        return payload

    def fetch_concept_frame(self, concept: str, period: str, *, unit: str = "USD") -> dict:
        """XBRL Frames: one concept across all filers for a period (e.g. 'CY2023Q4').

        Walks every (namespace, tag) pair for the concept and returns the first that yields
        rows, landing it as-is. Raises LookupError if no combination resolves.
        """
        if concept not in CONCEPT_TAG_MAP:
            raise KeyError(f"unknown concept {concept!r}; known: {sorted(CONCEPT_TAG_MAP)}")

        for namespace in XBRL_NAMESPACES:
            for tag in CONCEPT_TAG_MAP[concept]:
                path = f"/api/xbrl/frames/{namespace}/{tag}/{unit}/{period}.json"
                try:
                    payload = self._get(path).json()
                except Exception as exc:  # noqa: BLE001 — any miss just means "try next tag"
                    log.debug("frames miss %s/%s: %s", namespace, tag, exc)
                    continue
                if payload.get("data"):
                    self._land(f"frame_{concept}_{namespace}_{tag}_{period}", payload)
                    log.info(
                        "concept %s resolved via %s:%s for %s (%d rows)",
                        concept,
                        namespace,
                        tag,
                        period,
                        len(payload["data"]),
                    )
                    return payload
        raise LookupError(f"no XBRL tag resolved for concept {concept!r} in period {period!r}")


def main() -> None:
    """Land companyfacts for every company in the universe."""
    bootstrap()
    companies = load_companies()
    resolved: dict[str, str] = {}

    with SecEdgarClient() as client:
        for company in companies:
            ticker = company["ticker"]
            cik = client.cik_for_company(company)
            resolved[ticker] = cik
            log.info("fetching companyfacts for %s (CIK %s)", ticker, cik)
            client.fetch_company_facts(cik)
        # Cache the ticker→CIK resolution for later backfill/audit against companies.yml.
        client._land("resolved_ciks", resolved)

    log.info("done — landed companyfacts for %d companies", len(resolved))


if __name__ == "__main__":
    main()
