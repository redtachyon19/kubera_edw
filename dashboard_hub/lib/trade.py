"""Who trades with whom, and in what.

Two questions, two sources, both free and keyless:

* **Who** — World Bank **WITS**, which republishes UN Comtrade. One request per
  reporter returns its trade with all 222 partners in a year, both directions.
  That is the bilateral flow: what Japan sells to China and what it buys back.
* **What** — World Bank indicators for the composition of a country's trade,
  split five ways (manufactures, fuel, food, ores and metals, agricultural raw
  materials). Not a full commodity breakdown, but it answers the question people
  actually ask of a country — does it sell things it makes, or things it digs up.

Both are annual and land a year or two behind, which is what trade statistics
are. They are cached to disk with a long TTL because re-pulling them on a page
load would cost seconds for figures that move once a year.
"""

from __future__ import annotations

import json
import pathlib
import time
import urllib.error
import urllib.request
from typing import Any

_WITS = (
    "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/tradestats-trade"
    "/reporter/{iso3}/year/{year}/partner/all/product/total/indicator/{indicator}/?format=JSON"
)

# WITS names the two directions from the reporter's point of view.
_FLOWS = {"exports": "XPRT-TRD-VL", "imports": "MPRT-TRD-VL"}

# WITS reports in thousands of USD.
_WITS_UNIT = 1_000

# The partner list mixes real countries with aggregates — WLD (world), EAS (East
# Asia & Pacific), NAC (North America), ECS (Europe & Central Asia) and a dozen
# more. They share the ISO3 namespace and would otherwise sit at the top of every
# ranking, so the reference file is used as the allow-list of real countries.
_COUNTRIES_PATH = pathlib.Path(__file__).resolve().parents[1] / "countries.json"

# WITS carries the world total under this code, which is worth keeping — it is
# the denominator that turns a partner's value into a share.
_WORLD = "WLD"

# Composition of trade, as a share of merchandise trade. `{}` is the flow prefix:
# TX for exports, TM for imports.
_COMPOSITION = {
    "manufactures": "{}.VAL.MANF.ZS.UN",
    "fuel": "{}.VAL.FUEL.ZS.UN",
    "food": "{}.VAL.FOOD.ZS.UN",
    "oresAndMetals": "{}.VAL.MMTL.ZS.UN",
    "agriculturalRaw": "{}.VAL.AGRI.ZS.UN",
}

_COMPOSITION_LABEL = {
    "manufactures": "Manufactures",
    "fuel": "Fuel",
    "food": "Food",
    "oresAndMetals": "Ores & metals",
    "agriculturalRaw": "Agricultural raw",
}

_WB = "https://api.worldbank.org/v2/country/{iso3}/indicator/{code}"

# Trade statistics are compiled slowly; the most recent year with broad coverage
# is typically two to three back. The reader walks backwards from here.
_LATEST_YEAR = 2022
_YEARS_BACK = 3

_TIMEOUT = 60
_ATTEMPTS = 3
_BACKOFF = 1.5
_TTL = 7 * 24 * 3600

_CACHE_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "trade_cache"


def _countries() -> dict[str, str]:
    """Real ISO3 codes mapped to display names."""
    try:
        rows = json.loads(_COUNTRIES_PATH.read_text())
    except (OSError, ValueError):
        return {}
    return {row["iso3"]: row["name"] for row in rows}


