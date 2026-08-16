/**
 * The trade desk's endpoints on the hub's market API.
 *
 * Everything here is warehouse-backed — IMF PortWatch, built by dbt into
 * `marts.*` and served from `dashboard_hub/lib/maritime.py`. That matters for
 * how it is captioned: PortWatch republishes weekly and lags several days, so
 * nothing on this desk is live, and the UI says so rather than implying a feed.
 */

/**
 * Which way the cargo moves relative to the PORT — outbound leaves the quay,
 * inbound arrives at it.
 *
 * Not `import`/`export`, which always begs "whose?". PortWatch's own fields are
 * named from the partner country's side, so its `import` is a port's *outbound*
 * cargo; the translation happens in dbt, and this vocabulary is what survives it.
 */
export type FlowDirection = 'inbound' | 'outbound';

export interface TradePort {
  portId: string;
  name: string;
  iso3: string;
  country: string;
  lat: number;
  lon: number;
  /** Metric tons over the trailing 90 days of published data. */
  tons: number | null;
  priorTons: number | null;
  /** Fraction against the preceding 90 days. */
  change: number | null;
  portCalls: number | null;
  importTons: number | null;
  exportTons: number | null;
  containerTons: number | null;
  dryBulkTons: number | null;
  tankerTons: number | null;
  /** Summed from the trade links — what the cargo is worth, not what it weighs. */
  valueDaily: number | null;
  valueAnnual: number | null;
  valueRank: number;
  topIndustry: string | null;
  /** Rank by tonnage. `valueRank` orders the same ports by worth instead. */
  rank: number;
  asOf: string | null;
}

export interface TradeRibbon {
  id: string;
  portId: string;
  portName: string;
  portIso3: string;
  portCountry: string;
  fromLat: number;
  fromLon: number;
  partnerIso3: string;
  partnerName: string;
  toLat: number;
  toLon: number;
  direction: FlowDirection;
  valueDaily: number | null;
  valueAnnual: number | null;
  /** Null when no single industry is at least a third of the flow. */
  industry: string | null;
  industryShare: number | null;
  industryCount: number;
  rank: number;
}

export interface TradeChokepoint {
  chokepointId: string;
  name: string;
  iso3: string;
  lat: number;
  lon: number;
  transits: number | null;
  priorTransits: number | null;
  yearAgoTransits: number | null;
  capacity: number | null;
  priorCapacity: number | null;
  yearAgoCapacity: number | null;
  transitsChange: number | null;
  capacityChange: number | null;
  capacityChangeYoY: number | null;
  containerTransits: number | null;
  tankerTransits: number | null;
  dryBulkTransits: number | null;
  asOf: string | null;
}

export interface TradeIndustry {
  name: string;
  hsSection: string | null;
  order: number;
}

export interface TradeOverview {
  ports: TradePort[];
  ribbons: TradeRibbon[];
  chokepoints: TradeChokepoint[];
  industries: TradeIndustry[];
  coverage: { from: string | null; to: string | null; observations: number | null };
  source: string;
}

export interface PortWeek {
  week: string;
  tons: number | null;
  importTons: number | null;
  exportTons: number | null;
  portCalls: number | null;
  containerTons: number | null;
  dryBulkTons: number | null;
  tankerTons: number | null;
  generalCargoTons: number | null;
  roroTons: number | null;
  /** 13-week trailing mean. */
  trend: number | null;
  yearAgo: number | null;
  shareOfCountry: number | null;
  /** True for the newest bucket, which PortWatch has not finished publishing. */
  partial: boolean;
}

export interface PortLink {
  partnerIso3: string;
  partnerName: string;
  direction: FlowDirection;
  valueDaily: number | null;
  valueAnnual: number | null;
  industry: string | null;
  industryShare: number | null;
}

export interface PortDisruption {
  eventId: number;
  type: string;
  name: string | null;
  alertLevel: string | null;
  severity: string | null;
  from: string | null;
  to: string | null;
  days: number | null;
  portsHit: number | null;
}

export interface PortDetail {
  portId: string;
  found: boolean;
  name: string;
  fullName: string | null;
  locode: string | null;
  iso3: string;
  country: string;
  continent: string | null;
  lat: number;
  lon: number;
  isCatalogued: boolean;
  industries: string[];
  shareOfCountryImports: number | null;
  shareOfCountryExports: number | null;
  tons: number | null;
  priorTons: number | null;
  change: number | null;
  portCalls: number | null;
  importTons: number | null;
  exportTons: number | null;
  valueDaily: number | null;
  valueAnnual: number | null;
  valueRank: number;
  rank: number;
  rankInCountry: number;
  asOf: string | null;
  history: PortWeek[];
  links: PortLink[];
  disruptions: PortDisruption[];
}

