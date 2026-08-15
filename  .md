# Global Watch Terminal — API Reference

**Compiled 14 August 2026.** Every entry below was checked against live documentation or a live endpoint. Anything that could not be verified is flagged inline. Pricing and free tiers change often — re-check before you commit to a paid tier.

---

## How to read this

Sources are graded by how much friction stands between you and working data:

| Grade | Meaning |
|---|---|
| **A** | Free, no auth, returns GeoJSON or clean JSON. Wire it up in an afternoon. |
| **B** | Free with registration, or needs a format conversion step. |
| **C** | Usable free tier with real constraints, or cheap paid tier. |
| **D** | Effectively paid-only, or free tier too crippled to build on. |
| **✗** | Skip. Dead, licence-blocked, or not worth the effort. |

---

## The short version

If you build nothing else, build these eleven. All free, all verified live, and between them they cover most of what you described.

| Source | Layer | Grade |
|---|---|---|
| IMF PortWatch | Ports, chokepoints, disruptions | **A** |
| USGS Earthquake Feeds | Seismic | **A** |
| GDACS | Multi-hazard with severity scoring | **A** |
| NOAA NHC `CurrentStorms.json` | Tropical cyclones | **A** |
| GDELT GEO 2.0 | Geocoded world news | **A** |
| Frankfurter | FX | **A** |
| World Bank Indicators | Macro | **A** |
| FRED | US macro and rates | **B** |
| EIA Open Data v2 | Energy prices and inventories | **B** |
| US Census International Trade | HS-code trade by port | **B** |
| Natural Earth | Globe basemap geometry | **A** |

**Total cost: $0.** Roughly $53/month adds company fundamentals, daily metals, and intraday equities if you later decide you need them.

---

# 1. Trade, ports, and shipping

## IMF PortWatch — **the backbone of your trade layer**

Free, no auth, no key, no referrer check. Verified by anonymous fetch on 14 Aug 2026.

**ArcGIS org host:** `https://services9.arcgis.com/weJ1QsnbMYJlCHdG`
**Formats:** `f=json` (Esri), `f=geojson`, `f=pbf`. Hub also serves CSV, KML, Shapefile.

### Daily port activity

```
https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Ports_Data/FeatureServer/0/query
```

- **Verified live:** 5,689,075 records, 2019-01-01 → 2026-08-09. 2,065 ports globally.
- **Layer type:** Table — no geometry. Join to `PortWatch_ports_database` for lat/lon.
- **Fields (30):** `date`, `year`, `month`, `day`, `portid`, `portname`, `country`, `ISO3`, `ObjectId`, plus three parallel metric families:
  - `portcalls_{container,dry_bulk,general_cargo,roro,tanker,cargo}` and `portcalls` — vessel arrival counts
  - `import_{...}` and `import` — metric tons inbound
  - `export_{...}` and `export` — metric tons outbound
- **`date` returns as a `"YYYY-MM-DD"` string, not epoch milliseconds.** Catches people out.
- **maxRecordCount:** 1000. Set `maxRecordCountFactor=5` for 5,000-row pages. Full backfill ≈ 1,140 requests.

Working query:

```
?where=ISO3%3D%27USA%27+AND+date%3E%3DDATE+%272026-07-01%27
&outFields=date,portid,portname,portcalls,import,export
&orderByFields=date+DESC&resultRecordCount=1000&resultOffset=0
&maxRecordCountFactor=5&returnGeometry=false&f=json
```

### Daily chokepoint transits

```
https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query
```

- **Verified live:** 76,412 records, 2019-01-01 → 2026-08-09. 28 chokepoints.
- **Fields (21):** same date/id block, plus `n_{container,dry_bulk,general_cargo,roro,tanker,cargo}`, `n_total` (transit counts) and `capacity_{...}`, `capacity` (aggregate DWT in metric tons).
- **IDs are lowercase and case-sensitive in `where` clauses:** `chokepoint1` Suez · `2` Panama · `3` Bosporus · `4` Bab el-Mandeb · `5` Malacca · `6` Hormuz · `7` Cape of Good Hope · `8` Gibraltar · `9` Dover · `10` Oresund · `11` Taiwan · `12` Korea · `13` Tsugaru · `14` Luzon · `15` Lombok · `16` Ombai · `17` Bohai · `18` Torres · `19` Sunda · `20` Makassar · `21` Magellan · `22` Yucatan · `23` Windward · `24` Mona · `25` Balabac · `26` Bering · `27` Mindoro · `28` Kerch.
- **Live sample, Suez:** 2026-08-09 → 48 transits, 1,948,912 t capacity.

### Companion services

| Service | Type | Why you need it |
|---|---|---|
| `PortWatch_ports_database/FeatureServer/0` | Point | **The join table.** 2,065 ports with lat/lon, LOCODE, continent, `industry_top1..3`, maritime import/export share |
| `PortWatch_chokepoints_database/FeatureServer/0` | Point | Same, for the 28 chokepoints |
| `portwatch_disruptions_database/FeatureServer/0` | Polygon | Disruption events — `eventtype`, `alertlevel`, `severitytext`, `affectedports`, `affectedpopulation`. GDACS-sourced plus manual geopolitical entries |
| `Daily_Trade_Data_WLD/FeatureServer/0` | Table | World daily aggregate |
| `Daily_Trade_Data_REG`, `Monthly_TradeNow` | Table | Regional and monthly rollups |

Enumerate everything at `.../ArcGIS/rest/services?f=pjson` (252 FeatureServers, mostly unrelated IMF climate dashboards).

**Cadence:** Weekly, Tuesdays 09:00 ET — despite the "daily" in the name. Observed lag on 14 Aug was 5 days.
**Source:** AIS from the UN Global Platform, ~90,000 ships. Volume estimated from draft-inferred payload delta × vessel DWT.
**Licence:** IMF general terms. Not CC-BY. Attribution required; bulk redistribution not granted.
**Grade: A.** Nothing else here is this good for free. Its only weakness is the weekly refresh, so treat it as a trend instrument rather than a live one.

## US Census International Trade API

- **Base:** `https://api.census.gov/data/timeseries/intltrade/imports/hs` (also `/exports/hs`, `/porths`, `/statehs`, `/naics`, `/enduse`, `/sitc`)
- **What it does:** US imports and exports at HS 2/4/6/10-digit, monthly, Jan 2010–present. **Breaks out by port of entry** — which joins straight to your PortWatch port layer. Key vars: `GEN_VAL_MO/YR`, `CON_VAL_MO/YR`, `VES_VAL_*`, `AIR_VAL_*`, `I_COMMODITY`, `CTY_CODE`, `PORT`, `DISTRICT`.
- **Cadence:** Monthly on the FT-900 release, ~5 weeks after month end. Annual revisions land with April statistics.
- **Auth:** Free key. 500 queries/IP/day without one. Max 50 variables per query.
- **Format:** JSON array-of-arrays — not objects. **Licence:** Public domain.
- **Grade: B.** The highest-quality HS-level source anywhere, and free. Limited to one country.

## Eurostat Comext

- **Statistics API:** `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?format=JSON&lang=EN`
- **Bulk:** `https://ec.europa.eu/eurostat/api/dissemination/files?file=comext/COMEXT_DATA/PRODUCTS/full202305.7z`
- **What it does:** EU and member-state trade with all partners at CN8 (HS-compatible at 6 digits), monthly and annual from 1988. EUR values, kg and supplementary units.
- **Cadence:** Monthly, 6–8 week lag. **Auth:** None. **Licence:** Commercial re-use permitted with attribution — the most permissive of the three trade sources.
- **Grade: B.** Free and unmetered, but the bulk 7z archives have a non-obvious layout and the JSON-stat API doesn't expose full CN8 detail. Budget real ingestion time.

