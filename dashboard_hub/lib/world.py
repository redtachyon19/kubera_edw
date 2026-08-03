"""The world desk: governments, currencies and sectors, compared.

Three feeds meet here, and they reach different distances:

* **The warehouse** carries macro — GDP, inflation, unemployment — for every
  country the World Bank publishes, annually, one to two years behind. It is the
  authority on what a government's economy did.
* **Yahoo** carries FX and index levels live. It is the authority on what a
  currency and a stock market are doing right now.
* **The country reference** (`dashboard_hub/countries.json`) supplies the
  capital-city coordinates that let any of it be drawn on a globe. It is bundled
  rather than queried so the desk works on a clean checkout, the same way
  `sectors.json` and `companies.json` do.

Macro prefers the warehouse: it changes once a year, the pipeline already lands
it, and re-fetching the World Bank on every page load would be slower and no
more correct. But a warehouse scoped to the portfolio's dozen countries is not a
world view, so when the marts come back narrow — an older build, or a deployment
still on the previous prod schema — the World Bank is read live and cached to
disk instead. The desk says which of the two answered rather than leaving the
reader to guess why a globe has thirteen dots on it.
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from . import market_data, trade, warehouse

# ── Reference ────────────────────────────────────────────────────────────────
# What the World Bank does not publish: which currency a country spends and
# which index prices its listed companies. Both are editorial — the euro area
# shares one currency across nineteen members, and plenty of countries have no
# index Yahoo carries — so this is a hand-kept table rather than a derived one.
#
# Only countries with a currency entry can be compared on FX; only those with an
# index entry can be compared on market performance. Everything else still
# appears on the globe with its macro figures.

# `invert` marks the pairs Yahoo quotes the other way up. `JPY=X` is yen per
# dollar; `EURUSD=X` is dollars per euro, so it has to be flipped before it can
# sit in the same column.
CURRENCIES: dict[str, dict[str, Any]] = {
    "USA": {"code": "USD", "symbol": None, "invert": False},
    "JPN": {"code": "JPY", "symbol": "JPY=X", "invert": False},
    "CHN": {"code": "CNY", "symbol": "CNY=X", "invert": False},
    "IND": {"code": "INR", "symbol": "INR=X", "invert": False},
    "KOR": {"code": "KRW", "symbol": "KRW=X", "invert": False},
    "BRA": {"code": "BRL", "symbol": "BRL=X", "invert": False},
    "MEX": {"code": "MXN", "symbol": "MXN=X", "invert": False},
    "CAN": {"code": "CAD", "symbol": "CAD=X", "invert": False},
    "CHE": {"code": "CHF", "symbol": "CHF=X", "invert": False},
    "SWE": {"code": "SEK", "symbol": "SEK=X", "invert": False},
    "NOR": {"code": "NOK", "symbol": "NOK=X", "invert": False},
    "POL": {"code": "PLN", "symbol": "PLN=X", "invert": False},
    "CZE": {"code": "CZK", "symbol": "CZK=X", "invert": False},
    "TUR": {"code": "TRY", "symbol": "TRY=X", "invert": False},
    "ZAF": {"code": "ZAR", "symbol": "ZAR=X", "invert": False},
    "IDN": {"code": "IDR", "symbol": "IDR=X", "invert": False},
    "THA": {"code": "THB", "symbol": "THB=X", "invert": False},
    "SGP": {"code": "SGD", "symbol": "SGD=X", "invert": False},
    "TWN": {"code": "TWD", "symbol": "TWD=X", "invert": False},
    "HKG": {"code": "HKD", "symbol": "HKD=X", "invert": False},
    "ISR": {"code": "ILS", "symbol": "ILS=X", "invert": False},
    "PHL": {"code": "PHP", "symbol": "PHP=X", "invert": False},
    "MYS": {"code": "MYR", "symbol": "MYR=X", "invert": False},
    "ARG": {"code": "ARS", "symbol": "ARS=X", "invert": False},
    "CHL": {"code": "CLP", "symbol": "CLP=X", "invert": False},
    "COL": {"code": "COP", "symbol": "COP=X", "invert": False},
    "VNM": {"code": "VND", "symbol": "VND=X", "invert": False},
    "EGY": {"code": "EGP", "symbol": "EGP=X", "invert": False},
    "SAU": {"code": "SAR", "symbol": "SAR=X", "invert": False},
    "ARE": {"code": "AED", "symbol": "AED=X", "invert": False},
    "NGA": {"code": "NGN", "symbol": "NGN=X", "invert": False},
    "PAK": {"code": "PKR", "symbol": "PKR=X", "invert": False},
    "BGD": {"code": "BDT", "symbol": "BDT=X", "invert": False},
    "KEN": {"code": "KES", "symbol": "KES=X", "invert": False},
    "RUS": {"code": "RUB", "symbol": "RUB=X", "invert": False},
    "GBR": {"code": "GBP", "symbol": "GBPUSD=X", "invert": True},
    "AUS": {"code": "AUD", "symbol": "AUDUSD=X", "invert": True},
    "NZL": {"code": "NZD", "symbol": "NZDUSD=X", "invert": True},
}

# The euro is one currency and nineteen governments. Each member gets the same
# rate, and their inflation figures diverge anyway — which is the comparison the
# desk exists to show.
_EURO = ("DEU FRA ITA ESP NLD BEL AUT IRL PRT GRC FIN SVK SVN LTU LVA EST LUX CYP MLT HRV").split()
for _iso3 in _EURO:
    CURRENCIES[_iso3] = {"code": "EUR", "symbol": "EURUSD=X", "invert": True}

# Local benchmarks, in local currency. Verified against Yahoo — symbols that
# return nothing are dropped at request time rather than shown as a gap.
INDICES: dict[str, dict[str, str]] = {
    "USA": {"symbol": "^GSPC", "label": "S&P 500"},
    "CAN": {"symbol": "^GSPTSE", "label": "S&P/TSX"},
    "MEX": {"symbol": "^MXX", "label": "IPC"},
    "BRA": {"symbol": "^BVSP", "label": "Bovespa"},
    "ARG": {"symbol": "^MERV", "label": "Merval"},
    "GBR": {"symbol": "^FTSE", "label": "FTSE 100"},
    "DEU": {"symbol": "^GDAXI", "label": "DAX"},
    "FRA": {"symbol": "^FCHI", "label": "CAC 40"},
    "ESP": {"symbol": "^IBEX", "label": "IBEX 35"},
    "ITA": {"symbol": "FTSEMIB.MI", "label": "FTSE MIB"},
    "NLD": {"symbol": "^AEX", "label": "AEX"},
    "CHE": {"symbol": "^SSMI", "label": "SMI"},
    "SWE": {"symbol": "^OMX", "label": "OMX 30"},
    "TUR": {"symbol": "XU100.IS", "label": "BIST 100"},
    "JPN": {"symbol": "^N225", "label": "Nikkei 225"},
    "HKG": {"symbol": "^HSI", "label": "Hang Seng"},
    "CHN": {"symbol": "000001.SS", "label": "SSE Composite"},
    "KOR": {"symbol": "^KS11", "label": "KOSPI"},
    "TWN": {"symbol": "^TWII", "label": "TAIEX"},
    "IND": {"symbol": "^BSESN", "label": "Sensex"},
    "AUS": {"symbol": "^AXJO", "label": "ASX 200"},
    "NZL": {"symbol": "^NZ50", "label": "NZX 50"},
    "SGP": {"symbol": "^STI", "label": "Straits Times"},
    "IDN": {"symbol": "^JKSE", "label": "Jakarta Composite"},
    "MYS": {"symbol": "^KLSE", "label": "KLCI"},
    "THA": {"symbol": "^SET.BK", "label": "SET"},
    "PHL": {"symbol": "PSEI.PS", "label": "PSEi"},
    "ISR": {"symbol": "^TA125.TA", "label": "TA-125"},
    "ZAF": {"symbol": "^JN0U.JO", "label": "JSE Top 40"},
}

# The ten iShares global sector funds. One per GICS sector, each holding names
# from every market rather than one — which is what makes this a world sector
# league table and not a second view of the S&P.
GLOBAL_SECTORS: list[dict[str, str]] = [
    {"slug": "technology", "name": "Technology", "symbol": "IXN"},
    {"slug": "financials", "name": "Financials", "symbol": "IXG"},
    {"slug": "health-care", "name": "Health Care", "symbol": "IXJ"},
    {"slug": "energy", "name": "Energy", "symbol": "IXC"},
    {"slug": "industrials", "name": "Industrials", "symbol": "EXI"},
    {"slug": "staples", "name": "Consumer Staples", "symbol": "KXI"},
    {"slug": "discretionary", "name": "Consumer Discretionary", "symbol": "RXI"},
    {"slug": "materials", "name": "Materials", "symbol": "MXI"},
    {"slug": "utilities", "name": "Utilities", "symbol": "JXI"},
    {"slug": "telecom", "name": "Communications", "symbol": "IXP"},
]

# Broad regional funds, all USD-denominated, so their returns are directly
# comparable with each other and with the global sector funds above.
REGIONS: list[dict[str, str]] = [
    {"slug": "north-america", "name": "North America", "symbol": "SPY"},
    {"slug": "europe", "name": "Europe", "symbol": "VGK"},
    {"slug": "japan", "name": "Japan", "symbol": "EWJ"},
    {"slug": "asia-ex-japan", "name": "Asia ex-Japan", "symbol": "AAXJ"},
    {"slug": "emerging", "name": "Emerging Markets", "symbol": "EEM"},
    {"slug": "latin-america", "name": "Latin America", "symbol": "ILF"},
]

# Energy first, because that is what the question is usually about, then the
# metals that price it and the broad basket that averages it.
ENERGY: list[dict[str, str]] = [
    {"slug": "wti", "name": "WTI Crude", "symbol": "CL=F", "unit": "USD/bbl", "group": "Energy"},
    {
        "slug": "brent",
        "name": "Brent Crude",
        "symbol": "BZ=F",
        "unit": "USD/bbl",
        "group": "Energy",
    },
    {
        "slug": "henry-hub",
        "name": "Natural Gas · Henry Hub",
        "symbol": "NG=F",
        "unit": "USD/MMBtu",
        "group": "Energy",
    },
    {
        "slug": "ttf",
        "name": "Natural Gas · Dutch TTF",
        "symbol": "TTF=F",
        "unit": "EUR/MWh",
        "group": "Energy",
    },
    {
        "slug": "gasoline",
        "name": "RBOB Gasoline",
        "symbol": "RB=F",
        "unit": "USD/gal",
        "group": "Energy",
    },
    {
        "slug": "heating-oil",
        "name": "Heating Oil",
        "symbol": "HO=F",
        "unit": "USD/gal",
        "group": "Energy",
    },
    {"slug": "gold", "name": "Gold", "symbol": "GC=F", "unit": "USD/oz", "group": "Metals"},
    {"slug": "silver", "name": "Silver", "symbol": "SI=F", "unit": "USD/oz", "group": "Metals"},
    {"slug": "copper", "name": "Copper", "symbol": "HG=F", "unit": "USD/lb", "group": "Metals"},
    {
        "slug": "uranium",
        "name": "Uranium miners",
        "symbol": "URA",
        "unit": "USD",
        "group": "Metals",
    },
    {
        "slug": "gsci",
        "name": "S&P GSCI commodity index",
        "symbol": "^SPGSCI",
        "unit": "index",
        "group": "Basket",
    },
    {
        "slug": "energy-equities",
        "name": "Energy equities",
        "symbol": "XLE",
        "unit": "USD",
        "group": "Basket",
    },
]

GOLD = "GC=F"

_TTL = 900
_MACRO_TTL = 12 * 3600
_NEWS_TTL = 1800

_COUNTRIES_PATH = pathlib.Path(__file__).resolve().parents[1] / "countries.json"

# Below this, whatever answered is a portfolio-scoped warehouse rather than a
# world one, and the live World Bank is asked instead. The pipeline lands every
# country (`ingestion/world_bank_client.py`), but a warehouse built before that
# change — or a deployment still on the old prod schema — carries only the dozen
# with an issuer, and a globe of thirteen dots is not a world view.
_MIN_WORLD_COUNTRIES = 40

_WB_INDICATORS = {
    "inflation": "FP.CPI.TOTL.ZG",
    "gdpGrowth": "NY.GDP.MKTP.KD.ZG",
    "unemployment": "SL.UEM.TOTL.ZS",
}
_WB_URL = "https://api.worldbank.org/v2/country/all/indicator/{code}"
_WB_TIMEOUT = 60
_WB_ATTEMPTS = 3
_WB_BACKOFF = 1.5
_WB_MAX_PAGES = 6
# Enough to find a value for a country whose last publication is a few years old
# without pulling a history nothing on this page draws.
_WB_WINDOW_YEARS = 4


def _num(value: Any) -> float | None:
    """A float, or None for anything that cannot be plotted."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _returns(symbols: list[str], period_label: str) -> dict[str, dict]:
    """Period return and latest level for each symbol.

    One batched download. Symbols Yahoo has nothing for are absent from the
    result rather than present and empty, so callers can tell "no coverage" from
    "flat".
    """
    if not symbols:
        return {}

    period, interval = market_data.PERIODS.get(period_label, market_data.PERIODS["1Y"])
    frame = market_data._closes(tuple(sorted(set(symbols))), period, interval, False)
    if frame is None or frame.empty:
        return {}

    out: dict[str, dict] = {}
    for symbol in symbols:
        if symbol not in frame.columns:
            continue
        series = frame[symbol].dropna()
        if len(series) < 2:
            continue
        first, last = _num(series.iloc[0]), _num(series.iloc[-1])
        if first is None or last is None or first == 0:
            continue
        out[symbol] = {
            "last": last,
            "change": last / first - 1,
            "start": first,
            "asOf": str(pd.Timestamp(series.index[-1]).date()),
            "points": len(series),
        }
    return out