export interface RibbonIndustry {
  name: string;
  hsSection: string | null;
  order: number;
  valueDaily: number | null;
  valueAnnual: number | null;
  share: number | null;
  rank: number;
}

export interface RibbonDetail {
  found: boolean;
  id: string;
  portId: string;
  portName: string;
  portIso3: string;
  portCountry: string;
  partnerIso3: string;
  partnerName: string;
  direction: FlowDirection;
  valueDaily: number | null;
  valueAnnual: number | null;
  /** PortWatch's own total, and the sum of its named industries. They differ. */
  publishedTotal: number | null;
  industrySum: number | null;
  topIndustry: string | null;
  topIndustryShare: number | null;
  industryCount: number;
  rank: number;
  rankInPort: number;
  rankInCountry: number;
  industries: RibbonIndustry[];
}

export interface ChokepointDay {
  date: string;
  transits: number | null;
  capacity: number | null;
  container: number | null;
  tanker: number | null;
  dryBulk: number | null;
  transitsTrend: number | null;
  capacityTrend: number | null;
  capacityYearAgo: number | null;
}

export interface ChokepointDetail {
  chokepointId: string;
  found: boolean;
  name: string;
  fullName: string | null;
  iso3: string;
  country: string;
  lat: number;
  lon: number;
  industries: string[];
  transits: number | null;
  capacity: number | null;
  transitsChange: number | null;
  capacityChange: number | null;
  capacityChangeYoY: number | null;
  containerTransits: number | null;
  tankerTransits: number | null;
  dryBulkTransits: number | null;
  asOf: string | null;
  history: ChokepointDay[];
}

export interface CountryTradeDetail {
  iso3: string;
  found: boolean;
  ports: {
    portId: string;
    name: string;
    lat: number;
    lon: number;
    tons: number | null;
    change: number | null;
    importTons: number | null;
    exportTons: number | null;
    topIndustry: string | null;
    rank: number;
    rankInCountry: number;
    shareOfImports: number | null;
    shareOfExports: number | null;
  }[];
  history: { week: string; tons: number | null; importTons: number | null; exportTons: number | null; portCalls: number | null }[];
  partners: {
    iso3: string;
    name: string;
    direction: FlowDirection;
    valueDaily: number | null;
    valueAnnual: number | null;
    portCount: number;
  }[];
  industryMix: { name: string; direction: FlowDirection; valueDaily: number | null }[];
}

/**
 * US customs detail for one port — the only layer where energy stands alone.
 *
 * Census reports HS *chapters*, so chapter 27 (crude, refined fuels, gas, coal)
 * is its own category here. PortWatch can only reach HS section, where those sit
 * welded to iron ore and cement and cannot be pulled apart.
 */
export interface UsPortCommodities {
  portName: string;
  found: boolean;
  /**
   * Which Census ports were counted. The two sources share no port identifier —
   * PortWatch has one "Los Angeles-Long Beach", Census has separate numbered
   * codes for each city — so the match is by name and is named on screen rather
   * than trusted silently.
   */
  matchedPorts?: string[];
  /** One row per month, with a column per category (and `__kg` twins). */
  months: Record<string, string | number | null>[];
  categories: { name: string; order: number }[];
  topChapters: {
    chapter: string;
    name: string | null;
    category: string | null;
    valueUsd: number | null;
  }[];
}

export function fetchUsPort(portName: string, signal?: AbortSignal): Promise<UsPortCommodities> {
  return get<UsPortCommodities>(
    `/api/market/trade-us-port?portName=${encodeURIComponent(portName)}`,
    signal,
  );
}

/**
 * Colours for the finer US categories. Identical to the global set except that
 * the graphite of "Mineral Products" now belongs to Energy alone, and the ores
 * it used to be lumped with take the neutral.
 */
