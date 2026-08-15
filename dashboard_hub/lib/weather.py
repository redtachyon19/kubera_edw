"""Current weather at every capital, and the tropical cyclones that are running.

Two sources, deliberately kept apart because they answer different questions and
have different coverage:

* **Open-Meteo** gives current conditions anywhere, so it is asked once for all
  212 capitals in `countries.json` and answers globally. No key, no account.
* **NOAA's National Hurricane Center** publishes the storms it is actually
  advising on. That is authoritative but *regional* — the Atlantic and the
  eastern and central Pacific only. A typhoon in the western Pacific is a real
  storm that this feed will never mention, so the desk says which basins it
  covers rather than implying the rest of the world is calm.

The gap between the two is filled honestly rather than silently: thunderstorms
are read from the WMO code Open-Meteo returns per capital, which *is* worldwide,
so severe conditions outside the NHC's basins still show up — as a thunderstorm
at a named capital, which is what the data supports, not as a cyclone track it
cannot see.

    weather.snapshot()   -> conditions at every capital
    weather.storms()     -> active tropical cyclones, NHC basins
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from dashboard_hub.lib.market_data import _cached
from dashboard_hub.lib.world import reference

_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
_NHC_STORMS = "https://www.nhc.noaa.gov/CurrentStorms.json"
# GDACS rather than NASA's EONET, for two reasons found by checking both: EONET's
# *open* wildfires are sourced entirely from IRWIN and are therefore US-only,
# and it emits corrupt coordinates (a Kansas fire at [15, 30], a New Mexico one
# at latitude 200). GDACS is global, needs no key, carries burned area in
# hectares and an alert level — and is where EONET's own worldwide fires come
# from anyway, so this reads the original rather than a copy.
_GDACS_FIRES = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=WF"

_TIMEOUT = 45
# Open-Meteo updates on a 15-minute cadence and the NHC issues advisories every
# three hours, so anything shorter than this is asking the same question twice.
_TTL = 900
_STORM_TTL = 600
# GDACS re-scores a fire roughly daily; a burn scar does not move in an hour.
_FIRE_TTL = 1800

_CURRENT_FIELDS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)

# WMO 4677, grouped to the bands a reader actually distinguishes. The exact code
# is kept alongside the band so the table can print the precise condition while
# the globe colours by the group.
_WMO = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}

_THUNDER = {95, 96, 99}
_SNOW = {71, 73, 75, 77, 85, 86}
_RAIN = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
_FOG = {45, 48}


def _num(value: Any) -> float | None:
    """A float, or None for anything that cannot be plotted."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def condition(code: Any) -> dict:
    """The WMO code as a label and a band the globe can colour by."""
    try:
        value = int(code)
    except (TypeError, ValueError):
        return {"code": None, "label": "No reading", "band": "unknown"}

    if value in _THUNDER:
        band = "thunderstorm"
    elif value in _SNOW:
        band = "snow"
    elif value in _RAIN:
        band = "rain"
    elif value in _FOG:
        band = "fog"
    elif value == 3:
        band = "overcast"
    elif value in (1, 2):
        band = "cloud"
    else:
        band = "clear"

    return {"code": value, "label": _WMO.get(value, f"WMO {value}"), "band": band}


def _capitals() -> list[dict]:
    """Every capital with usable coordinates, in a fixed order.

    The order matters: Open-Meteo answers a multi-coordinate request with a bare
    array positionally matched to the input, with no echo of which country each
    entry belongs to. The zip below is only correct because this list is built
    once and reused for both halves of the request.
    """
    out = []
    for row in reference():
        lat, lon = _num(row.get("lat")), _num(row.get("lon"))
        if lat is None or lon is None:
            continue
        out.append(
            {
                "iso3": row.get("iso3"),
                "name": row.get("name"),
                "capital": row.get("capital"),
                "region": row.get("region"),
                "lat": lat,
                "lon": lon,
            }
        )
    return out