def reference() -> list[dict]:
    """Every country the desk can draw, from the bundled reference file.

    Regenerate with `python -m scripts.generate_country_reference`.
    """
    try:
        return json.loads(_COUNTRIES_PATH.read_text())
    except (OSError, ValueError):
        return []


def _wb_pages(query: str) -> list[dict]:
    """Every row for one indicator query, following the page cursor.

    The World Bank times out often enough that a single attempt loses roughly one
    request in three, and a lost request here is a whole indicator missing from
    the desk rather than a gap in one row. Each page is retried before the
    indicator is given up on.
    """
    rows: list[dict] = []
    page = 1
    while page <= _WB_MAX_PAGES:
        payload = None
        for attempt in range(_WB_ATTEMPTS):
            request = urllib.request.Request(
                f"{query}&page={page}", headers={"User-Agent": "kubera-edw/1.0"}
            )
            try:
                with urllib.request.urlopen(request, timeout=_WB_TIMEOUT) as response:
                    payload = json.load(response)
                break
            except urllib.error.HTTPError as exc:
                # A 400 is the query being rejected, not the network failing —
                # retrying it verbatim would fail identically. Let the caller
                # try a different shape of query instead.
                if exc.code == 400:
                    return []
                if attempt + 1 < _WB_ATTEMPTS:
                    time.sleep(_WB_BACKOFF * (attempt + 1))
            except Exception:  # noqa: BLE001 — retried below; a miss must not fail the desk
                if attempt + 1 < _WB_ATTEMPTS:
                    time.sleep(_WB_BACKOFF * (attempt + 1))

        if not isinstance(payload, list) or len(payload) < 2:
            break
        rows.extend(payload[1] or [])
        if page >= int((payload[0] or {}).get("pages") or 1):
            break
        page += 1
    return rows