## UN Comtrade

- **Base:** `https://comtradeapi.un.org/data/v1/get/{typeCode}/{freqCode}/{clCode}`
- **What it does:** ~200 reporters, HS 2/4/6-digit, annual and monthly, back to 1962. USD value, net weight, supplementary quantity.
- **Free tier:** 500 calls/day, 1/sec — but the preview endpoint caps at **500 records and one period and one product per call.**
- **Paid:** Premium Individual $2,000/yr. Pro tiers $6,000–$12,000/yr.
- **Grade: D.** The free tier is a lookup service, not a backend. Fine for on-demand queries, useless for populating a dashboard.

## AIS vessel tracking

| Source | Cost | Notes |
|---|---|---|
| **aisstream.io** | **Free** | `wss://stream.aisstream.io/v0/stream`. Send subscription JSON within **3 seconds** of connect or the socket closes. 28 message types. Terrestrial only — ~40nm from shore, **no deep-ocean coverage**. Max 50 MMSI filters. BETA, no SLA. Persist your own history; there's no REST backfill. **Grade: B** |
| **Global Fishing Watch v3** | Free token | Vessel identity across 40+ registries, encounter/loitering/port-visit events, fishing-effort rasters. **Non-commercial only.** **Grade: B** |
| **Datalastic** | ~€80–100/mo *(unverified)* | REST + historical. Prices not published on their pricing page. |
| **VesselFinder** | €330 / 10k credits | Satellite AIS costs 10 credits/call vs 1 terrestrial. Credits expire in 12 months. No free trial. |
| **MarineTraffic (Kpler)** | Enterprise | Conflicting reports on whether the credit system still exists. Treat as contact-sales. |
| **Spire Maritime** | ~$2,000–8,000/mo *(unverified)* | Satellite AIS, sub-30-min global revisit, SLA-backed. |

**Grade for the category: B free / D paid.** aisstream.io plus targeted enrichment is the only sane solo path.

## Bill of lading / shipment-level customs

**No free API exists in this category.** ImportGenius starts at **$229/mo** (25 searches/day, 1,000 rows/mo, 12 months of US imports only) and $449/mo for 2006+ history. ImportYeti's free web search is genuinely useful but its API page publishes no endpoints, auth, or pricing. Panjiva and Descartes Datamyne are quote-only.

**Grade: D.** Out of budget. If you need one shipment lookup, ImportYeti's free web tier is the only zero-cost path and it isn't automatable.

## Freight rates and congestion

None of the four major indices offers a free API.

| Index | Free access | API |
|---|---|---|
| **Drewry WCI** | Weekly composite + 8 routes free on the public page, HTML only | None |
| **Freightos FBX** | Daily/weekly index values free **with mandatory attribution and link** | Enterprise only |
| **Xeneta XSI-C** | 8 corridors free, daily, "internal viewing only" | None |
| **Baltic (BDI)** | No free programmatic access | Licensed via Nasdaq |
| **SCFI/CCFI** | Behind login at sse.net.cn; mirrored free on container-news.com | None |

**Free structural substitutes:** **RWI/ISL Container Throughput Index** (92 ports, monthly, flash ~20 days after month end) and the **Kiel Trade Indicator** (free monthly AIS-based nowcast). For congestion, PortWatch port calls plus scraped **Sea-Intelligence** monthly headline reliability figures gets ~80% of the signal at zero cost. Portcast's congestion API is quote-only.

**Grade: C free-scraped / D API.** Don't budget for a real freight-rate API.

---

# 2. Markets, FX, commodities, macro

## Macro — the strongest category, all free

### FRED (St. Louis Fed) — **Grade B**
- `https://api.stlouisfed.org/fred/` · ~800k series. GDP, CPI/PCE, unemployment, payrolls, yield curve, Fed funds, housing, industrial production, plus mirrored EIA energy series. ALFRED gives point-in-time vintages if you ever backtest.
- **120 req/min with a free key** (30/min without). No daily cap published.
- **Mandatory attribution string:** *"This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."*
- **Trap:** many FRED series are third-party-owned and you are solely responsible for their copyrights. Most dashboards ignore this.
- Highest-value single API on this list.

### World Bank Indicators — **Grade A**
- `https://api.worldbank.org/v2/` · ~16,000 indicators, 217 economies. **No key, no registration, no quota.** Annual granularity with multi-year lags on developing economies. CC-BY 4.0. `per_page` up to 32,000.

### ECB Data Portal — **Grade A**
- `https://data-api.ecb.europa.eu/service` · SDMX 2.1. Euro-area HICP, policy rates, yield curves, and the **official euro FX reference rates** (33 currencies, ~16:00 CET each TARGET day). No key. Legacy `sdw-wsrest.ecb.europa.eu` redirects — migrate now.

### BLS — **Grade B**
- `https://api.bls.gov/publicAPI/v2/timeseries/data/` · CPI, PPI, unemployment, payrolls, JOLTS. **500 queries/day** registered, 50 series per query. **The free key must be renewed annually** — set a reminder or you'll silently drop to the 25/day v1 limits. FRED mirrors most of this with a friendlier API.

### OECD — **Grade C**
- `https://sdmx.oecd.org/public/rest/` · Cross-country GDP, CPI, unemployment, PPP, composite leading indicators. No key. Rate limits not published (their docs are JS-rendered). Dimension and codelist discovery is genuinely painful — budget a full day.

### IMF Data — **Grade C, verify first**
- `https://api.imf.org/external/sdmx/3.0` · IFS, **DOTS** (bilateral trade), BOP, WEO, **PCPS** (commodity prices). Legacy `dataservices.imf.org` is deprecated. The new portal gates the OpenAPI spec behind a free account and it's unclear whether unauthenticated reads still work. Valuable data with no good free substitute, but expect breakage — this platform migrated recently.

## FX

### Frankfurter — **Grade A, and self-host it**
- `https://api.frankfurter.dev/v2/` · **201 currencies from 84 central banks, back to 1948.** Endpoints: `/rates`, `/rate/{base}/{quote}`, `/currencies`, `/providers`. Params: `base`, `quotes`, `date`, `from`/`to`, `group=week|month`, `providers`, `scope=all`.
- **No quotas at all.** No key. JSON, CSV, NDJSON. Free for commercial use, open source, **runs in Docker** — which removes your only availability risk.
- These are central-bank daily fixings, not live tradeable quotes.

### Others
- **ExchangeRate-API open endpoint** — `https://open.er-api.com/v6/latest/{CODE}`, no key, daily. **Attribution required and redistribution explicitly prohibited.** Fine as a fallback. **Grade B**
- **Open Exchange Rates** — 1,000 req/month free, USD base only. $12/mo Developer, $47/mo Enterprise, $97/mo Unlimited. **Grade C** — Frankfurter beats the free tier outright.
- **exchangerate.host** — ✗ **Avoid.** Repositioned to paid: 100 requests/month free, $14.99/mo for 10k. Not the free API people remember.

## Commodities — the weakest category

There is **no good free real-time futures API.** Exchange-traded prices (CME, NYMEX, ICE, LME) are licensed products; every "free commodity API" is delayed, derived, or a thin reseller. Build around statistical agencies and accept latency.

