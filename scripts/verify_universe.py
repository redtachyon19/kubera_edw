"""Verify a candidate coverage universe against the sources that actually feed the warehouse.

Phase 0 established that three attributes must be READ FROM FILINGS, never inferred:

  * reporting currency — AstraZeneca, Shell and Infosys are foreign issuers that nonetheless
    file with the SEC in USD, so domicile does not imply reporting currency;
  * XBRL taxonomy — Alibaba files a 20-F but tags under us-gaap, so filer type does not imply
    taxonomy, and Toyota MIGRATED namespaces mid-history;
  * CIK — the ticker map can point at a reorg successor holding no financial history, as it
    does for XOM.

Doing that by hand for ~40 names is not viable, so this script does it in one throttled pass and
reports what each candidate would contribute — including whether its country has World Bank
macro coverage and its currency is served by Frankfurter, the two gaps that removed Taiwan.

It only REPORTS. It never edits companies.yml.

Usage:
    python scripts/verify_universe.py                 # verify the full spec universe (§6)
    python scripts/verify_universe.py AAPL MSFT ...   # verify specific tickers
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.base_client import BaseClient  # noqa: E402
from ingestion.config_loader import bootstrap  # noqa: E402
from ingestion.fx_client import FxClient  # noqa: E402
from ingestion.sec_edgar_client import SecEdgarClient  # noqa: E402

SPEC = Path(__file__).resolve().parent.parent / "docs" / "project_spec.md"

#: Country name in the spec -> ISO-3166 alpha-3, for the macro/FX coverage checks.
ISO3 = {
    "United States": "USA",
    "Mexico": "MEX",
    "United Kingdom": "GBR",
    "France": "FRA",
    "Netherlands": "NLD",
    "Netherlands/UK": "GBR",
    "Switzerland": "CHE",
    "Germany": "DEU",
    "Japan": "JPN",
    "Taiwan": "TWN",
    "South Korea": "KOR",
    "China": "CHN",
    "India": "IND",
    "Australia": "AUS",
    "Brazil": "BRA",
}
#: Domestic currency by ISO3.
CURRENCY = {
    "USA": "USD",
    "MEX": "MXN",
    "GBR": "GBP",
    "FRA": "EUR",
    "NLD": "EUR",
    "CHE": "CHF",
    "DEU": "EUR",
    "JPN": "JPY",
    "TWN": "TWD",
    "KOR": "KRW",
    "CHN": "CNY",
    "IND": "INR",
    "AUS": "AUD",
    "BRA": "BRL",
}


def spec_universe() -> list[dict]:
    """Parse the §6 coverage tables out of the specification."""
    text = SPEC.read_text()
    section = text[text.index("## 6. Company Universe") : text.index("## 7. Technology Stack")]
    rows = re.findall(
        r"^\| ([A-Za-z][^|]+?) \| ([A-Z]{1,5}) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$",
        section,
        re.M,
    )
    return [
        {
            "name": n.strip(),
            "ticker": t.strip(),
            "country": c.strip(),
            "sector": s.strip(),
            "filer_hint": "20-F" if "20-F" in f else "10-K",
        }
        for n, t, c, s, f in rows
    ]


def audit(client: SecEdgarClient, ticker: str) -> dict:
    """Resolve a ticker and read its real filer type, currency, taxonomy and fiscal year end."""
    out: dict = {"ticker": ticker, "status": "ok", "notes": []}
    try:
        cik = client.resolve_cik(ticker)
    except Exception as exc:  # noqa: BLE001
        return {**out, "status": "NO_CIK", "notes": [str(exc)[:80]]}
    out["cik"] = cik

    try:
        subs = client._get(f"/submissions/CIK{cik}.json").json()
    except Exception as exc:  # noqa: BLE001
        return {**out, "status": "NO_SUBMISSIONS", "notes": [str(exc)[:80]]}

    out["entity"] = subs.get("name", "")
    out["fiscal_year_end"] = subs.get("fiscalYearEnd") or ""
    recent = subs.get("filings", {}).get("recent", {})
    annuals = [
        (form, date)
        for form, date in zip(recent.get("form", []), recent.get("filingDate", []), strict=False)
        if form in ("10-K", "20-F")
    ]
    if not annuals:
        # The XOM pattern: the ticker resolves to an entity with no annual report at all.
        out["status"] = "NO_ANNUAL_FILING"
        out["notes"].append("ticker resolves to an entity with no 10-K/20-F")
        return out
    out["filer_type"], out["latest_annual"] = annuals[0]

    try:
        facts = client._get(f"/api/xbrl/companyfacts/CIK{cik}.json").json().get("facts", {})
    except Exception as exc:  # noqa: BLE001
        out["status"] = "NO_COMPANYFACTS"
        out["notes"].append(str(exc)[:80])
        return out

    # Reporting currency = the currency the monetary facts are actually denominated in.
    units: Counter = Counter()
    for taxonomy, concepts in facts.items():
        if taxonomy == "dei":
            continue
        for body in concepts.values():
            for unit, rows in body.get("units", {}).items():
                if len(unit) == 3 and unit.isalpha():
                    units[unit] += len(rows)
    out["currency_units"] = dict(units.most_common(3))
    out["reporting_currency"] = units.most_common(1)[0][0] if units else None

    taxonomies = [t for t in facts if t in ("us-gaap", "ifrs-full")]
    out["taxonomies"] = taxonomies
    out["xbrl_taxonomy"] = taxonomies[0] if taxonomies else None
    if not taxonomies:
        out["status"] = "NO_FINANCIAL_TAXONOMY"
        out["notes"].append("neither us-gaap nor ifrs-full present")
    if len(taxonomies) > 1:
        out["notes"].append(f"BOTH taxonomies present ({'+'.join(taxonomies)})")
    return out


def coverage_checks(iso3s: set[str], currencies: set[str]) -> tuple[set[str], set[str]]:
    """Which countries lack World Bank macro, and which currencies Frankfurter will not serve."""
    import httpx

    missing_macro = set()
    for iso3 in sorted(iso3s):
        # Space the calls. Firing these back-to-back trips a World Bank rate limit that
        # returns an empty body, which reads as "no coverage" — a FALSE NEGATIVE that
        # wrongly condemned Australia and Germany on the first run of this script.
        time.sleep(0.6)
        try:
            r = httpx.get(
                f"https://api.worldbank.org/v2/country/{iso3}/indicator/NY.GDP.MKTP.KD.ZG",
                params={"format": "json", "per_page": 5, "date": "2020:2023"},
                timeout=30,
            )
            payload = r.json()
            rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else None
        except Exception:  # noqa: BLE001
            rows = None
        if not rows:
            missing_macro.add(iso3)

    with FxClient() as fx:
        served = fx.supported_currencies()
    missing_fx = {c for c in currencies if c != "USD" and c not in served}
    return missing_macro, missing_fx


def main() -> None:
    bootstrap()
    BaseClient.min_interval_s = 0.11  # stay under SEC's ~10 req/s guidance

    wanted = sys.argv[1:]
    universe = spec_universe()
    if wanted:
        universe = [c for c in universe if c["ticker"] in wanted]

    print(f"Auditing {len(universe)} candidates against SEC EDGAR...\n")
    results = []
    with SecEdgarClient() as client:
        for i, cand in enumerate(universe, 1):
            res = audit(client, cand["ticker"])
            res.update(
                name=cand["name"],
                country=cand["country"],
                sector=cand["sector"],
                filer_hint=cand["filer_hint"],
                country_iso3=ISO3.get(cand["country"], "???"),
            )
            res["currency"] = CURRENCY.get(res["country_iso3"], "???")
            results.append(res)
            flag = "" if res["status"] == "ok" else f"  <-- {res['status']}"
            print(f"  [{i:2}/{len(universe)}] {cand['ticker']:6} {res['status']:22}{flag}")

    ok = [r for r in results if r["status"] == "ok"]
    print(f"\n{'=' * 78}\nVERIFIED ({len(ok)}/{len(results)})\n{'=' * 78}")
    print(f"{'tkr':6}{'cik':12}{'filer':7}{'rpt':5}{'taxonomy':11}{'fye':6}{'latest':12}notes")
    for r in sorted(ok, key=lambda x: x["ticker"]):
        note = "; ".join(r["notes"])
        mismatch = []
        if r["filer_type"] != r["filer_hint"]:
            mismatch.append(f"filer {r['filer_hint']}->{r['filer_type']}")
        if r["reporting_currency"] != r["currency"]:
            mismatch.append(f"ccy {r['currency']}->{r['reporting_currency']}")
        note = "; ".join(filter(None, [note, *mismatch]))
        print(
            f"{r['ticker']:6}{r['cik']:12}{r['filer_type']:7}{r['reporting_currency'] or '?':5}"
            f"{r['xbrl_taxonomy'] or '?':11}{r['fiscal_year_end']:6}{r['latest_annual']:12}{note}"
        )

    failed = [r for r in results if r["status"] != "ok"]
    if failed:
        print(f"\n{'=' * 78}\nEXCLUDED ({len(failed)})\n{'=' * 78}")
        for r in failed:
            print(f"  {r['ticker']:6} {r['status']:24} {'; '.join(r['notes'])}")

    iso3s = {r["country_iso3"] for r in ok}
    currencies = {r["currency"] for r in ok} | {
        r["reporting_currency"] for r in ok if r.get("reporting_currency")
    }
    missing_macro, missing_fx = coverage_checks(iso3s, currencies)
    print(f"\n{'=' * 78}\nDOWNSTREAM COVERAGE\n{'=' * 78}")
    print(f"  countries: {len(iso3s)}  no World Bank macro: {sorted(missing_macro) or 'none'}")
    print(
        f"  currencies: {len(currencies)}  "
        f"not served by Frankfurter: {sorted(missing_fx) or 'none'}"
    )
    blocked = [
        r["ticker"]
        for r in ok
        if r["reporting_currency"] in missing_fx or r["country_iso3"] in missing_macro
    ]
    print(f"  candidates hitting a coverage gap: {sorted(blocked) or 'none'}")

    out = Path("data/universe_audit.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\n  full audit written to {out}")


if __name__ == "__main__":
    main()