def _wb_indicator(code: str) -> list[dict]:
    """Rows for one indicator, however the API is willing to give them up.

    `mrnev=1` — most recent non-empty value — is one small response per
    indicator and is the cheap path. Not every series accepts it:
    `NY.GDP.MKTP.KD.ZG` answers a flat 400. Those fall back to a short date
    window, which returns several years per country for the caller to reduce.
    """
    base = f"{_WB_URL.format(code=code)}?format=json&per_page=400"
    rows = _wb_pages(f"{base}&mrnev=1")
    if rows:
        return rows

    year = time.gmtime().tm_year
    return _wb_pages(f"{base}&date={year - _WB_WINDOW_YEARS}:{year}")


def _world_bank_live() -> dict[str, dict]:
    """Macro straight from the World Bank, for when the warehouse is narrow.

    Each country keeps the newest published value per indicator. Indicators are
    released on different schedules — unemployment lands a year behind inflation
    — so the year is tracked per field as well as per country.
    """
    out: dict[str, dict] = {}
    for field, code in _WB_INDICATORS.items():
        for row in _wb_indicator(code):
            iso3, value = row.get("countryiso3code"), _num(row.get("value"))
            year = int(row["date"]) if str(row.get("date", "")).isdigit() else None
            if not iso3 or value is None or year is None:
                continue

            entry = out.setdefault(iso3, {})
            # The date-window path returns every year, in no order this relies
            # on, so an older row must never overwrite a newer one.
            if year < entry.get(f"{field}Year", 0):
                continue
            entry[field] = value
            entry[f"{field}Year"] = year
            entry["year"] = max(year, entry.get("year", 0))

    return out


