"""Generate `dashboard_hub/countries.json` — the world desk's geography.

The hub needs a name, a region and a pair of coordinates for every country
before it can draw anything. That reference is small, changes about never, and
is needed on a clean checkout with no warehouse built, so it is bundled as a
file the way `sectors.json` and `companies.json` already are rather than read
from the marts on every page load.

The warehouse carries the same reference (`marts.dim_country`) and is the source
of truth for macro figures; this file exists so the globe can be drawn before,
and independently of, a dbt run.

    python -m scripts.generate_country_reference

Re-run it when the World Bank admits a member or redraws a region.
"""

from __future__ import annotations

import json
import pathlib
import sys

from ingestion.world_bank_client import WorldBankClient

OUT_PATH = pathlib.Path(__file__).resolve().parents[1] / "dashboard_hub" / "countries.json"

# The same folding `dim_country` applies, kept in step deliberately: the desk
# groups by these names and so does the warehouse.
REGIONS = {
    "East Asia & Pacific": "Asia-Pacific",
    "South Asia": "Asia-Pacific",
    "Europe & Central Asia": "Europe",
    "North America": "North America",
    "Latin America & Caribbean": "Latin America",
    "Sub-Saharan Africa": "Africa",
    "Middle East, North Africa, Afghanistan & Pakistan": "Middle East & North Africa",
}

# The World Bank has no entry for Taiwan — it is not a member — but it has a
# market Kubera charts, so it is added by hand rather than left off the globe.
EXTRA = [
    {
        "iso3": "TWN",
        "iso2": "TW",
        "name": "Taiwan",
        "region": "Asia-Pacific",
        "incomeLevel": "High income",
        "capital": "Taipei",
        "lat": 25.0330,
        "lon": 121.5654,
    }
]


def build() -> list[dict]:
    with WorldBankClient() as client:
        raw = client.fetch_countries()

    countries = []
    for row in raw:
        region = ((row.get("region") or {}).get("value") or "").strip()
        countries.append(
            {
                "iso3": row["id"],
                "iso2": row.get("iso2Code"),
                "name": row["name"],
                "region": REGIONS.get(region, region),
                "incomeLevel": ((row.get("incomeLevel") or {}).get("value") or "").strip(),
                "capital": row.get("capitalCity") or None,
                "lat": round(float(row["latitude"]), 4),
                "lon": round(float(row["longitude"]), 4),
            }
        )

    known = {c["iso3"] for c in countries}
    countries.extend(entry for entry in EXTRA if entry["iso3"] not in known)
    countries.sort(key=lambda c: c["name"])
    return countries


def main() -> int:
    countries = build()
    if len(countries) < 150:
        print(f"only {len(countries)} countries came back — refusing to overwrite", file=sys.stderr)
        return 1

    OUT_PATH.write_text(json.dumps(countries, indent=2, ensure_ascii=False) + "\n")
    regions: dict[str, int] = {}
    for country in countries:
        regions[country["region"]] = regions.get(country["region"], 0) + 1
    print(f"wrote {len(countries)} countries to {OUT_PATH.relative_to(OUT_PATH.parents[1])}")
    for region, count in sorted(regions.items(), key=lambda kv: -kv[1]):
        print(f"  {region:<28} {count:>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