export const FINE_COLOUR: Record<string, string> = {
  'Animal & Animal Products': 'var(--goods-animal)',
  'Vegetable Products': 'var(--goods-vegetable)',
  'Prepared Foodstuffs & Beverages': 'var(--goods-foodstuffs)',
  'Energy — oil, gas & coal': 'var(--goods-mineral)',
  'Ores, Stone & Minerals': 'var(--goods-other)',
  'Chemical & Allied Industries': 'var(--goods-chemical)',
  'Plastics, Rubber, Leather': 'var(--goods-plastics)',
  'Wood & Wood Products': 'var(--goods-wood)',
  'Textiles & Footwear': 'var(--goods-textiles)',
  'Stone & Glass': 'var(--goods-stone)',
  Metals: 'var(--goods-metals)',
  'Machinery & Electrical Equipment': 'var(--goods-machinery)',
  'Vehicles & Equipment': 'var(--goods-vehicles)',
  Miscellaneous: 'var(--goods-other)',
};

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(body.error ?? `API returned ${response.status}`);
  return body as T;
}

export function fetchTradeOverview(signal?: AbortSignal): Promise<TradeOverview> {
  return get<TradeOverview>('/api/market/trade-overview', signal);
}

export function fetchPort(portId: string, signal?: AbortSignal): Promise<PortDetail> {
  return get<PortDetail>(`/api/market/trade-port?portId=${encodeURIComponent(portId)}`, signal);
}

export function fetchRibbon(
  portId: string,
  partner: string,
  direction: string,
  signal?: AbortSignal,
): Promise<RibbonDetail> {
  return get<RibbonDetail>(
    `/api/market/trade-ribbon?portId=${encodeURIComponent(portId)}` +
      `&partner=${encodeURIComponent(partner)}&direction=${encodeURIComponent(direction)}`,
    signal,
  );
}

export function fetchChokepoint(id: string, signal?: AbortSignal): Promise<ChokepointDetail> {
  return get<ChokepointDetail>(`/api/market/trade-chokepoint?id=${encodeURIComponent(id)}`, signal);
}

export function fetchCountryTrade(iso3: string, signal?: AbortSignal): Promise<CountryTradeDetail> {
  return get<CountryTradeDetail>(`/api/market/trade-country?iso3=${encodeURIComponent(iso3)}`, signal);
}

// ── Goods colours ────────────────────────────────────────────────────────────

/**
 * Every industry gets a colour, and the colour means something: green for what
 * grows, gold for metals, brown for timber, crimson for livestock, slate for
 * what is dug out of the ground.
 *
 * The assignment is fixed here in code rather than derived from the data, so a
 * category never changes colour because the numbers moved — a legend that
 * repaints between two page loads is worse than no legend.
 *
 * **Thirteen categories is past what colour alone can carry.** Each of these
 * clears the lightness band, the chroma floor and contrast against the globe's
 * face, but some pairs are unavoidably close at this count — gold beside timber,
 * crimson beside green for a deuteranope — precisely because the things they
 * name are neighbours. So the colour is never the only signal: the legend is
 * always on screen, the hover readout names the cargo, and every bar in every
 * panel is labelled. Colour is the shortcut; the word is the answer.
 */
export interface IndustrySpec {
  colour: string;
  /** The HS chapters the category actually spans. */
  chapters: string;
  /** What is in it, in words a reader recognises. */
  contains: string;
  /**
   * Display name, where the official one actively misleads. Only Mineral
   * Products needs it: the label says rocks and the contents are mostly the
   * world's oil and gas.
   */
  label?: string;
}

/**
 * The thirteen cargo categories, each with the HS chapters behind it and a
 * plain-English gloss.
 *
 * The names come from the Harmonised System and several of them tell you almost
 * nothing on their own — "Machinery & Electrical Equipment" is phones and
 * computers as much as it is turbines, and "Mineral Products" is where all the
 * world's crude oil, refined fuel, coal and gas live. Anywhere a category is
 * named on screen the gloss goes with it, because the official label is not the
 * useful one.
 */
