"""Long-run quarterly figures, read from SEC EDGAR at request time.

Yahoo publishes five quarters. A filer's own XBRL facts go back to whenever it
started tagging them — usually 2008 or 2009 — so a quarterly revenue chart that
reaches back two decades has to come from EDGAR rather than from the quote feed.

This is the same source the warehouse is built from, read live and for one
company at a time, which is a different job from the nightly pipeline in
`ingestion/`: no landing, no dbt, nothing persisted. It exists so the Company
Explorer can draw a long series for any filer, not only the 38 the warehouse
carries.

Two things make the raw facts unusable as they arrive:

Duration, not labels, says what a period is. The `frame` field EDGAR attaches is
sparse — NVIDIA has twelve framed quarters against sixty-six real ones — and a
company changes revenue tags over the years (`SalesRevenueNet` becomes
`Revenues` becomes `RevenueFromContractWithCustomerExcludingAssessedTax`). So
every fact under every candidate tag is collected and classified by how long its
period actually is.

And a 10-K filer never reports a fourth quarter. Three 10-Qs and an annual report
is the whole year, which leaves a hole every fourth point unless the missing
quarter is derived from the annual figure less the three that are published.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

BASE = "https://data.sec.gov"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

# Revenue and result, in the order they are preferred. A company appears under
# several of these across its history; all are read and merged by period.
CONCEPTS: dict[str, tuple[tuple[str, str], ...]] = {
    "revenue": (
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
        ("us-gaap", "Revenues"),
        ("us-gaap", "SalesRevenueNet"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
        ("ifrs-full", "Revenue"),
        ("ifrs-full", "RevenueFromContractsWithCustomers"),
    ),
    "netIncome": (
        ("us-gaap", "NetIncomeLoss"),
        ("ifrs-full", "ProfitLoss"),
        ("us-gaap", "ProfitLoss"),
    ),
    "grossProfit": (
        ("us-gaap", "GrossProfit"),
        ("ifrs-full", "GrossProfit"),
    ),
}

# A "quarter" and a "year" as reported: filers close on a 13-week or 52/53-week
# calendar, so neither lands on an exact day count.
QUARTER_DAYS = (80, 100)
YEAR_DAYS = (340, 380)

# SEC asks for no more than ten requests a second and a real User-Agent.
_MIN_INTERVAL = 0.12
_TIMEOUT = 20
_TTL = 24 * 3600
_MAP_TTL = 7 * 24 * 3600

_lock = threading.Lock()
_last_call = 0.0
_cache: dict[tuple, tuple[float, Any]] = {}


def available() -> bool:
    """True when SEC will accept our requests — it requires an identifying UA."""
    return bool(os.environ.get("SEC_EDGAR_USER_AGENT", "").strip())


def _cached(key: tuple, produce, ttl: int = _TTL, keep=None):
    """Memoise `produce` for `ttl` seconds, optionally only when `keep` holds.

    The guard matters more here than it looks. A tag a company never used and a
    request that failed both come back empty, and caching the second for a day
    would silently truncate a series — Ford's revenue stopped in 2022 for
    exactly that reason, one dropped request pinned as "this tag has nothing".
    """
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = produce()
    if keep is None or keep(value):
        _cache[key] = (now, value)
    return value


def _get(url: str, attempts: int = 2) -> dict | None:
    """One throttled GET, or None for anything that does not come back as JSON.

    A concept a company never tagged answers 404, which is ordinary here — the
    tag list is a set of candidates, not a set of expectations. A 403 or a
    timeout is not ordinary, so it is retried once before being given up on.
    """
    global _last_call
    agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    if not agent:
        return None

    request = urllib.request.Request(
        url, headers={"User-Agent": agent, "Accept": "application/json"}
    )
    for attempt in range(attempts):
        with _lock:
            wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # 404 is a tag this filer never used; asking again will not change it.
            if error.code == 404:
                return None
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            pass
        if attempt + 1 < attempts:
            time.sleep(0.5 * (attempt + 1))
    return None


def _ticker_map() -> dict[str, str]:
    """Every SEC filer's ticker to its zero-padded CIK."""

    def run() -> dict[str, str]:
        payload = _get(TICKER_MAP_URL)
        if not payload:
            return {}
        return {
            str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
            for row in payload.values()
            if row.get("ticker")
        }

    return _cached(("tickermap",), run, ttl=_MAP_TTL, keep=bool)


def resolve_cik(ticker: str, known: str | None = None) -> str | None:
    """The filer behind a ticker, preferring a CIK the warehouse already holds."""
    if known:
        return known.zfill(10)
    return _ticker_map().get(ticker.upper().strip())


