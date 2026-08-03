from __future__ import annotations

import json
import logging
import os

from .base_client import BaseClient
from .config_loader import bootstrap, cik_for, load_companies

log = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

XBRL_NAMESPACES = ("us-gaap", "ifrs-full")

CONCEPT_TAG_MAP: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenue",
        "RevenueFromContractsWithCustomers",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfSales",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "ProfitLossFromOperatingActivities",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "total_debt": [
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "Borrowings",
    ],
    "cash_and_equivalents": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashAndCashEquivalents",
    ],
}


class SecEdgarClient(BaseClient):
    source_name = "sec_edgar"
    base_url = "https://data.sec.gov"
    min_interval_s = 0.11

    def _default_headers(self) -> dict[str, str]:
        ua = os.environ.get("SEC_EDGAR_USER_AGENT")
        if not ua:
            raise RuntimeError(
                "SEC_EDGAR_USER_AGENT is required by SEC EDGAR. Set it in .env "
                '(format: "Name you@example.com").'
            )
        return {"User-Agent": ua, "Accept": "application/json"}

    def _ticker_map(self) -> dict[str, str]:
        cache = self._land_path("company_tickers")
        if self._is_fresh(cache, max_age_days=7):
            payload = json.loads(cache.read_text())
        else:
            payload = self._get(TICKER_MAP_URL).json()
            self._land("company_tickers", payload)
        return {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in payload.values()}

    def resolve_cik(self, ticker: str) -> str:
        mapping = self._ticker_map()
        cik = mapping.get(ticker.upper())
        if not cik:
            raise LookupError(f"ticker {ticker!r} not found in SEC company_tickers.json")
        return cik

    def cik_for_company(self, company: dict) -> str:
        pinned = cik_for(company)
        if pinned:
            return pinned
        log.warning("no pinned CIK for %s — falling back to ticker resolution", company["ticker"])
        return self.resolve_cik(company["ticker"])

    def fetch_company_facts(self, cik: str) -> dict:
        cik = str(cik).zfill(10)
        payload = self._get(f"/api/xbrl/companyfacts/CIK{cik}.json").json()
        self._land(f"companyfacts_CIK{cik}", payload)
        return payload

    def fetch_concept_frame(self, concept: str, period: str, *, unit: str = "USD") -> dict:
        if concept not in CONCEPT_TAG_MAP:
            raise KeyError(f"unknown concept {concept!r}; known: {sorted(CONCEPT_TAG_MAP)}")

        for namespace in XBRL_NAMESPACES:
            for tag in CONCEPT_TAG_MAP[concept]:
                path = f"/api/xbrl/frames/{namespace}/{tag}/{unit}/{period}.json"
                try:
                    payload = self._get(path).json()
                except Exception as exc:  # noqa: BLE001
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
        client._land("resolved_ciks", resolved)

    log.info("done — landed companyfacts for %d companies", len(resolved))


if __name__ == "__main__":
    main()