export const INDUSTRY: Record<string, IndustrySpec> = {
  'Animal & Animal Products': {
    colour: 'var(--goods-animal)',
    chapters: 'HS 01–05',
    contains: 'live animals, meat, fish, dairy, eggs',
  },
  'Vegetable Products': {
    colour: 'var(--goods-vegetable)',
    chapters: 'HS 06–14',
    contains: 'cereals, fruit, vegetables, coffee, seeds',
  },
  'Prepared Foodstuffs & Beverages': {
    colour: 'var(--goods-foodstuffs)',
    chapters: 'HS 15–24',
    contains: 'processed food, drinks, spirits, tobacco, edible oils',
  },
  'Mineral Products': {
    colour: 'var(--goods-mineral)',
    chapters: 'HS 25–27',
    contains: 'crude oil, refined fuels, gas, coal · plus iron and other ores, stone, cement, salt',
    // Renamed for display because "Mineral Products" reads as quarrying and is
    // in fact where every barrel of seaborne crude sits. The grouping is the
    // HS's, not ours — section 5 bundles fuels (ch 27) with ores (26) and stone
    // (25), and PortWatch publishes the value pre-aggregated at section level,
    // so it cannot be split back apart. The honest fix is a label that leads
    // with what dominates it, and pointing the reader at the tanker series,
    // which does separate energy and does have history.
    label: 'Fuels, Ores & Stone',
  },
  'Chemical & Allied Industries': {
    colour: 'var(--goods-chemical)',
    chapters: 'HS 28–38',
    contains: 'industrial chemicals, medicines, fertiliser, paint, soap, cosmetics',
  },
  'Plastics, Rubber, Leather': {
    colour: 'var(--goods-plastics)',
    chapters: 'HS 39–43',
    contains: 'plastics and articles of, rubber, tyres, leather, hides, handbags',
  },
  'Wood & Wood Products': {
    colour: 'var(--goods-wood)',
    chapters: 'HS 44–49',
    contains: 'timber, cork, wood pulp, paper, card, printed books',
  },
  'Textiles & Footwear': {
    colour: 'var(--goods-textiles)',
    chapters: 'HS 50–67',
    contains: 'cotton, wool, yarn, fabric, clothing, shoes, hats',
  },
  'Stone & Glass': {
    colour: 'var(--goods-stone)',
    chapters: 'HS 68–71',
    contains: 'stone, ceramics, glass, pearls, precious stones, gold and silver bullion',
  },
  Metals: {
    colour: 'var(--goods-metals)',
    chapters: 'HS 72–83',
    contains: 'iron, steel, copper, aluminium, nickel, tools, fasteners',
  },
  'Machinery & Electrical Equipment': {
    colour: 'var(--goods-machinery)',
    chapters: 'HS 84–85, 90–92',
    contains: 'engines, industrial machinery, computers, phones, chips, appliances, instruments',
  },
  'Vehicles & Equipment': {
    colour: 'var(--goods-vehicles)',
    chapters: 'HS 86–89',
    contains: 'cars, trucks, parts, railway stock, ships, aircraft',
  },
  Miscellaneous: {
    colour: 'var(--goods-other)',
    chapters: 'HS 93–97',
    contains: 'arms, furniture, bedding, lamps, toys, games, art, antiques',
  },
};

export const INDUSTRY_COLOUR: Record<string, string> = Object.fromEntries(
  Object.entries(INDUSTRY).map(([name, spec]) => [name, spec.colour]),
);

/** The legend, in the warehouse's fixed industry order. */
export const INDUSTRY_LEGEND = Object.entries(INDUSTRY).map(([name, spec]) => ({
  name,
  ...spec,
  label: spec.label ?? name,
}));

/** What to print for a category — the display name where one is set. */
export function industryLabel(name: string | null): string {
  if (!name) return '—';
  return INDUSTRY[name]?.label ?? name;
}

export function industryColour(name: string | null): string | null {
  if (!name) return null;
  return INDUSTRY[name]?.colour ?? 'var(--goods-other)';
}

/** "HS 25–27 · crude oil, refined fuels, …" — for tooltips and captions. */
export function industryGloss(name: string | null): string | null {
  const spec = name ? INDUSTRY[name] : undefined;
  return spec ? `${spec.chapters} · ${spec.contains}` : null;
}

// ── Formatting ───────────────────────────────────────────────────────────────

/** Metric tons run from thousands to hundreds of millions. */
export function tons(value: number | null | undefined): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  const size = Math.abs(value);
  if (size >= 1e9) return `${(value / 1e9).toFixed(1)}bn t`;
  if (size >= 1e6) return `${(value / 1e6).toFixed(size / 1e6 >= 100 ? 0 : 1)}M t`;
  if (size >= 1e3) return `${(value / 1e3).toFixed(0)}k t`;
  return `${value.toFixed(0)} t`;
}

/** Deadweight tonnage through a chokepoint — same shape, different unit. */
export function dwt(value: number | null | undefined): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  const size = Math.abs(value);
  if (size >= 1e9) return `${(value / 1e9).toFixed(1)}bn DWT`;
  if (size >= 1e6) return `${(value / 1e6).toFixed(size / 1e6 >= 100 ? 0 : 1)}M DWT`;
  return `${(value / 1e3).toFixed(0)}k DWT`;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

/** A date the desk can print without implying more precision than it has. */
export function asOfLabel(value: string | null | undefined): string {
  if (!value) return 'no date';
  const parsed = new Date(`${value}T00:00:00Z`);
  if (isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}