def _company_facts(cik: str) -> dict | None:
    """Every XBRL fact one filer has ever published.

    This is the whole-company endpoint rather than the per-concept one, for two
    reasons. It is one request instead of nine. And `companyconcept` is not
    reliable: Ford's current revenue tag returns an empty unit there while the
    same tag on this endpoint carries fifty quarters — a series that silently
    ended in 2022 was the symptom.

    The payload runs to megabytes, so it is deliberately not cached; what gets
    cached is the small series derived from it.
    """
    payload = _get(f"{BASE}/api/xbrl/companyfacts/CIK{cik}.json")
    return (payload or {}).get("facts") if payload else None


def _reporting_unit(facts: dict, concept: str) -> str:
    """The one currency a series should be built in.

    A filer can carry facts in more than one: Toyota's XBRL has twenty-seven
    years of revenue in JPY and four years of the same line in USD, filed
    alongside for US readers. Taking whichever appears first per tag mixes the
    two on one axis — ¥19T lands beside $191B and the early years flatten
    against the later ones — so the currency is chosen once for the whole
    concept, as the one the most recent filings use.
    """
    latest: dict[str, str] = {}
    counts: dict[str, int] = {}
    for namespace, tag in CONCEPTS[concept]:
        body = (facts.get(namespace) or {}).get(tag)
        if not body:
            continue
        for unit, rows in (body.get("units") or {}).items():
            for fact in rows:
                end = fact.get("end")
                if not end:
                    continue
                if end > latest.get(unit, ""):
                    latest[unit] = end
                counts[unit] = counts.get(unit, 0) + 1
    if not latest:
        return ""
    return max(latest, key=lambda unit: (latest[unit], counts[unit]))


def _collect(
    facts: dict, concept: str, unit: str | None = None
) -> tuple[dict[tuple, float], dict[tuple, float], str]:
    """Every published value for one concept, split into quarters and years.

    Args:
        facts: A filer's whole XBRL fact set.
        concept: A key of `CONCEPTS`.
        unit: Force a currency — used to hold revenue and net income to the
            same one, since they are drawn on the same axis.

    Returns:
        `(quarters, years, currency)` keyed by `(start, end)`. Where the same
        period appears in more than one filing — a 10-Q figure later restated in
        a 10-K — the most recently filed value wins.
    """
    quarters: dict[tuple, tuple[str, float]] = {}
    years: dict[tuple, tuple[str, float]] = {}
    currency = unit or _reporting_unit(facts, concept)
    if not currency:
        return {}, {}, ""

    for namespace, tag in CONCEPTS[concept]:
        body = (facts.get(namespace) or {}).get(tag)
        if not body:
            continue
        for fact in (body.get("units") or {}).get(currency, []):
            start, end = fact.get("start"), fact.get("end")
            value = fact.get("val")
            if not start or not end or value is None:
                continue
            try:
                span = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
            except ValueError:
                continue
            if QUARTER_DAYS[0] <= span <= QUARTER_DAYS[1]:
                bucket = quarters
            elif YEAR_DAYS[0] <= span <= YEAR_DAYS[1]:
                bucket = years
            else:
                continue
            key = (start, end)
            filed = str(fact.get("filed") or "")
            if key not in bucket or filed >= bucket[key][0]:
                bucket[key] = (filed, float(value))

    return (
        {key: value for key, (_, value) in quarters.items()},
        {key: value for key, (_, value) in years.items()},
        currency,
    )


def _with_fourth_quarters(
    quarters: dict[tuple, float], years: dict[tuple, float]
) -> tuple[dict[tuple, float], set[tuple]]:
    """Fill the quarter a 10-K filer never reports.

    An annual period containing exactly three published quarters is missing its
    fourth by construction, and the annual figure less those three is what the
    fourth was. The derived period runs from the day after the last published
    quarter to the end of the year, and is only kept if that span is a quarter —
    which rules out a year whose three quarters do not actually sit inside it.
    """
    filled = dict(quarters)
    derived: set[tuple] = set()

    for (year_start, year_end), annual in years.items():
        inside = [
            (start, end, value)
            for (start, end), value in quarters.items()
            if start >= year_start and end <= year_end
        ]
        if len(inside) != 3:
            continue
        last_end = max(end for _, end, _ in inside)
        try:
            start = (dt.date.fromisoformat(last_end) + dt.timedelta(days=1)).isoformat()
            span = (dt.date.fromisoformat(year_end) - dt.date.fromisoformat(start)).days
        except ValueError:
            continue
        key = (start, year_end)
        if key in filled or not QUARTER_DAYS[0] <= span <= QUARTER_DAYS[1]:
            continue
        filled[key] = annual - sum(value for _, _, value in inside)
        derived.add(key)

    return filled, derived