def _fetch_json(url: str, timeout: int = _TIMEOUT) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "kubera-edw/weather"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _snapshot() -> dict:
    places = _capitals()
    if not places:
        return {"countries": [], "asOf": None, "source": "Open-Meteo", "error": "no capitals"}

    query = urllib.parse.urlencode(
        {
            "latitude": ",".join(f"{p['lat']:.4f}" for p in places),
            "longitude": ",".join(f"{p['lon']:.4f}" for p in places),
            "current": ",".join(_CURRENT_FIELDS),
            "timezone": "UTC",
        }
    )

    payload = _fetch_json(f"{_OPEN_METEO}?{query}")
    # One coordinate comes back as an object, many as an array. Normalising here
    # keeps the zip below from silently pairing a dict's keys with countries.
    entries = payload if isinstance(payload, list) else [payload]

    # Position is the *only* thing linking a reading to a country here. A short
    # or long answer would pair Tokyo's weather with Sudan and look entirely
    # plausible on the globe, so this refuses rather than guesses.
    if len(entries) != len(places):
        return {
            "countries": [],
            "asOf": None,
            "source": "Open-Meteo",
            "error": f"asked for {len(places)} capitals, got {len(entries)} readings",
        }

    countries: list[dict] = []
    as_of: str | None = None
    for place, entry in zip(places, entries, strict=True):
        current = (entry or {}).get("current") or {}
        as_of = as_of or current.get("time")
        countries.append(
            {
                **place,
                "temperature": _num(current.get("temperature_2m")),
                "apparent": _num(current.get("apparent_temperature")),
                "humidity": _num(current.get("relative_humidity_2m")),
                "precipitation": _num(current.get("precipitation")),
                "wind": _num(current.get("wind_speed_10m")),
                "condition": condition(current.get("weather_code")),
            }
        )

    return {
        "countries": countries,
        "asOf": as_of,
        "source": "Open-Meteo",
        "units": {
            "temperature": "°C",
            "apparent": "°C",
            "humidity": "%",
            "precipitation": "mm",
            "wind": "km/h",
        },
    }


def snapshot() -> dict:
    """Current conditions at every capital, behind a TTL.

    Every metric comes back in one payload rather than one request per metric:
    the upstream call is the same size either way, and it means switching layer
    on the desk is instant instead of a round trip.
    """
    return _cached(
        ("weather", "snapshot"),
        _snapshot,
        ttl=_TTL,
        # A failed pull must not be cached for fifteen minutes.
        keep=lambda v: bool(v["countries"]),
    )


# Saffir-Simpson, in knots, which is the unit the NHC reports intensity in.
_CATEGORY = ((137, 5), (113, 4), (96, 3), (83, 2), (64, 1))

_CLASSIFICATION = {
    "TD": "Tropical depression",
    "TS": "Tropical storm",
    "HU": "Hurricane",
    "MH": "Major hurricane",
    "TY": "Typhoon",
    "ST": "Super typhoon",
    "STD": "Subtropical depression",
    "STS": "Subtropical storm",
    "SD": "Subtropical depression",
    "SS": "Subtropical storm",
    # A system the NHC is advising on *before* it is a cyclone, because it is
    # forecast to threaten land within two days. It carries warnings, so it
    # belongs on the desk even though it has no closed circulation yet.
    "PTC": "Potential tropical cyclone",
    "PT": "Post-tropical",
    "POST": "Post-tropical",
    "EX": "Extratropical",
    "LO": "Remnant low",
    "DB": "Disturbance",
    "WV": "Tropical wave",
}

# The NHC's bin prefixes, which are the only place the feed says which basin a
# storm is in.
_BASIN = {"AT": "Atlantic", "EP": "Eastern Pacific", "CP": "Central Pacific"}


def _category(intensity: float | None) -> int | None:
    """Saffir-Simpson category, or None below hurricane strength."""
    if intensity is None:
        return None
    for threshold, cat in _CATEGORY:
        if intensity >= threshold:
            return cat
    return None


def _storm_payload() -> Any:
    """The NHC feed, or a fixture when one is named.

    `KUBERA_STORM_FIXTURE=path/to/CurrentStorms.json` is a development seam, not
    a feature: outside a live hurricane the real feed is `{"activeStorms": []}`,
    which is most of the year, and nobody can develop or review the storm layer
    against an empty list. Point it at NHC's own published sample
    (https://www.nhc.noaa.gov/productexamples/NHC_JSON_Sample.json) to draw four
    real systems. Unset, nothing changes.
    """
    fixture = os.environ.get("KUBERA_STORM_FIXTURE")
    if fixture:
        print(f"[weather] storms read from fixture {fixture}", file=sys.stderr)
        with open(fixture, encoding="utf-8") as handle:
            return json.load(handle)
    return _fetch_json(_NHC_STORMS, timeout=30)