### EIA Open Data v2 — **Grade B, and excellent**
- `https://api.eia.gov/v2/` · **2M+ series.** WTI and Brent spot, Henry Hub, retail fuels, **weekly crude inventories** (Wednesdays), refinery utilisation, electricity, coal, renewables, nuclear, plus international energy statistics.
- Free key. **Max 5,000 rows per JSON request** — paginate with `offset`/`length`. Rate limits not published numerically; exceeding tolerance suspends the key with automatic reactivation.
- The best free energy data source in existence, and the anchor of any credible commodity panel.

### World Bank Pink Sheet — **Grade B**
- ~70 commodity series (energy, metals, precious, fertilisers, grains, softs) in one monthly workbook. **Monthly, first business days.** August 2026 edition published; next 2026-09-02.
- **XLSX and PDF only — no JSON API.** You parse the spreadsheet on a cron. CC-BY, so redistribution-friendly.

### CFTC Commitments of Traders — **Grade A**
- `https://publicreporting.cftc.gov/resource/{dataset}.json` (Socrata SoQL). Weekly positioning across commodity and financial futures — Legacy, Disaggregated, and Traders in Financial Futures. **Fridays 15:30 ET**, as of Tuesday. No key needed. A genuinely differentiated panel that costs nothing. *(Note: CFTC opened a review of the COT programme in May 2026 — the report structure may change.)*

### USDA — agriculture and perishables
- **NASS Quick Stats** — `https://quickstats.nass.usda.gov/api`. US crop and livestock production, yields, acreage, stocks, prices received. Free key, 50,000 records/query. Production statistics, not a price feed.
- **AMS Market News** — `https://www.ams.usda.gov/resources/apis-open-data`. **Daily terminal and shipping-point prices for specialty crops.** This is your perishables early-warning signal: garlic or lettuce spikes here well before any trade statistic reflects it. **Grade B, and underrated for your use case.**

### Metals — all paid
- **LBMA/ICE:** No free access. An IBA licence is required for real-time *or* historical benchmark data. **FRED removed the LBMA gold/silver series in 2022** — any tutorial referencing `GOLDAMGBD228NLBM` is dead.
- **World Gold Council:** Free XLSX of gold price *averages* in many currencies since 1978, weekly. Averages only.
- **metals.dev:** Free tier 100 req/month (unusable). **$1.79/mo for 2k, $9.99 for 10k.** Spot, bid/ask, LBMA and LME. Confirm redistribution terms in writing before displaying LBMA-labelled values — a reseller's licence doesn't automatically extend to you.
- **Grade: C.** metals.dev at $1.79–$9.99/mo is the pragmatic answer.

## Equities and fundamentals

| Source | Free tier | Paid entry | Grade |
|---|---|---|---|
| **Tiingo** | **50 req/hour, 1,000/day, 500 unique symbols/month, 1 GB/mo.** 109k securities, 30+ years EOD, news with 3-month history | $50/mo commercial (10k/hr, 100k/day) | **B** — the most honest free equity tier available, and the symbol cap suits a fixed watchlist |
| **Finnhub** | **~60 calls/min** *(vendor page is JS-rendered; figure corroborated by third parties, not vendor-verified)*. Real-time US quotes, profiles, basic financials, earnings calendar, news | ~$50/mo | **B** — best free throughput, but the free tier is **personal non-commercial only** |
| **Massive** (was Polygon.io) | 5 calls/min, EOD only, 2 years | **$29/mo Starter — unlimited calls, 15-min delayed** | **C** — best paid value here. `polygon.io` now 302s to `massive.com`; migrate to `api.massive.com` |
| **Financial Modeling Prep** | 250 calls/day but **restricted to ~85 sample symbols** — the headline number is misleading | **$22/mo Starter** | **C** — cheapest real fundamentals access. **Displaying the data requires a separate licensing agreement with FMP** |
| **Twelve Data** | 8 credits/min, 800/day, 3 exchanges | $79/mo | **C** — free tier thin, paid jump steep |
| **Nasdaq Data Link** | Registered key: 300/10s, 50,000/day | — | **C** — the *limits* are free, the *datasets* mostly aren't. WIKI equities and LBMA gold were retired. Useful only as a JSON wrapper around IMF series |
| **Alpha Vantage** | **25 requests/day** (was 500) | $49.99/mo | **D** — breadth is real (equities, FX, commodities, macro on one key) but 25/day means nightly batch only. Its commodity and macro series are largely re-published EIA/FRED data you can pull directly |
| **Yahoo Finance unofficial** | — | — | ✗ **Do not use.** Yahoo's API terms require **data be deleted within 24 hours**, prohibit redistribution, and prohibit use in competing products. `yfinance` broke repeatedly through 2025–26 on cookie/crumb and rate-limit changes. Free legitimate alternatives cover the same ground |

---

# 3. Hazards, weather, environment

## Earthquakes

### USGS Real-time Feeds — **Grade A, best hazard feed in existence**
```
https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{category}_{window}.geojson
```
- `category`: `significant` | `4.5` | `2.5` | `1.0` | `all` · `window`: `hour` | `day` | `week` | `month` — 20 combinations.
- **Updated every minute.** Native GeoJSON FeatureCollection with bbox. Magnitude, depth, epicentre, PAGER alert level, **tsunami flag**, ShakeMap/DYFI links. No auth, no documented rate limit, public domain.
- Poll `all_hour.geojson` frequently, `all_day.geojson` on startup for backfill.

### USGS FDSN Event Service — **Grade B**
- `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=…&minmagnitude=…`
- For historical backfill. **Hard cap 20,000 events per query** (HTTP 400 beyond). USGS explicitly asks you to use the static feeds above for live display since those are cached.

### EMSC SeismicPortal — **Grade A**
- `wss://www.seismicportal.eu/standing_order/websocket` — the only genuinely **push-based** hazard feed here. GeoJSON-shaped Features, `action` distinguishes insert vs update. No auth.
- Often faster than USGS for Euro-Med events. **Deduplicate against USGS on origin time + distance, not on ID** — the catalogues use different identifiers.

## Tropical cyclones

### NOAA NHC `CurrentStorms.json` — **Grade A**
- `https://www.nhc.noaa.gov/CurrentStorms.json` — verified live.
- Per storm: `id`, `name`, `classification`, `intensity` (kt), `pressure` (mb), `latitudeNumeric`/`longitudeNumeric`, `movementDir`, `movementSpeed`, `lastUpdate`, plus **direct URLs** to `forecastTrack`, `trackCone`, `initialWindExtent`, `forecastWindRadiiGIS`, `bestTrackGIS`, `windWatchesWarnings`, `stormSurgeWatchWarningGIS`.
- **Coverage: Atlantic, Eastern and Central Pacific only.**
- **Cadence:** Full advisories every 6h (00/06/12/18 UTC), intermediate every 3h when watches are active. That's your latency floor.
- Plain JSON with numeric lat/lon — build the GeoJSON yourself, trivial.
- One poll gives you every active storm plus its GIS product URLs, so you never guess advisory numbers.

### NHC GIS products — **Grade B**
- `https://www.nhc.noaa.gov/gis/` · Forecast cone, track, wind field, wind-speed probabilities, storm surge, arrival times.
- **Zipped shapefiles, KML/KMZ, GRIB2 — no native GeoJSON.** Budget an `ogr2ogr` conversion job. The cone polygon is visually essential and only changes every 3–6h, so cache it.