def _spaced(keys: list[tuple], minimum: int) -> list[tuple]:
    """Periods of one cadence, oldest first, without overlaps.

    A filer that changes its year end, or reports a stub period alongside a full
    one, leaves two "annual" periods a few months apart. Walking back from the
    most recent and keeping the next only once a full period has elapsed drops
    those without dropping a 52/53-week year end that lands a few days off.
    """
    kept: list[tuple] = []
    for key in sorted(keys, key=lambda k: k[1], reverse=True):
        if not kept:
            kept.append(key)
            continue
        gap = (dt.date.fromisoformat(kept[-1][1]) - dt.date.fromisoformat(key[1])).days
        if gap >= minimum:
            kept.append(key)
    return list(reversed(kept))


def _points(
    revenue: dict[tuple, float],
    income: dict[tuple, float],
    gross: dict[tuple, float],
    derived: set[tuple],
    annual: bool,
) -> list[dict]:
    """One cadence as the chart wants it, oldest first.

    Net income is matched to revenue on the period *end* rather than on the
    whole period. The two lines are often tagged with start dates a day apart —
    one filing counts the year from the first of the month, another from the day
    after the last close — and joining on both would drop the result for a year
    whose revenue is right there.
    """
    by_end = {key[1]: value for key, value in income.items()}
    gross_by_end = {key[1]: value for key, value in gross.items()}
    out = []
    for key in _spaced(list(revenue), YEAR_DAYS[0] if annual else QUARTER_DAYS[0]):
        end = key[1]
        stamp = dt.date.fromisoformat(end)
        result = income.get(key, by_end.get(end))
        margin = gross.get(key, gross_by_end.get(end))
        out.append(
            {
                "end": end,
                "label": str(stamp.year) if annual else stamp.strftime("%b %Y"),
                "revenue": round(revenue[key], 2),
                "grossProfit": round(margin, 2) if margin is not None else None,
                "netIncome": round(result, 2) if result is not None else None,
                "derived": key in derived,
            }
        )
    return out


def series(ticker: str, cik: str | None = None) -> dict:
    """Revenue and net income for one filer, at both cadences, oldest first.

    Both come out of a single request, because a filer that publishes no
    quarters usually still publishes a long run of annual figures — a foreign
    private issuer on Form 20-F reports once a year, and twenty of those is a
    real history rather than a reason to fall back on five quarters from the
    quote feed.

    Args:
        ticker: The listing's ticker, used to look up a CIK when none is given.
        cik: A CIK the caller already holds, which skips the ticker lookup.

    Returns:
        `{quarterly, annual, currency, derived, cik}` where each cadence is a
        list of `{end, label, revenue, netIncome, derived}`. Both are empty when
        SEC has nothing for this filer or no User-Agent is configured.
    """
    blank: dict = {"quarterly": [], "annual": [], "currency": "", "derived": 0, "cik": None}
    if not available():
        return blank

    resolved = resolve_cik(ticker, cik)
    if not resolved:
        return blank

    def run() -> dict:
        facts = _company_facts(resolved)
        if facts is None:
            return {**blank, "cik": resolved, "answered": False}

        revenue_q, revenue_y, currency = _collect(facts, "revenue")
        # Both lines share an axis, so both are held to the revenue currency.
        income_q, income_y, _ = _collect(facts, "netIncome", unit=currency or None)
        gross_q, gross_y, _ = _collect(facts, "grossProfit", unit=currency or None)
        revenue_q, derived = _with_fourth_quarters(revenue_q, revenue_y)
        income_q, _ = _with_fourth_quarters(income_q, income_y)
        gross_q, _ = _with_fourth_quarters(gross_q, gross_y)

        return {
            "quarterly": _points(revenue_q, income_q, gross_q, derived, annual=False),
            "annual": _points(revenue_y, income_y, gross_y, set(), annual=True),
            "currency": currency,
            "derived": len(derived),
            "cik": resolved,
            "answered": True,
        }

    # An empty answer is only worth keeping when SEC actually answered. A filer
    # with no XBRL is settled for the day; a request that never landed should be
    # tried again on the next view.
    return _cached(
        ("series", resolved),
        run,
        keep=lambda result: (
            bool(result["quarterly"] or result["annual"]) or result.get("answered", False)
        ),
    )