def _storms() -> dict:
    try:
        payload = _storm_payload()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # A storm feed that cannot be reached is not the same as a calm ocean,
        # and the desk has to be able to tell the reader which one it is.
        return {"storms": [], "basins": list(_BASIN.values()), "error": str(exc)}

    active = payload.get("activeStorms") or []
    storms = []
    for row in active:
        intensity = _num(row.get("intensity"))
        lat = _num(row.get("latitudeNumeric"))
        lon = _num(row.get("longitudeNumeric"))
        if lat is None or lon is None:
            continue

        code = str(row.get("classification") or "").upper()
        bin_number = str(row.get("binNumber") or "")
        storms.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "classification": code,
                "kind": _CLASSIFICATION.get(code, code or "Storm"),
                "category": _category(intensity),
                "intensity": intensity,
                "pressure": _num(row.get("pressure")),
                "lat": lat,
                "lon": lon,
                "movementDir": _num(row.get("movementDir")),
                "movementSpeed": _num(row.get("movementSpeed")),
                "basin": _BASIN.get(bin_number[:2], "Unknown"),
                "lastUpdate": row.get("lastUpdate"),
            }
        )

    # Strongest first: on a globe covered in dots, the one that matters is the
    # one about to make landfall, not the one that formed first.
    storms.sort(key=lambda s: s["intensity"] or 0, reverse=True)
    return {
        "storms": storms,
        "basins": list(_BASIN.values()),
        "source": "NOAA National Hurricane Center",
    }


def storms() -> dict:
    """Active tropical cyclones the NHC is advising on, behind a TTL."""
    return _cached(("weather", "storms"), _storms, ttl=_STORM_TTL)


# GDACS grades every event it tracks on one three-step scale. Red is the one
# that means people are being moved.
_ALERT_RANK = {"red": 3, "orange": 2, "green": 1}


def _coordinate(pair: Any) -> tuple[float, float] | None:
    """A GeoJSON `[lon, lat]` pair, or None if it is not a real place.

    This is not defensive padding. Checking NASA's EONET against GDACS turned up
    live wildfire records at latitude 200 and longitude 189 — values that are
    not on the planet but that project to a perfectly plausible-looking dot.
    Anything outside the real range is dropped rather than drawn.
    """
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    lon, lat = _num(pair[0]), _num(pair[1])
    if lon is None or lat is None:
        return None
    if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
        return None
    return lat, lon


def _fires() -> dict:
    try:
        payload = _fetch_json(_GDACS_FIRES)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"fires": [], "error": str(exc)}

    fires = []
    dropped = 0
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        where = _coordinate((feature.get("geometry") or {}).get("coordinates"))
        if where is None:
            dropped += 1
            continue

        lat, lon = where
        severity = (props.get("severitydata") or {}).get("severity")
        alert = str(props.get("alertlevel") or "").strip()
        fires.append(
            {
                "id": str(props.get("eventid") or ""),
                "name": props.get("name") or props.get("description") or "Wildfire",
                "country": props.get("country") or "",
                "iso3": props.get("iso3") or "",
                "lat": lat,
                "lon": lon,
                # Burned area, which is what "massive" actually means here.
                "hectares": _num(severity),
                "alert": alert,
                "alertRank": _ALERT_RANK.get(alert.lower(), 0),
                # GDACS keeps an event in the list after it stops burning, which
                # is useful — a fire that burned 60,000 ha last week is still the
                # news — but the two must not look the same on the desk.
                "current": str(props.get("iscurrent") or "").lower() == "true",
                "from": props.get("fromdate"),
                "to": props.get("todate"),
            }
        )

    # Biggest first: the question is which fires are massive, not which started
    # first, and GDACS returns them in no useful order.
    fires.sort(key=lambda f: f["hectares"] or 0, reverse=True)
    return {
        "fires": fires,
        "dropped": dropped,
        "source": "GDACS / Global Wildfire Information System",
    }


def fires() -> dict:
    """Significant wildfires worldwide, largest first, behind a TTL."""
    return _cached(("weather", "fires"), _fires, ttl=_FIRE_TTL)