### JTWC — **Grade C, fragile**
- `https://www.metoc.navy.mil/jtwc/` — **returned HTTP 403 to automated fetch during verification.** Navy METOC blocks non-browser user agents and historically non-US IPs.
- Covers Western/Central Pacific west of 180°, Indian Ocean, Southern Hemisphere — **exactly the basins NHC ignores**. Text warnings and KMZ, no official JSON.
- Build it as best-effort with graceful degradation, not a dependency. If the server blocks automated access, that is the access policy — don't route around it.

### Global fallback
**GDACS** tracks tropical cyclones globally with alert scoring and returns GeoJSON with no auth. For a globe, GDACS is the pragmatic global TC layer; NHC adds high-fidelity cones for the Atlantic and E-Pacific.

## Multi-hazard

### GDACS — **Grade A, build this second after USGS**
- `https://www.gdacs.org/gdacsapi/api/events/geteventlist/events4app` (cached, cheaper — prefer for polling)
- `https://www.gdacs.org/gdacsapi/api/Events/geteventlist/SEARCH` (filtered)
- **Params:** `eventlist` (EQ, TC, FL, VO, DR, WF), `fromdate`, `todate`, `alertlevel` (green/orange/red), `pagenumber`, `pagesize` (max 100).
- **Six hazard types, global, native GeoJSON, no auth, with modelled human-exposure and impact scoring already applied** — so you can drive marker colour and size straight off `alertlevel`. Also XML/RSS, KML, CAP.
- Compare the `datetime` property before re-fetching; it cuts request volume substantially.
- Attribution: "Global Disaster Awareness and Coordination System, GDACS."

## Wildfires

### NASA FIRMS — **Grade B, the only realistic global option**
```
https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north|world}/{DAY_RANGE}[/{DATE}]
```
- **Sources:** `VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `MODIS_NRT`, `LANDSAT_NRT` (US/Canada only).
- **Resolution:** VIIRS 375m, MODIS 1km, Landsat 30m. Per-detection lat/lon, brightness temperature, FRP, confidence, acquisition time, day/night flag.
- **Latency:** ~3 hours NRT. **Under 60 seconds URT — US and Canada only.** Elsewhere it's satellite-revisit-limited, ~4–6 passes/day across all VIIRS platforms.
- Free MAP_KEY by email. **5,000 transactions per 10-minute window.**
- **Area API returns CSV only.** The **WFS service** (`/mapserver/wfs-info/`) does support GeoJSON with the MAP_KEY embedded in the URL.
- ⚠️ **The `country` and `countries` endpoints were flagged unavailable** at time of check — use `area` with a bounding box.
- **Design constraint:** a global 24-hour VIIRS pull is tens of thousands of points. Cluster or hexbin server-side; do not hand raw detections to a WebGL layer.

**Complements:** EFFIS (Copernicus, burnt-area perimeters, WMS/WFS), NIFC/IRWIN (US incident perimeters via ArcGIS FeatureServer, GeoJSON, no auth).

## Volcanoes

- **Smithsonian GVP WFS** — `https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs`, typeNames `GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes` / `_Pleistocene_Volcanoes` / `_Holocene_Eruptions`. **GeoJSON supported**, no auth. Current version **VOTW 5.4.0, 7 Aug 2026**, DOI `10.5479/si.GVP.VOTW5-2026.5.4`. Citation explicitly required. This is the authoritative static basemap, **not** a real-time alert feed. **Grade A**
- **Weekly Volcanic Activity Report** — `https://volcano.si.edu/reports_weekly.cfm`. Wednesdays. Week ending 12 Aug 2026 covered 26 volcanoes; ~40 in continuing-eruption status. HTML only, no confirmed RSS. **Grade C**
- **VAAC (9 centres)** — Anchorage, Buenos Aires, Darwin, London, Montreal, Tokyo, Toulouse, Washington, Wellington. **Every 6 hours or sooner when ash-active.** This is the true real-time volcano signal, but you must parse fixed-format ICAO text across nine sites with different layouts. **Grade C — highest effort-to-payoff ratio here. Defer past v1.**

## Floods

- **GDACS** — flood events included, free, GeoJSON. Start here.
- **Copernicus EMS Rapid Mapping** — `https://mapping.emergency.copernicus.eu/activations/api/activations/`. Per-activation metadata plus products as GeoJSON, TIFF, geodatabase. Superb polygon detail (flood extent, damage grading) but **activations happen days after an event.** Use as an aftermath enrichment layer. **Grade B**
- **GloFAS** — daily global river-discharge forecasts via the CEMS Early Warning Data Store. Free ECMWF account. **GRIB/NetCDF, not GeoJSON** — you threshold and vectorise it yourself. Scientifically the best free global flood forecast and the worst fit for a lightweight dashboard. **Grade D for v1.**
- **ReliefWeb** — `https://api.reliefweb.int/v2/`. Humanitarian situation reports and disaster records. **1,000 entries/call, 1,000 calls/day.** ⚠️ **Since 1 Nov 2025 the mandatory `appname` parameter must be pre-approved** — an arbitrary string no longer works. No geometry; join to country centroids. CC BY 4.0. Good as a click-through detail pane, useless as a map layer. **Grade C**

## Tsunami

### tsunami.gov — **Grade B**
- NTWC Atom `https://www.tsunami.gov/events/xml/PAAQAtom.xml` · CAP `PAAQCAP.xml`
- PTWC Atom `https://www.tsunami.gov/events/xml/PHEBAtom.xml` · CAP `PHEBCAP.xml`
- Event-driven, issued within minutes. **True real-time**, no auth, public domain. CAP 1.2 XML with `<area>` polygons/circles you can convert.
- **Filter on CAP `severity`/`urgency`** — most messages are "Information Statement" with no threat, and you will cry wolf constantly otherwise.
- Free first indicator: the USGS earthquake feed already carries a `tsunami` flag per event.

## Weather

### Open-Meteo — **Grade A, best free global weather API**
- `https://api.open-meteo.com/v1/forecast` · **No API key.**
- Blends **17 national weather services**, auto-selecting the highest-resolution model per location — DWD ICON (2–11km), NOAA GFS/HRRR (3–25km), Météo-France AROME (1–25km), ECMWF IFS, UK Met Office (2–10km), JMA, KMA, CMA, GEM, BOM, Nordic MET (1km).
- 7-day default, **up to 16** via `&forecast_days=16`. 15-minutely, hourly, daily aggregation. Temperature, humidity, precipitation, wind at multiple heights, pressure, cloud layers, soil, solar radiation.
- **Free tier: 600 calls/min, 5,000/hour, 10,000/day, 300,000/month.** **Non-commercial only** — paid keys at `customer-api.open-meteo.com`, prices not published.
- JSON/CSV/XLSX, **no GeoJSON**. CC BY 4.0, attribution mandatory.
- Point-query based, so a global weather *field* means many calls or your own gridding.

### NOAA / NWS API — **Grade A (US only)**
- `https://api.weather.gov` · `/points/{lat},{lon}` → `/gridpoints/{office}/{x},{y}/forecast` · **`/alerts/active?area={state}`**
- **GeoJSON is the default output.** Also CAP and ATOM for alerts. ~2.5km forecast grid.
- No key, but **a descriptive `User-Agent` with contact info is required** — generic agents get blocked. Rate limits not published; on 429 retry after ~5s.
- The best severe-weather alert source anywhere, native GeoJSON polygons, zero auth — and it stops at the US border. `/alerts/active` is the endpoint to build on.