def _cache_path() -> pathlib.Path:
    root = pathlib.Path(__file__).resolve().parents[2] / "data"
    return root / "world_macro_cache.json"


def _read_cache() -> dict[str, dict] | None:
    """The last good pull, if it is still inside its TTL."""
    try:
        payload = json.loads(_cache_path().read_text())
        if time.time() - float(payload["fetchedAt"]) > _MACRO_TTL:
            return None
        data = payload["data"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return data if len(data) >= _MIN_WORLD_COUNTRIES else None


def _write_cache(data: dict[str, dict]) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetchedAt": time.time(), "data": data}))
    except OSError:
        # A read-only deployment is fine — it just re-fetches each time the
        # process-local cache expires.
        pass


def _macro_live_cached() -> dict[str, dict]:
    """`_world_bank_live` behind a TTL, and behind a file across restarts.

    The figures move once a year. Re-pulling them on every cold start would cost
    a minute of the reader's time for data that has not changed since the last
    process was running.
    """

    def produce() -> dict[str, dict]:
        cached = _read_cache()
        if cached is not None:
            return cached
        fresh = _world_bank_live()
        if len(fresh) >= _MIN_WORLD_COUNTRIES:
            _write_cache(fresh)
        return fresh

    return market_data._cached(
        ("world-macro-live",),
        produce,
        ttl=_MACRO_TTL,
        keep=lambda value: len(value) >= _MIN_WORLD_COUNTRIES,
    )


def _macro_by_country() -> dict[str, dict]:
    """Latest macro reading per country, with the prior year for direction.

    The warehouse answers when it covers the world. A warehouse scoped to the
    portfolio's countries is treated as no answer at all and the World Bank is
    read live instead, so the desk is not silently reduced to a dozen dots.
    """
    rows = warehouse.macro()
    if len({row.get("country_iso3") for row in rows}) < _MIN_WORLD_COUNTRIES:
        return _macro_live_cached()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        iso3 = row.get("country_iso3")
        if iso3:
            grouped.setdefault(str(iso3), []).append(row)

    out: dict[str, dict] = {}
    for iso3, history in grouped.items():
        # `warehouse.macro` orders by year ascending, so the tail is the newest.
        latest = None
        for row in reversed(history):
            if any(
                _num(row.get(field)) is not None
                for field in ("cpi_inflation_pct", "gdp_growth_pct", "unemployment_pct")
            ):
                latest = row
                break
        if latest is None:
            continue

        prior = next(
            (
                row
                for row in reversed(history)
                if row["calendar_year"] < latest["calendar_year"]
                and _num(row.get("cpi_inflation_pct")) is not None
            ),
            None,
        )

        out[iso3] = {
            "year": int(latest["calendar_year"]),
            "inflation": _num(latest.get("cpi_inflation_pct")),
            "gdpGrowth": _num(latest.get("gdp_growth_pct")),
            "unemployment": _num(latest.get("unemployment_pct")),
            "gdp": _num(latest.get("gdp")),
            "priorInflation": _num(prior.get("cpi_inflation_pct")) if prior else None,
            "inflationTrail": [
                {"year": int(row["calendar_year"]), "value": _num(row.get("cpi_inflation_pct"))}
                for row in history
                if _num(row.get("cpi_inflation_pct")) is not None
            ],
        }
    return out


def _fx(period_label: str) -> dict[str, dict]:
    """Rate per USD and its period move, per currency code."""
    symbols = sorted({c["symbol"] for c in CURRENCIES.values() if c["symbol"]})
    moves = _returns(symbols, period_label)

    out: dict[str, dict] = {"USD": {"perUsd": 1.0, "change": 0.0, "symbol": None}}
    for entry in CURRENCIES.values():
        code, symbol, invert = entry["code"], entry["symbol"], entry["invert"]
        if not symbol or code in out:
            continue
        move = moves.get(symbol)
        if not move:
            continue
        # An inverted pair quotes USD per unit, so both the level and the
        # direction flip: a rising GBPUSD is a strengthening pound, while a
        # rising USDJPY is a weakening yen.
        per_usd = 1 / move["last"] if invert and move["last"] else move["last"]
        against_usd = move["change"] if invert else (1 / (1 + move["change"]) - 1)
        out[code] = {
            "perUsd": _num(per_usd),
            # Positive means the currency gained on the dollar over the window.
            "change": _num(against_usd),
            "symbol": symbol,
            "asOf": move["asOf"],
        }
    return out


def _snapshot(period_label: str) -> dict:
    macro = _macro_by_country()
    fx = _fx(period_label)
    index_moves = _returns([entry["symbol"] for entry in INDICES.values()], period_label)
    issuers = {
        str(row.get("country_iso3"))
        for row in warehouse.holdings().values()
        if row.get("country_iso3")
    }

    countries: list[dict] = []
    for row in reference():
        iso3 = str(row["iso3"])
        currency = CURRENCIES.get(iso3)
        code = currency["code"] if currency else None
        rate = fx.get(code) if code else None
        index = INDICES.get(iso3)
        move = index_moves.get(index["symbol"]) if index else None

        countries.append(
            {
                "iso3": iso3,
                "name": row["name"],
                "region": row["region"],
                "incomeLevel": row.get("incomeLevel") or None,
                "capital": row.get("capital"),
                "lat": _num(row["lat"]),
                "lon": _num(row["lon"]),
                "hasIssuer": iso3 in issuers,
                "currency": code,
                "fxPerUsd": rate["perUsd"] if rate else None,
                "fxChange": rate["change"] if rate else None,
                "index": index["label"] if index else None,
                "indexSymbol": index["symbol"] if index else None,
                "marketChange": move["change"] if move else None,
                **(macro.get(iso3) or {}),
            }
        )

    countries.sort(key=lambda c: c["name"])
    return {
        "period": period_label,
        "countries": countries,
        "macroYear": max((c["year"] for c in countries if c.get("year")), default=None),
        "macroSource": "warehouse" if _macro_from_warehouse() else "World Bank, live",
    }


def _macro_from_warehouse() -> bool:
    """Whether the marts are wide enough to be the macro source."""
    return len({row.get("country_iso3") for row in warehouse.macro()}) >= _MIN_WORLD_COUNTRIES


def snapshot(period_label: str = "1Y") -> dict:
    """Every country, its macro reading, its currency and its market."""
    return market_data._cached(
        ("world", period_label),
        lambda: _snapshot(period_label),
        ttl=_TTL,
        keep=lambda value: bool(value.get("countries")),
    )


def _sectors(period_label: str) -> dict:
    sector_moves = _returns([s["symbol"] for s in GLOBAL_SECTORS], period_label)
    region_moves = _returns([r["symbol"] for r in REGIONS], period_label)

    sectors = [
        {
            **sector,
            "change": sector_moves[sector["symbol"]]["change"],
            "last": sector_moves[sector["symbol"]]["last"],
            "asOf": sector_moves[sector["symbol"]]["asOf"],
        }
        for sector in GLOBAL_SECTORS
        if sector["symbol"] in sector_moves
    ]
    sectors.sort(key=lambda s: s["change"], reverse=True)

    regions = [
        {**region, "change": region_moves[region["symbol"]]["change"]}
        for region in REGIONS
        if region["symbol"] in region_moves
    ]
    regions.sort(key=lambda r: r["change"], reverse=True)

    return {"period": period_label, "sectors": sectors, "regions": regions}


def sectors(period_label: str = "1Y") -> dict:
    """The global sector league table, ranked, plus how each region did."""
    return market_data._cached(
        ("world-sectors", period_label),
        lambda: _sectors(period_label),
        ttl=_TTL,
        keep=lambda value: bool(value.get("sectors")),
    )


# ── Gold as the unit of account ──────────────────────────────────────────────
# Every figure on this desk is quoted in dollars, and the dollar is not a fixed
# rule — it is one of the things being measured. A market "up 20%" against a
# currency that lost ground has not necessarily bought its holders anything.
#
# Gold is used as the alternative numeraire because it is the one asset with a
# continuous price in every currency going back further than any of these
# governments' current monetary regimes. It is not a claim that gold is stable;
# it is that gold is *independent* — it is not issued by any of the countries
# being compared, so it cannot flatter or punish one of them.


def _series(symbol: str, period_label: str) -> pd.Series | None:
    """One symbol's close series over the window, or None."""
    period, interval = market_data.PERIODS.get(period_label, market_data.PERIODS["5Y"])
    frame = market_data._closes((symbol,), period, interval, False)
    if frame is None or frame.empty or symbol not in frame.columns:
        return None
    series = frame[symbol].dropna()
    return series if len(series) > 2 else None


def _rebase(series: pd.Series) -> list[dict]:
    """A series indexed to 100 at its start, thinned to something drawable."""
    first = float(series.iloc[0])
    if not first:
        return []

    # A ten-year daily series is 2,500 points behind a chart 700px wide. One
    # point per two pixels is past what anyone can see.
    step = max(1, len(series) // 320)
    return [
        {"date": str(pd.Timestamp(index).date()), "value": round(float(value) / first * 100, 2)}
        for index, value in list(series.items())[::step]
    ]


def _purchasing_power(iso3: str, period_label: str) -> dict:
    """What one unit of a country's currency buys, in gold and against the dollar.

    Three lines, all indexed to 100 at the start of the window:

    * **In gold** — the currency's price in gold. This is the one that answers
      "has my money held its value", because it is measured against something no
      central bank issues.
    * **Against the dollar** — the conventional reading, kept beside it so the
      difference between the two is visible rather than asserted.
    * **The dollar in gold** — the same treatment applied to the benchmark
      itself, so the dollar is shown as a measured thing and not the ruler.
    """
    entry = CURRENCIES.get(iso3)
    gold_usd = _series(GOLD, period_label)
    if gold_usd is None:
        return {
            "iso3": iso3,
            "currency": entry["code"] if entry else None,
            "points": [],
            "lines": [],
        }

    code = entry["code"] if entry else "USD"
    symbol = entry["symbol"] if entry else None

    # Units of the local currency per USD, aligned to gold's trading days.
    if symbol:
        fx = _series(symbol, period_label)
        if fx is None:
            return {"iso3": iso3, "currency": code, "points": [], "lines": []}
        per_usd = 1 / fx if entry["invert"] else fx
    else:
        per_usd = pd.Series(1.0, index=gold_usd.index)

    frame = pd.DataFrame({"gold": gold_usd, "perUsd": per_usd}).dropna()
    if len(frame) < 3:
        return {"iso3": iso3, "currency": code, "points": [], "lines": []}

    # Gold priced in the local currency, then inverted: how much gold one unit of
    # the currency buys. Rising means the money is gaining on gold.
    gold_local = frame["gold"] * frame["perUsd"]
    in_gold = _rebase(1 / gold_local)
    in_usd = _rebase(1 / frame["perUsd"])
    dollar_in_gold = _rebase(1 / frame["gold"])

    by_date: dict[str, dict] = {}
    for key, rows in (("inGold", in_gold), ("vsUsd", in_usd), ("usdInGold", dollar_in_gold)):
        for row in rows:
            by_date.setdefault(row["date"], {"date": row["date"]})[key] = row["value"]

    points = [by_date[date] for date in sorted(by_date)]
    lines = [{"key": "inGold", "label": f"{code} in gold"}]
    if code != "USD":
        # For the dollar itself these last two are the same series, and drawing
        # one line twice under two names is worse than drawing it once.
        lines.append({"key": "vsUsd", "label": f"{code} vs USD"})
        lines.append({"key": "usdInGold", "label": "USD in gold"})

    latest = points[-1] if points else {}
    return {
        "iso3": iso3,
        "currency": code,
        "period": period_label,
        "points": points,
        "lines": lines,
        # Percentage change over the window, from the rebased tail.
        "goldChange": (latest.get("inGold", 100) / 100 - 1) if latest.get("inGold") else None,
        "usdChange": (latest.get("vsUsd", 100) / 100 - 1) if latest.get("vsUsd") else None,
        "dollarGoldChange": (
            (latest.get("usdInGold", 100) / 100 - 1) if latest.get("usdInGold") else None
        ),
    }


def _energy(period_label: str) -> dict:
    moves = _returns([entry["symbol"] for entry in ENERGY], period_label)
    rows = [
        {
            **entry,
            "last": moves[entry["symbol"]]["last"],
            "change": moves[entry["symbol"]]["change"],
        }
        for entry in ENERGY
        if entry["symbol"] in moves
    ]

    # Crude is the reference everything else in the panel is read against, so it
    # carries a drawn series rather than just a number.
    brent = _series("BZ=F", period_label)
    wti = _series("CL=F", period_label)
    gas = _series("NG=F", period_label)

    # Rebased, not absolute. Crude trades near $80 a barrel and gas near $3 an
    # MMBtu, so on a shared axis the gas line lies flat along the bottom and says
    # nothing — even though it is the one that moved differently. Indexing all
    # three to 100 makes the comparison the chart is for legible; the levels are
    # in the table underneath, which is where a price belongs anyway.
    merged: dict[str, dict] = {}
    for key, series in (("brent", brent), ("wti", wti), ("gas", gas)):
        for row in _rebase(series) if series is not None else []:
            merged.setdefault(row["date"], {"date": row["date"]})[key] = row["value"]

    return {
        "period": period_label,
        "prices": rows,
        "points": [merged[date] for date in sorted(merged)],
        "lines": [
            {"key": "brent", "label": "Brent"},
            {"key": "wti", "label": "WTI"},
            {"key": "gas", "label": "Henry Hub gas"},
        ],
    }


def energy(period_label: str = "1Y") -> dict:
    """Crude, gas, refined products, the metals that price them, and the basket."""
    return market_data._cached(
        ("world-energy", period_label),
        lambda: _energy(period_label),
        ttl=_TTL,
        keep=lambda value: bool(value.get("prices")),
    )


# ── News ─────────────────────────────────────────────────────────────────────
# Google News' RSS search takes a plain query and needs no key. GDELT was the
# other candidate and covers more of the world, but it rate-limits hard enough
# that a reader clicking three countries in a row gets 429s.

_NEWS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
_NEWS_LIMIT = 8


def _unescape(text: str) -> str:
    for entity, character in (
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&apos;", "'"),
        ("&amp;", "&"),
    ):
        text = text.replace(entity, character)
    return text


def _tag(block: str, tag: str) -> str:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
    if not match:
        return ""
    value = match.group(1).strip()
    cdata = re.match(r"^<!\[CDATA\[(.*?)\]\]>$", value, re.S)
    return _unescape((cdata.group(1) if cdata else value).strip())


def _country_news(name: str, limit: int) -> list[dict]:
    """Recent economy and market stories for one country.

    The query is narrowed to economy, trade and markets deliberately — an
    unqualified country name returns sport and weather, which is not what a
    research desk is for.
    """
    query = urllib.parse.quote(f"{name} economy OR trade OR markets OR central bank when:14d")
    request = urllib.request.Request(
        _NEWS_URL.format(query=query),
        headers={"User-Agent": "Mozilla/5.0 (compatible; kubera-edw/1.0)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            xml = response.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — no news is a thin panel, not an error
        return []

    stories = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S)[: limit * 2]:
        title = _tag(block, "title")
        if not title:
            continue
        # Google appends " - Publisher" to every headline; the publisher is
        # already carried separately, so the suffix is redundant noise.
        source = _tag(block, "source")
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        stories.append(
            {
                "title": title,
                "url": _tag(block, "link"),
                "source": source,
                "published": _tag(block, "pubDate"),
            }
        )
        if len(stories) >= limit:
            break
    return stories


def news(iso3: str, limit: int = _NEWS_LIMIT) -> dict:
    """Headlines for one country, keyed by its ISO3 code."""
    iso3 = (iso3 or "").upper()
    name = next((c["name"] for c in reference() if c["iso3"] == iso3), None)
    if not name:
        return {"iso3": iso3, "stories": []}

    stories = market_data._cached(
        ("world-news", iso3),
        lambda: _country_news(name, limit),
        ttl=_NEWS_TTL,
        keep=bool,
    )
    return {"iso3": iso3, "name": name, "stories": stories}


def country(iso3: str, period_label: str = "5Y") -> dict:
    """Everything the desk knows about one country, for its detail panel."""
    iso3 = (iso3 or "").upper()
    profile = next(
        (c for c in snapshot(period_label).get("countries", []) if c["iso3"] == iso3), None
    )

    return {
        "iso3": iso3,
        "profile": profile,
        "purchasingPower": market_data._cached(
            ("world-pp", iso3, period_label),
            lambda: _purchasing_power(iso3, period_label),
            ttl=_TTL,
            keep=lambda value: bool(value.get("points")),
        ),
        "trade": trade.partners(iso3),
        "composition": trade.composition(iso3),
        "news": news(iso3)["stories"],
    }
