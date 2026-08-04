"""Company logos and country flags, fetched once and kept.

Both are small images that change about never, and both come from services that
would rather not be hit 300 times every time somebody opens a grid. So they are
fetched on first request, written to `data/image_cache/`, and served from there
until the file is older than `TTL` — at which point the next request refreshes
it. The browser is told to cache them for a day on top of that.

The upstreams:

* **Logos** — Google's favicon service, which resolves a domain to the largest
  icon a site publishes (128–180px for most listed companies). DuckDuckGo's icon
  service is the fallback; it answers for some domains Google does not, but its
  sizes are erratic — 16px for JPMorgan — so it is second, not first. Clearbit
  used to be the obvious choice here and no longer resolves at all.
* **Flags** — flagcdn, keyed by two-letter country code, which is already in
  `countries.json`.

Nothing here raises. A missing logo is a lettermark in the UI, not an error.
"""

from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.error
import urllib.request

_CACHE_DIR = pathlib.Path(__file__).resolve().parents[2] / "data" / "image_cache"
_COMPANIES_PATH = pathlib.Path(__file__).resolve().parents[1] / "companies.json"
_COUNTRIES_PATH = pathlib.Path(__file__).resolve().parents[1] / "countries.json"

# Logos are re-checked monthly. A company rebrands rarely, and when it does,
# nobody is harmed by a month of the old mark.
TTL = 30 * 24 * 3600

_TIMEOUT = 15
_MAX_BYTES = 512 * 1024

# Anything larger than this is not an icon and is refused rather than cached.
_MIN_BYTES = 64

_LOGO_SOURCES = (
    "https://www.google.com/s2/favicons?domain={domain}&sz=256",
    "https://icons.duckduckgo.com/ip3/{domain}.ico",
)
_FLAG_SOURCE = "https://flagcdn.com/w160/{iso2}.png"

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def _fetch(url: str) -> tuple[bytes, str] | None:
    """`(body, content_type)` for an image URL, or None."""
    request = urllib.request.Request(
        url,
        headers={
            # The favicon services return HTML error pages to clients they do
            # not recognise as browsers.
            "User-Agent": "Mozilla/5.0 (compatible; kubera-edw/1.0)",
            "Accept": "image/png,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
            body = response.read(_MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None

    if len(body) > _MAX_BYTES or len(body) < _MIN_BYTES:
        return None
    # A service that has nothing often answers 200 with an HTML page.
    if not content_type.startswith("image/"):
        return None
    return body, content_type


def _cache_path(key: str) -> pathlib.Path:
    return _CACHE_DIR / f"{key}.bin"


def _meta_path(key: str) -> pathlib.Path:
    return _CACHE_DIR / f"{key}.json"


def _read(key: str) -> tuple[bytes, str] | None:
    """A cached image, if one is on disk and still inside its TTL."""
    body_path, meta_path = _cache_path(key), _meta_path(key)
    try:
        if time.time() - body_path.stat().st_mtime > TTL:
            return None
        meta = json.loads(meta_path.read_text())
        return body_path.read_bytes(), meta.get("contentType", "image/png")
    except (OSError, ValueError):
        return None


def _write(key: str, body: bytes, content_type: str) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_bytes(body)
        _meta_path(key).write_text(json.dumps({"contentType": content_type}))
    except OSError:
        # A read-only deployment serves the bytes it just fetched and refetches
        # next time; that is slower, not broken.
        pass


def _domains() -> dict[str, str]:
    """`{ticker: domain}` from the generated universe file."""
    try:
        payload = json.loads(_COMPANIES_PATH.read_text())
    except (OSError, ValueError):
        return {}
    rows = payload.get("companies", payload) if isinstance(payload, dict) else payload
    return {
        row["symbol"]: row["domain"]
        for row in rows
        if isinstance(row, dict) and row.get("symbol") and row.get("domain")
    }


def _iso2() -> dict[str, str]:
    """`{iso3: iso2}` from the country reference."""
    try:
        rows = json.loads(_COUNTRIES_PATH.read_text())
    except (OSError, ValueError):
        return {}
    return {row["iso3"]: row["iso2"] for row in rows if row.get("iso2")}


def logo(symbol: str) -> tuple[bytes, str] | None:
    """The mark for one ticker, from cache or from the web."""
    symbol = (symbol or "").strip().upper()
    if not symbol or not _SAFE.match(symbol.replace("^", "")):
        return None

    key = f"logo_{symbol.replace('.', '_').replace('^', '')}"
    cached = _read(key)
    if cached:
        return cached

    domain = _domains().get(symbol)
    if not domain:
        return None

    for template in _LOGO_SOURCES:
        found = _fetch(template.format(domain=domain))
        if found:
            _write(key, *found)
            return found
    return None


def flag(iso3: str) -> tuple[bytes, str] | None:
    """The flag for one ISO3 country code."""
    iso3 = (iso3 or "").strip().upper()
    if len(iso3) != 3 or not _SAFE.match(iso3):
        return None

    key = f"flag_{iso3}"
    cached = _read(key)
    if cached:
        return cached

    iso2 = _iso2().get(iso3)
    if not iso2:
        return None

    found = _fetch(_FLAG_SOURCE.format(iso2=iso2.lower()))
    if found:
        _write(key, *found)
    return found


def warm() -> dict[str, int]:
    """Pre-fetch every logo and flag. Used by the generator, not by requests."""
    logos = sum(1 for symbol in _domains() if logo(symbol))
    flags = sum(1 for iso3 in _iso2() if flag(iso3))
    return {"logos": logos, "flags": flags}