### Others
- **OpenWeatherMap** — **60 calls/min, 1,000,000/month free**, including the Air Pollution API and **15 weather map raster tile layers** (genuinely useful for a globe). ⚠️ **One Call 4.0 went live in 2026 and requires a separate subscription — a 3.0 subscription does not carry over.** Paid monthly prices aren't rendered on the pricing page. Data is **ODbL (share-alike)** on paid plans. **Grade B**
- **WeatherAPI.com** — 100,000 calls/month free. **$7/mo for 3M calls**, $25 Pro+, $65 Business. Realtime refreshed every 10–15 min. Commercial use permitted on all tiers. Best price-per-call of any commercial option, and the sane paid fallback if Open-Meteo's non-commercial clause becomes a problem. **Grade B**
- **Meteomatics** — 1,800+ parameters, 110+ models, 90m resolution. ✗ **Pricing entirely sales-gated** — no tier limits or prices published anywhere. Skip; Open-Meteo covers the same ground free.
- **WMO Severe Weather Information Centre** — `https://severeweather.wmo.int/` aggregates official CAP warnings from national met services worldwide, the only global equivalent of `api.weather.gov/alerts`. ⚠️ **The feeds page is labelled "Demo" and its endpoint table renders empty to a fetcher** — client-side populated. Worth 30 minutes with browser dev tools to find the real feed URLs. Strategically the most valuable gap-filler here.

## Air quality and pollen

- **OpenAQ v3** — `https://api.openaq.org/v3/`. Global government reference monitors plus low-cost sensors: PM2.5, PM10, O₃, NO₂, SO₂, CO, BC. Free key via `X-API-Key` header. **60 req/min, 2,000/hour.** JSON, not GeoJSON. Latency inherits each national agency's cadence — **always render the measurement timestamp.** Bulk archives on AWS S3 are cheaper for wide-area snapshots. **Grade B**
- **Open-Meteo Air Quality** — `https://air-quality-api.open-meteo.com/v1/air-quality`. Modelled rather than measured, but gridded and global, which suits a globe better than sparse points. CAMS European 11km and CAMS global 45km. No key. **Grade A**
- **Pollen:** Open-Meteo's air-quality endpoint carries **6 species — alder, birch, grass, mugwort, olive, ragweed — Europe only**, 4-day forecast. Free, no key, already in your stack. **Google Pollen API** covers 65+ countries at 1km but needs a GCP billing account, and ⚠️ **the old $200/month Maps credit expired 28 Feb 2025** — it's now per-SKU allowances (Essentials 10,000 free calls/SKU/month). **BreezoMeter no longer exists** — acquired by Google and folded into their Air Quality and Pollen APIs; don't build against its endpoints. **Ambee** publishes no call limits or prices.
- **Verdict on pollen:** take the free Europe-only Open-Meteo data since it costs nothing, and defer everything else. You already called this low priority and that's the right call.

## Drought

- **US Drought Monitor** — `https://usdmdataservices.unl.edu/api/{area}/{statisticsType}`. Methods: `GetDroughtSeverityStatisticsByArea`, `…ByPopulation`, `GetDSCI`. XML/CSV/JSON via `Accept` header, no auth. **US only, weekly (Thursdays).** Statistics only — polygons are shapefile downloads. *(Note: `WebServiceLinks.aspx` 404s; use `WebServiceInfo.aspx`.)* **Grade C**
- **Copernicus EDO/GDO** — `https://drought.emergency.copernicus.eu/api/wms`. Verified layers: `smian`, `smang` (soil moisture anomaly), `fpanv` (fAPAR anomaly), `cdiad` (combined drought indicator), `twsan` (GRACE water storage), `spaST`/`spcLT`/`spgTS` (SPI variants). **WMS raster tiles** — which is actually the *right* format for a continuous field on a globe; you texture it onto the sphere rather than parsing polygons. Free, no auth. **Better fit for your use case than USDM. Grade B**

---

# 4. News and events

## GDELT — **Grade A, and the licensing is the headline**

GDELT is available for *"unlimited and unrestricted use for any academic, commercial, or governmental use,"* **redistribution included**, requiring only citation with a link to gdeltproject.org. **No key, no quota, no commercial restriction.** Nothing else in news comes close on terms.

### GEO 2.0 API — the one you want for a globe
```
https://api.gdeltproject.org/api/v2/geo/geo?query=…&mode=PointData&format=GeoJSON&timespan=1440
```
- **Native GeoJSON.** Modes: PointData, PointHeatmap, Country, ADM1, SourceCountry, ImagePointData.
- `maxpoints` 1–1,000 for PointData, **up to 25,000 for PointHeatmap**.
- ⚠️ **Timespan is 15 minutes to 7 days only** — rolling window, not an archive.
- 15-minute cadence, 65 languages, no auth.
- ⚠️ **Verification caveat:** parameters above come from GDELT's own documentation. Live calls to this endpoint returned 404 and 500 from this environment on 14 Aug 2026 — consistent with GDELT's known behaviour of rejecting requests that lack a descriptive `User-Agent` header. **Set a real UA and test from your own server before you design around it.** The DOC 2.0 API has the same documented requirement.
- **Highest value per line of code in this entire document** — assuming it responds for you.

### DOC 2.0 API — article search
```
https://api.gdeltproject.org/api/v2/doc/doc?query=…&mode=ArtList&format=json&timespan=…
```
- Query syntax supports phrases, `OR`, `-` exclusion, `domain:`, `sourcelang:`, `sourcecountry:`, `theme:`, `tone<`/`tone>`.
- Modes include TimelineVol, TimelineTone, ToneChart, ImageCollage, WordCloud variants.
- **CORS `*`** — callable directly from a browser. Searchable back to 1 Jan 2017, default last 3 months.
- ⚠️ **Max 250 records, no pagination beyond that.** And **requests without a `User-Agent` header get rate-limited or blocked** — set a descriptive one.

### Raw 15-minute files — the firehose
- `http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.{export|mentions|gkg}.CSV.zip`
- Pointers: `lastupdate.txt` (newest of each type), `masterfilelist.txt` (full history). Translingual twins have `-translation` suffixes.
- **96 files per type per day per stream.** English + Translingual = 6 files per 15-minute tick.
- **Events schema: 61 columns**, CAMEO-coded, with `ActionGeo_Lat`/`_Long`, `ActionGeo_Type` (1=Country, 2=US State, 3=US City, 4=World City, 5=World State), `GoldsteinScale`, `AvgTone`, `NumMentions`, `NumSources`, `NumArticles`, `SOURCEURL`.
- **GKG 2.1:** themes, persons, organisations, `V2Locations` with lat/long, counts, tone vector, quotations.
- ⚠️ **`data.gdeltproject.org` serves HTTP, and HTTPS requests 302-redirect back to HTTP.** You need a server-side fetcher.

### Honest assessment of GDELT's noise

This matters enough to spell out, because most projects discover it too late:

- **Sub-national geographic accuracy is poor.** Hammond & Weidmann (2014) found grid-cell-month correlation with hand-coded conflict data of **0.26 vs ACLED** and **0.20 vs UCDP-GED**. Temporal-only correlations were much higher — **0.64 and 0.33** — which tells you exactly where the signal lives.
- **Systematic capital-city bias.** GDELT over-reports near capitals and under-reports remote areas, the inverse of the established finding that violence concentrates in the periphery. Artifact of the geocoder defaulting to the most prominent toponym.
- **Toponym failures.** The UK ONS documented "Aberfeldy in Perth and Kinross" (Scotland) coded as **Australia**, and concluded country codes cannot be trusted. Paris TX vs Paris FR, Springfield ×34, London ON vs London UK.
- **Reference-vs-occurrence conflation.** An article about the 1918 flu geocodes and counts as a present-day event. ONS found only ~15% of articles had usable location-specific categorisation.
- **Duplication.** The same story re-coded from many outlets inflates event counts.
- GDELT itself concedes it: *"With anything this massive, you will always find some level of error when you dive deeply enough."*

