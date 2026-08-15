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
  topIndustry: string | null;
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
 * Three industries get a colour. Everything else is neutral.
 *
 * PortWatch splits trade thirteen ways, and thirteen categorical hues is not a
 * palette — it is a rainbow that nobody can read and that fails colour-vision
 * separation long before the thirteenth hue. Ribbons also cross each other
 * freely on a sphere, so *any* two can end up adjacent, which is the strictest
 * case a palette can be asked to survive.
 *
 * Validated against that strict all-pairs case in both themes, the ceiling is
 * three hues. That turns out to cost almost nothing: across the ribbons large
 * enough to draw, Machinery and Mineral Products alone are the dominant cargo of
 * ~61%, and a further ~28% have no dominant cargo at all. The long tail that
 * loses its own colour is about 4% of what is on screen.
 *
 * The assignment is fixed here in code rather than derived from the data, so a
 * category never changes colour because the underlying numbers moved. Identity
 * never rests on colour alone: the legend is always present, the hover readout
 * names the cargo, and the ribbon panel breaks out all thirteen with labels.
 */
export const INDUSTRY_COLOUR: Record<string, string> = {
  'Machinery & Electrical Equipment': 'var(--goods-machinery)',
  'Mineral Products': 'var(--goods-mineral)',
  'Vehicles & Equipment': 'var(--goods-vehicles)',
};

/** The legend, in the order the colours were assigned. */
export const INDUSTRY_LEGEND = [
  { name: 'Machinery & Electrical Equipment', colour: 'var(--goods-machinery)' },
  { name: 'Mineral Products', colour: 'var(--goods-mineral)' },
  { name: 'Vehicles & Equipment', colour: 'var(--goods-vehicles)' },
  { name: 'Other cargo', colour: 'var(--goods-other)' },
];

export function industryColour(name: string | null): string | null {
  if (!name) return null;
  return INDUSTRY_COLOUR[name] ?? 'var(--goods-other)';
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