def _cache_read(name: str) -> Any:
    try:
        payload = json.loads((_CACHE_DIR / f"{name}.json").read_text())
        if time.time() - float(payload["fetchedAt"]) > _TTL:
            return None
        return payload["data"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _cache_write(name: str, data: Any) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (_CACHE_DIR / f"{name}.json").write_text(
            json.dumps({"fetchedAt": time.time(), "data": data})
        )
    except OSError:
        # A read-only deployment just re-fetches; it is not an error.
        pass


def _fetch(url: str) -> Any:
    """GET and decode JSON, or None. Never raises — a page draws without it."""
    for attempt in range(_ATTEMPTS):
        request = urllib.request.Request(url, headers={"User-Agent": "kubera-edw/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # A rejected query fails identically on retry; only wait out the
            # transient ones.
            if exc.code in (400, 404):
                return None
            if attempt + 1 < _ATTEMPTS:
                time.sleep(_BACKOFF * (attempt + 1))
        except Exception:  # noqa: BLE001 — a missing feed must not take the desk down
            if attempt + 1 < _ATTEMPTS:
                time.sleep(_BACKOFF * (attempt + 1))
    return None


def _wits_flow(iso3: str, year: int, indicator: str) -> dict[str, float]:
    """`{partner_iso3: value_usd}` for one reporter, one year, one direction.

    WITS answers in SDMX-JSON: the dimensions carry the partner list and each
    series key indexes into it positionally, so the codes have to be read back
    out of `structure` rather than the series itself.
    """
    payload = _fetch(_WITS.format(iso3=iso3.lower(), year=year, indicator=indicator))
    if not payload:
        return {}

    try:
        dimensions = payload["structure"]["dimensions"]["series"]
        partner_dimension = next(d for d in dimensions if d["id"].upper() == "PARTNER")
        partners = [value["id"] for value in partner_dimension["values"]]
        position = dimensions.index(partner_dimension)
        series = payload["dataSets"][0]["series"]
    except (KeyError, IndexError, StopIteration, TypeError):
        return {}

    out: dict[str, float] = {}
    for key, entry in series.items():
        try:
            index = int(key.split(":")[position])
            observation = (entry.get("observations") or {}).get("0")
            if observation is None:
                continue
            value = float(observation[0])
        except (ValueError, IndexError, TypeError):
            continue
        if value > 0:
            out[partners[index]] = value * _WITS_UNIT
    return out


def _partners(iso3: str) -> dict:
    known = _countries()
    exports: dict[str, float] = {}
    imports: dict[str, float] = {}
    year = None

    # Walk back until a year has data — coverage thins towards the present, and a
    # country with nothing in 2022 usually has 2021.
    for candidate in range(_LATEST_YEAR, _LATEST_YEAR - _YEARS_BACK, -1):
        exports = _wits_flow(iso3, candidate, _FLOWS["exports"])
        imports = _wits_flow(iso3, candidate, _FLOWS["imports"])
        if exports or imports:
            year = candidate
            break

    if year is None:
        return {
            "iso3": iso3,
            "year": None,
            "partners": [],
            "totalExports": None,
            "totalImports": None,
        }

    total_exports = exports.get(_WORLD)
    total_imports = imports.get(_WORLD)

    rows = []
    for partner in set(exports) | set(imports):
        if partner not in known or partner == iso3:
            continue
        sold = exports.get(partner)
        bought = imports.get(partner)
        rows.append(
            {
                "iso3": partner,
                "name": known[partner],
                # `exports` is what the reporter sells to this partner.
                "exports": sold,
                "imports": bought,
                # Positive means the reporter sells more than it buys.
                "balance": (sold or 0) - (bought or 0) if (sold or bought) else None,
                "total": (sold or 0) + (bought or 0),
            }
        )

    rows.sort(key=lambda r: -r["total"])
    return {
        "iso3": iso3,
        "year": year,
        "partners": rows,
        "totalExports": total_exports,
        "totalImports": total_imports,
    }


def partners(iso3: str) -> dict:
    """Bilateral trade for one country, biggest counterparty first."""
    iso3 = (iso3 or "").upper()
    if len(iso3) != 3:
        return {
            "iso3": iso3,
            "year": None,
            "partners": [],
            "totalExports": None,
            "totalImports": None,
        }

    cached = _cache_read(f"partners_{iso3}")
    if cached is not None:
        return cached

    result = _partners(iso3)
    if result["partners"]:
        _cache_write(f"partners_{iso3}", result)
    return result


def _wb_all(code: str) -> list[dict]:
    """One indicator for every country, over a short recent window.

    Asked for the world in one walk rather than per country. Ten indicators for
    one country took eleven minutes of small, slow round trips; ten indicators
    for **every** country takes about a minute and then answers instantly for all
    of them. The desk lets a reader click any country on a globe, so the cost has
    to be paid once, not per click.
    """
    rows: list[dict] = []
    page = 1
    while page <= 6:
        payload = _fetch(
            f"https://api.worldbank.org/v2/country/all/indicator/{code}"
            f"?format=json&per_page=1000&page={page}&date={_LATEST_YEAR - 3}:{_LATEST_YEAR + 4}"
        )
        if not isinstance(payload, list) or len(payload) < 2:
            break
        rows.extend(payload[1] or [])
        if page >= int((payload[0] or {}).get("pages") or 1):
            break
        page += 1
    return rows


def _composition_world() -> dict[str, dict]:
    """`{iso3: {exports: [...], imports: [...], years: {...}}}` for every country."""
    # {iso3: {flow: {key: (year, share)}}}
    gathered: dict[str, dict[str, dict[str, tuple[int, float]]]] = {}

    for flow, prefix in (("exports", "TX"), ("imports", "TM")):
        for key, template in _COMPOSITION.items():
            for row in _wb_all(template.format(prefix)):
                iso3 = row.get("countryiso3code")
                value = row.get("value")
                year = int(row["date"]) if str(row.get("date", "")).isdigit() else None
                if not iso3 or value is None or year is None:
                    continue
                bucket = gathered.setdefault(iso3, {}).setdefault(flow, {})
                # Rows arrive newest-first, but nothing here depends on that.
                if key not in bucket or year > bucket[key][0]:
                    bucket[key] = (year, float(value))

    out: dict[str, dict] = {}
    for iso3, flows in gathered.items():
        entry: dict = {"exports": [], "imports": [], "years": {}}
        for flow in ("exports", "imports"):
            shares = flows.get(flow) or {}
            entry[flow] = sorted(
                (
                    {"key": key, "label": _COMPOSITION_LABEL[key], "share": share}
                    for key, (_, share) in shares.items()
                ),
                key=lambda item: -item["share"],
            )
            entry["years"][flow] = max((year for year, _ in shares.values()), default=None)
        out[iso3] = entry
    return out


def composition_world() -> dict[str, dict]:
    """Every country's trade mix, from the cache when it is warm."""
    cached = _cache_read("composition_world")
    if cached is not None:
        return cached

    result = _composition_world()
    # A half-answered pull would otherwise be served for a week.
    if len(result) >= 100:
        _cache_write("composition_world", result)
    return result


def composition(iso3: str) -> dict:
    """The five-way split of one country's merchandise trade, largest share first."""
    iso3 = (iso3 or "").upper()
    blank = {"iso3": iso3, "exports": [], "imports": [], "years": {}}
    if len(iso3) != 3:
        return blank

    entry = composition_world().get(iso3)
    return {"iso3": iso3, **entry} if entry else blank


def warm() -> None:
    """Pull the world's trade mix if it is not already cached.

    Called on a background thread at API start so the first reader to open a
    country does not wait a minute for it.
    """
    composition_world()