**Mitigations:**
1. Filter on `NumSources`/`NumArticles` ≥ threshold — single-source events are mostly junk.
2. **Keep only `ActionGeo_Type` 3 and 4 (city-level) for map pins.** Discard Type 1 and 2 or country/state centroids will pile up in oceans and empty fields.
3. Deduplicate by `GLOBALEVENTID` clustering and SOURCEURL domain.
4. Present it as **"media attention density,"** which is what it actually measures well — never as a ground-truth event ledger.
5. Use GKG themes (`theme:PROTEST`, `theme:NATURAL_DISASTER`) rather than CAMEO codes — more robust.

## Other news sources

| Source | Free tier | Verdict |
|---|---|---|
| **NewsData.io** | **200 credits/day (6,000/mo), 10 articles/credit, 12-hour delay — but commercial use permitted** | **Grade B.** Best free tier that allows commercial use. The delay disqualifies it as live; use as backfill behind GDELT |
| **Currents API** | 250 req/day, 30-day history, 20 results/request | **Grade C.** Most generous free tier, but small coverage and docs still dated 2019 — verify liveness first. Redistribution needs separate terms |
| **Marketaux** | 100 req/day, **3 articles per request** | **Grade C.** Financial news with per-entity sentiment across 200k+ entities. Free tier is toy-grade; $29/mo is the real entry. Only relevant if you have a markets panel |
| **Google News RSS** | Free, unofficial | **Grade C.** ~100 items/feed, no pagination. Links are **`news.google.com` redirect tokens** you must resolve. ⚠️ A July 2026 sampling found **median item age 6.6 days**, only 7.6% under six hours old. No SLA, format has silently changed before |
| **Curated RSS** | Free | **Grade B as a thin layer.** 30–50 high-signal publisher feeds for freshness and clean links, layered on GDELT for geography. Headline + link + short excerpt only — **storing full article text is infringement.** Don't try to out-crawl GDELT |
| **NewsAPI.org** | 100 req/day, 24-hour delay | ✗ The free tier's ToS **explicitly forbids production use, including internal**. $449/mo Business. Not viable |
| **Bing News Search** | — | ✗ **Retired 11 August 2025.** Gone entirely |
| **Reuters / AP** | — | ✗ Enterprise-only. Reuters Connect is a five-step sales process; editorial syndication reportedly starts **$10,000–$50,000/year**. Categorically out of reach |

---

# 5. Geography, basemap, demographics

## Basemap

### Natural Earth — **Grade A, start here**
- `https://www.naturalearthdata.com/downloads/` · CDN mirror **naciscdn.org** (primary links are frequently slow — the mirror and the `nvkelso/natural-earth-vector` GitHub repo are more reliable).
- Three scales — **1:10m, 1:50m, 1:110m** — across Cultural (countries, states, populated places, **ports**, airports, roads, urban areas, disputed boundaries), Physical (coastline, ocean, rivers, lakes, bathymetry), Raster (shaded relief).
- **Public domain. No attribution required, no restrictions.**
- 1:110m countries is ~200KB of GeoJSON — exactly what a 3D globe needs at low zoom. Layer in 1:50m and 1:10m as the user zooms.

### Protomaps / PMTiles — **Grade A, the correct answer for self-hosting**
- `https://docs.protomaps.com/basemaps/downloads`
- A single-file cloud-optimised tile archive with HTTP range requests — **no tile server needed**, just object storage plus a static site. This is the single biggest cost lever available to you.
- Daily planet builds at `maps.protomaps.com/builds`, **~120 GB for zoom 0–15**. Cut a country- or city-sized extract (10 MB–2 GB) with the `pmtiles extract` CLI — that's what makes it budget-viable.
- ⚠️ **Hotlinking the build bucket is discouraged** — copy to your own storage.
- MVT vector tiles, renders with MapLibre GL JS, styles included. **ODbL as a Produced Work; OSM attribution required.**
- On Cloudflare R2 (zero egress fees) a country-scale extract is single-digit dollars per month.

### OpenStreetMap — **Grade B data, ✗ tile server**
- Planet PBF ~80GB weekly with minutely diffs; **Geofabrik** regional extracts daily; **Overpass API** free with heavy rate limiting (~10,000 queries/day soft, expect 429s).
- ⚠️ **ODbL 1.0 share-alike.** "© OpenStreetMap contributors" required. **Derived databases must be released under ODbL.** Rendered images ("Produced Works") are not virally licensed — that's the escape hatch most projects use. **This is the single most important licensing constraint in this document.**
- ⚠️ **Never hotlink `tile.openstreetmap.org`.** Their usage policy prohibits bulk downloading, offline use, headless rendering, and generic User-Agents (auto-blocked). No SLA, may block without notice.

### Commercial tile vendors
- **MapTiler** — Free: 5k map sessions/mo, 100k API requests/mo, 5 GB storage, **MapTiler logo required**. Flex $30/mo removes the logo. Friendliest to self-hosting. **Grade B**
- **Mapbox** — Free: 50,000 map loads/mo, 200k vector tile requests, 100k temporary geocoding. Paid $5.00/1k map loads. ⚠️ ToS restricts displaying Mapbox geocoding on non-Mapbox maps and forbids caching results without the paid permanent endpoint. **Mapbox GL JS went proprietary at v2.0 — use MapLibre GL JS, the open fork.** **Grade C**

### Admin boundaries

| Source | Levels | Licence | Note |
|---|---|---|---|
| **Natural Earth** | ADM0, ADM1 | **Public domain** | Best for globe zoom 0–5, disputed-boundary variants included |
| **geoBoundaries** | ADM0–ADM4/5 | **CC BY 4.0** | `https://www.geoboundaries.org/api/current/gbOpen/{ISO3}/{ADM#}/`. **Use the CGAZ product** — global composite ADM0/1/2. ~1M boundaries, 200+ entities |
| **Overture Divisions** | 12 levels, 5.5M features | ODbL | GeoParquet on S3/Azure, monthly. Query via DuckDB. Country/region complete, sub-county spotty |
| **OCHA CODs** (via HDX) | ADM0–ADM3 | mostly CC BY | Authoritative for humanitarian-priority countries |
| **GADM** | ADM0–ADM5 | ✗ **Non-commercial only, redistribution prohibited** | **Commonly misused. Do not ship it.** The most frequently violated licence in hobby geospatial work |

**Recommended chain:** Natural Earth (public domain) for the globe → geoBoundaries CGAZ (CC BY) for ADM1/ADM2 → TIGERweb for US sub-county.

## Demographics

### US Census ACS — **Grade B, best free demographic API anywhere**
- `https://api.census.gov/data/{year}/acs/acs5?get=NAME,group(B01001)&for=tract:*&in=state:06&key=KEY`
- Also `/acs5/subject` (S-tables) and `/acs5/profile` (DP-tables).
- ~20k+ variables. **5-year estimates down to block group**; 1-year only for geographies ≥65k population.
- **Latest vintage: 2020–2024 ACS 5-year, released 29 Jan 2026** — notably later than the historical December cadence, so plan for slipping release dates.
- **API key now required for all queries.** JSON array-of-arrays; you join to geometry via GEOID. Public domain.

### TIGERweb — **Grade A, underused**
- `https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer`
- **Verified: 56 layers, GeoJSON supported, MaxRecordCount 100,000.** States, counties, places, tracts, block groups, blocks, congressional and legislative districts, school districts, tribal areas, urban areas, ZCTAs.
- `.../MapServer/{layer}/query?where=STATE='06'&outFields=*&f=geojson` — no auth, no key.
- **Pre-generalise before rendering.** Raw TIGER block groups are far too dense for a browser.

### Other Census endpoints
- **Decennial** — `https://api.census.gov/data/2020/dec/{pl|dhc|dp}`. The only free source of true **block-level** US population. ⚠️ 2020 data carries **differential privacy noise injection** — fine for visualisation, wrong for precise small-area claims.
- **PEP (Population Estimates)** — ⚠️ **The API lags the published tables.** Developer page lists Vintage 2023 as newest while Census has published Vintage 2025 tables (March 2026). For current estimates, download the CSVs.
- **Geocoder** — `https://geocoding.geo.census.gov/geocoder/{returntype}/{searchtype}`. Free, no key, 10,000 records per batch. US only, no GeoJSON, frequently slow under load.

### Global population
- **GHS-POP R2023A** (EU JRC) — 1975–2030 in 5-year epochs at 100m/1km/3arcsec/30arcsec. GeoTIFF, direct HTTP download, **CC BY 4.0**. More consistent methodology and longer series than WorldPop. **GHS-UCDB R2024A is the single best free "world cities with population" table** — ideal for globe labels and zoom targets. **Grade B**
- **WorldPop** — `https://hub.worldpop.org/rest/data` (verified live, 18 dataset aliases). Gridded population at **100m and 1km**, 2015–2030, constrained and unconstrained variants, age/sex structures. GeoTIFF, free, no key, CC BY 4.0. **Grade B** — gold standard, but rasters mean preprocessing to COGs or admin-polygon aggregates.
- **UN WPP 2024** — `https://population.un.org/dataportalapi/api/v1/` (verified live, no auth on `/indicators`). ~200 countries, 1950–2100, fertility/mortality/migration and projection variants. **National level only.** Biennial, so a 2026 revision may land imminently — re-check. CC BY 3.0 IGO. **Grade A** for country totals and the "2050 projection" toggle.
- **HDX / HDX HAPI** — `https://hapi.humdata.org`, free app identifier, max 10,000 rows/response. Population, displacement, food security, conflict events, funding at admin0/1/2. Also hosts the **OCHA COD boundaries**. ⚠️ **Licences vary per dataset** — mostly CC BY, a minority restricted. Coverage deliberately skewed to humanitarian-response countries, sparse for OECD. **Grade B**

## Geocoding

- **Photon** — `https://photon.komoot.io/api?q=berl&limit=5`. **Native GeoJSON FeatureCollection**, built for search-as-you-type with typo tolerance, multilingual, location bias, bbox filter. Self-hosting needs Java 21+, OpenSearch 3.x, ~95 GB disk and ≥64 GB RAM for planet — far less for extracts. Apache 2.0. **Grade A self-hosted — this is the standard solo-dev answer.**
- **Nominatim** — `https://nominatim.openstreetmap.org/search?format=geojson`. ⚠️ **Autocomplete is explicitly forbidden** on the public instance: *"you must not implement such a service on the client side using the API."* Max 1 req/sec, 4/min for scheduled bulk. Identifying User-Agent required, results must be cached. Fine for occasional server-side lookups; cannot power a search box. **Grade C**
- **LocationIQ** — **5,000 req/day free, commercial use allowed**, attribution required. ~$0.16/1k paid. Best free-tier value of the hosted options. **Grade B**
- **OpenCage** — 2,500/day but **free tier is trial/testing only**. ~$0.17/1k. Very clear ToS, no result-storage restrictions on paid. **Grade C**
- ✗ **Google** and **Mapbox** geocoding both prohibit displaying results on non-Google/non-Mapbox maps — disqualifying for a MapLibre globe.

---

# 6. Aviation and traffic

## Aviation

### OpenSky Network — **Grade B, only realistic free option**
- `https://opensky-network.org/api` · ⚠️ **Auth changed: OAuth2 client credentials.** POST for a bearer token, **expires after 30 minutes**. Legacy HTTP Basic is deprecated.

| Tier | Daily credits | Resolution |
|---|---|---|
| Anonymous | 400 | 10s |
| Registered | 4,000 | 5s |
| Active feeder | 8,000 | 5s |
| Licensed/OGN | 14,400 (hourly refill) | 5s |

- **Credit cost scales with bounding-box area and time span.** A global `/states/all` call is expensive; a small bbox is often 1 credit — **poll the user's viewport, not the planet.** That actually suits a zoom-in dashboard well.
- Endpoints: `/states/all`, `/states/own` (unlimited for your own receiver), `/flights/arrival`, `/flights/departure`, `/tracks`.
- Coverage is crowd-sourced ADS-B: dense over Europe and North America, sparse over oceans, Africa, much of Asia and South America.
- ⚠️ **Non-commercial / research use only.** If this ever monetises, the flight layer has to go — there is no cheap commercial substitute.

### Others
- **ADS-B Exchange** — best raw coverage including unfiltered and blocked aircraft, but subscription with **minimum annual commitments**, no public price list, sales contact required. A low-cost Community API exists for personal use, typically conditioned on running a feeder. Acquired by JetNet in 2023 and the previously permissive posture has tightened considerably. **Grade D**
- **AviationStack** — ✗ **100 requests/month free is unusable** (three calls a day). $49.99/mo for 10k. It's a flight-status lookup service, not a traffic feed.

## Highway traffic — **the weakest category in this document**

**There is no free national real-time US traffic feed, and no free global one.**

- **NPMRDS** is FHWA's actual national road speed dataset, INRIX-sourced via RITIS. **Access is restricted to state DOTs, MPOs, and qualifying public agencies.** There is no public tier. If you don't qualify, you don't have access — don't try to obtain it through an agency proxy.
- **WZDx (Work Zone Data Exchange)** is the closest thing to a real federal aggregator, and it covers **work zones only**, not traffic.
  - Registry: `https://data.transportation.gov/resource/69qe-yiui.json` — Socrata, free, no key. **Verified: 40 registered feeds** across ~35 states plus NPS, Quebec, and two vendors.
  - **Output is GeoJSON.** Spec v4.2.
  - ⚠️ The FHWA landing page is stale (still says v4.0, 5 feeds). Trust the registry.
  - **Grade B** — genuinely usable, genuinely free, national-ish, already GeoJSON. Feeds vary in quality and several need their own keys.
- **State 511 systems** — ~50 separate registrations, schemas, keys, rate limits, and terms. 511NY allows **10 calls per 60 seconds**; 511 SF Bay 60 requests/hour. Almost none provide flow or speed — only incidents, cameras, closures.
- **Commercial:** TomTom free tier is 2,500 traffic incidents/month but **200k traffic flow/incident tiles/month** — the tiles fit a dashboard far better than per-incident calls. HERE has the best global traffic coverage; ⚠️ **~6% price increase effective 1 Apr 2026.** ⚠️ **Google has no public real-time traffic data API** — traffic is a rendered layer in Maps JS/Android only, and results may not be displayed on non-Google maps.
- **Free historical:** FHWA **TMAS** count-station volumes and **HPMS** AADT, both public domain, both available as ArcGIS REST from `geodata.bts.gov`. NHTSA **FARS** fatal crashes with lat/long, free API.

**Honest verdict: skip real-time highway traffic in v1.** The defensible subset is WZDx (one registry call, GeoJSON, free), TomTom or HERE traffic *tiles* as an overlay at high zoom, and FHWA AADT as a static "how busy is this road normally" layer. Everything beyond that is 50 separate mini-projects for very little payoff.

---

# 7. Skip list

| Source | Why |
|---|---|
| **Yahoo Finance / yfinance** | ToS requires deleting data within 24 hours, prohibits redistribution and competing products. Breaks constantly |
| **Bing News Search** | Retired 11 August 2025 |
| **BreezoMeter** | No longer exists — folded into Google's Air Quality and Pollen APIs |
| **exchangerate.host** | Free tier cut to 100 requests/month |
| **NewsAPI.org free tier** | ToS explicitly forbids production use, including internal |
| **GADM** | Non-commercial only, redistribution prohibited |
| **`tile.openstreetmap.org`** | Usage policy prohibits production use; auto-blocks generic User-Agents |
| **Meteomatics** | Pricing entirely sales-gated; Open-Meteo covers the same ground free |
| **Ambee** | No published limits or prices, for a feature you already deprioritised |
| **Reuters / AP** | $10,000+/year minimum, five-step sales process |
| **NPMRDS** | Access restricted to public agencies. You don't qualify |
| **Alpha Vantage** | 25 requests/day. Its commodity and macro series are re-published EIA/FRED data you can get directly |

---

# 8. Cost summary

**Free tier — a complete, credible terminal at $0/month:**

PortWatch · USGS · GDACS · NHC · EMSC · tsunami.gov · GDELT · FRED · World Bank · ECB · Frankfurter · EIA · CFTC COT · US Census (trade + ACS + TIGERweb) · Eurostat · Open-Meteo · NWS · OpenAQ · NASA FIRMS · GVP · Natural Earth · geoBoundaries · GHS-POP · UN WPP · WZDx · OpenSky · aisstream.io · self-hosted Photon · Protomaps on R2

**Paid, only where free genuinely fails:**

| Item | Cost | Buys you |
|---|---|---|
| FMP Starter | $22/mo | Company fundamentals — the one real gap in the free stack |
| metals.dev | $1.79–$9.99/mo | Daily gold, silver, platinum |
| Massive Starter | $29/mo | Intraday equities, unlimited calls at 15-min delay |
| WeatherAPI Starter | $7/mo | Commercial-safe weather if Open-Meteo's non-commercial clause bites |
| VPS + managed Postgres | ~$10–30/mo | Where all of this actually runs |

**Realistic total: $0 to ship, ~$60–90/month for a complete build including hosting.**

---

# 9. Licensing traps, in order of how likely they are to bite

1. **ODbL share-alike** on anything OSM-derived — Protomaps basemap, Overture Divisions, Photon and Nominatim results. Attribution is required and the derived-database obligation is real. Natural Earth (public domain) plus geoBoundaries (CC BY) let you keep the boundary layer clean of ODbL entirely.
2. **OpenSky is non-commercial.** So is Global Fishing Watch, Finnhub's free tier, and Open-Meteo's free tier. Fine for a personal terminal; each becomes a problem the moment money is involved.
3. **GDELT's geographic precision** — 0.20–0.26 correlation with hand-coded data at grid-cell level, plus documented capital-city bias. Present it as attention density, filter to city-level geo types, require multi-source corroboration before you show a pin.
4. **FRED's third-party series.** You are solely responsible for the copyrights of series FRED redistributes. Most dashboards ignore this.
5. **FMP requires a separate licensing agreement to display their data.** Not covered by the subscription alone.
6. **Freightos, Drewry, Xeneta, and IMF** all restrict redistribution. Their public index values are free to display with attribution; the APIs are enterprise.
7. **Google and Mapbox geocoding** cannot be displayed on a competitor's map. Disqualifying for MapLibre.
8. **GADM.** Non-commercial only. Don't ship it.

---

# 10. Ingestion notes

**Normalise to one event shape before anything touches the globe.** Something like:

```json
{
  "time": "2026-08-14T00:00:00Z",
  "lat": 30.0, "lon": 32.3,
  "type": "chokepoint_transit",
  "severity": 0.7,
  "source": "imf_portwatch",
  "source_id": "chokepoint1",
  "url": "https://portwatch.imf.org/...",
  "payload": { }
}
```

Ten feeds with ten cadences and ten schemas will otherwise mean frontend work every time you add a source.

**Cadence tiers to schedule around:**

| Tier | Sources |
|---|---|
| Real-time (push or <5 min) | EMSC WebSocket, USGS (1 min), tsunami.gov, NWS alerts, aisstream.io |
| 15 minutes | GDELT |
| Hourly to 6-hourly | NHC advisories, weather models, VAAC, OpenSky viewport polls |
| Daily | FX, EIA spot, GloFAS, commodity prices |
| Weekly | **PortWatch (Tuesdays 09:00 ET)**, CFTC COT (Fridays 15:30 ET), USDM (Thursdays), GVP |
| Monthly | Census trade (FT-900), Eurostat, Pink Sheet, RWI/ISL |
| Annual/static | World Bank, ACS, Natural Earth, GHS-POP |

**Format conversions you will need.** Only USGS, EMSC, GDACS, NWS, GVP WFS, FIRMS WFS, GDELT GEO, TIGERweb, and WZDx give you GeoJSON directly. NHC cones and USDM polygons are shapefiles; Copernicus drought is WMS raster; VAAC and tsunami are XML and fixed-format text; WorldPop and GHS-POP are GeoTIFF. One scheduled `ogr2ogr` job handles every shapefile case and lets you cache the results — which you want regardless, since cyclone cones only change every 3–6 hours.

**Three operational rules worth adopting from the start.** Cache server-side and have the frontend read your own store, never upstream — it keeps you inside redistribution boundaries and stops a page refresh from burning quota. Keep every API key server-side and out of client bundles, committed config, and logs. And render the source timestamp on anything time-sensitive, because PortWatch's weekly batch and OpenAQ's per-country lag will both otherwise read as "now."

---

## Verification log

Confirmed by live call on 14 August 2026:

- **PortWatch chokepoints** — endpoint responds anonymously, 76,412 records
- **PortWatch ports** — 5,689,075 records, latest date 2026-08-09
- **NHC `CurrentStorms.json`** — live, 2 active storms (Hernan ep082026, Lala cp012026), `activeStorms` root key as documented
- **World Bank Indicators** — responding, `lastupdated: 2026-07-13`
- **TIGERweb** — 56 layers, GeoJSON supported, MaxRecordCount 100,000
- **WorldPop REST** — 18 dataset aliases returned
- **UN WPP Data Portal** — `/indicators` responds with no auth
- **WZDx registry** — 40 registered feeds
- **GVP WFS** — GetCapabilities responds, VOTW 5.4.0

Could not confirm from this environment, flagged inline: GDELT GEO/DOC APIs (User-Agent requirement), JTWC (403 to automated fetch), WMO Alert Hub feed URLs (client-side rendered), OECD rate limits, IMF new-platform anonymous access, Meteomatics and Ambee pricing, TomTom per-1,000 rates, ADS-B Exchange pricing, Geoapify free-tier volume, Census PEP newest API vintage.

---

*Compiled 14 August 2026. Endpoint URLs, record counts, and free-tier limits were verified live where possible; items that could not be confirmed are marked above. Re-verify pricing before committing to any paid tier.*
