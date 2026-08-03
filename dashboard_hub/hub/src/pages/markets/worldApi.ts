/** World desk endpoints on the hub's market API (`dashboard_hub/market_api.py`). */

/** One country: what its government reports, what its currency did, what its market did. */
export interface WorldCountry {
  iso3: string;
  name: string;
  region: string;
  incomeLevel: string | null;
  capital: string | null;
  lat: number;
  lon: number;
  /** True when Kubera holds a company domiciled here. */
  hasIssuer: boolean;

  currency: string | null;
  /** Units of the local currency per USD. */
  fxPerUsd: number | null;
  /** Move against the dollar over the window — positive is a stronger currency. */
  fxChange: number | null;

  index: string | null;
  indexSymbol: string | null;
  /** Local-currency return on the local benchmark over the window. */
  marketChange: number | null;

  /** Annual figures, as percentages. Each carries the year it was published for. */
  inflation?: number | null;
  inflationYear?: number;
  gdpGrowth?: number | null;
  gdpGrowthYear?: number;
  unemployment?: number | null;
  unemploymentYear?: number;
  year?: number;
}

export interface WorldSnapshot {
  period: string;
  countries: WorldCountry[];
  macroYear: number | null;
  /** Which feed answered — the marts, or the World Bank read live. */
  macroSource: string;
}

export interface SectorLeg {
  slug: string;
  name: string;
  symbol: string;
  change: number;
  last?: number;
  asOf?: string;
}

export interface WorldSectors {
  period: string;
  sectors: SectorLeg[];
  regions: SectorLeg[];
}

/** The metrics the globe and the table can be coloured by. */
export const METRICS = ['market', 'inflation', 'gdpGrowth', 'unemployment', 'fx'] as const;
export type Metric = (typeof METRICS)[number];

interface MetricSpec {
  label: string;
  /** Where the colour ramp sits neutral, and how far from it saturates. */
  midpoint: number;
  spread: number;
  /** False for inflation and unemployment, where more is worse. */
  higherIsBetter: boolean;
  /** True for the two that arrive as fractions rather than percentages. */
  fractional: boolean;
  caption: (snapshot: WorldSnapshot) => string;
  value: (country: WorldCountry) => number | null;
}

export const METRIC: Record<Metric, MetricSpec> = {
  market: {
    label: 'Equity market',
    midpoint: 0,
    spread: 0.25,
    higherIsBetter: true,
    fractional: true,
    caption: (s) => `Local benchmark, ${s.period} return in local currency`,
    value: (c) => c.marketChange ?? null,
  },
  inflation: {
    label: 'Inflation',
    // Two percent is the target most of these central banks actually publish, so
    // it is the honest place for the ramp to sit neutral rather than zero.
    midpoint: 2,
    spread: 6,
    higherIsBetter: false,
    fractional: false,
    caption: (s) => `Consumer price inflation, World Bank, to ${s.macroYear ?? '—'}`,
    value: (c) => c.inflation ?? null,
  },
  gdpGrowth: {
    label: 'GDP growth',
    midpoint: 2,
    spread: 4,
    higherIsBetter: true,
    fractional: false,
    caption: (s) => `Real GDP growth, World Bank, to ${s.macroYear ?? '—'}`,
    value: (c) => c.gdpGrowth ?? null,
  },
  unemployment: {
    label: 'Unemployment',
    midpoint: 5,
    spread: 5,
    higherIsBetter: false,
    fractional: false,
    caption: (s) => `Unemployment rate, World Bank, to ${s.macroYear ?? '—'}`,
    value: (c) => c.unemployment ?? null,
  },
  fx: {
    label: 'Currency vs USD',
    midpoint: 0,
    spread: 0.15,
    higherIsBetter: true,
    fractional: true,
    caption: (s) => `Move against the US dollar over ${s.period}`,
    value: (c) => c.fxChange ?? null,
  },
};

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(body.error ?? `API returned ${response.status}`);
  return body as T;
}

export function fetchWorld(period: string, signal?: AbortSignal): Promise<WorldSnapshot> {
  return get<WorldSnapshot>(`/api/market/world?period=${encodeURIComponent(period)}`, signal);
}

export function fetchWorldSectors(period: string, signal?: AbortSignal): Promise<WorldSectors> {
  return get<WorldSectors>(`/api/market/world-sectors?period=${encodeURIComponent(period)}`, signal);
}

/** A percentage that arrived as a percentage — inflation, growth, unemployment. */
export function rate(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  return `${value.toFixed(digits)}%`;
}

/** A percentage that arrived as a fraction — a market or currency move. */
export function move(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  const lead = value >= 0 ? '+' : '−';
  return `${lead}${Math.abs(value * 100).toFixed(digits)}%`;
}

/** Enough decimals to be useful across rates that run from 0.74 to 1,494. */
export function fxLevel(value: number | null | undefined): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  if (value >= 100) return value.toFixed(0);
  if (value >= 1) return value.toFixed(2);
  return value.toFixed(4);
}

export function tone(value: number | null | undefined, higherIsBetter = true): string {
  if (value === null || value === undefined || !isFinite(value) || value === 0) return '';
  return value > 0 === higherIsBetter ? 'up' : 'down';
}

// ── Country detail ───────────────────────────────────────────────────────────

/** One observation on a drawn series. */
export interface SeriesPoint {
  date: string;
  [key: string]: string | number | null | undefined;
}

export interface SeriesLine {
  key: string;
  label: string;
}

/** A currency measured against gold, against the dollar, and the dollar against gold. */
export interface PurchasingPower {
  iso3: string;
  currency: string | null;
  period?: string;
  points: SeriesPoint[];
  lines: SeriesLine[];
  /** Change over the window, as fractions. */
  goldChange?: number | null;
  usdChange?: number | null;
  dollarGoldChange?: number | null;
}

/** One counterparty. `exports` is what the reporting country sells to it. */
export interface TradePartner {
  iso3: string;
  name: string;
  exports: number | null;
  imports: number | null;
  balance: number | null;
  total: number;
}

export interface TradeFlows {
  iso3: string;
  year: number | null;
  partners: TradePartner[];
  totalExports: number | null;
  totalImports: number | null;
}

export interface CompositionShare {
  key: string;
  label: string;
  /** Percent of merchandise trade. */
  share: number;
}

export interface Composition {
  iso3: string;
  exports: CompositionShare[];
  imports: CompositionShare[];
  years: { exports?: number | null; imports?: number | null };
}

export interface Story {
  title: string;
  url: string;
  source: string;
  published: string;
}

export interface CountryDetail {
  iso3: string;
  profile: WorldCountry | null;
  purchasingPower: PurchasingPower;
  trade: TradeFlows;
  composition: Composition;
  news: Story[];
}

export interface EnergyPrice {
  slug: string;
  name: string;
  symbol: string;
  unit: string;
  group: string;
  last: number;
  change: number;
}

export interface EnergyPanel {
  period: string;
  prices: EnergyPrice[];
  points: SeriesPoint[];
  lines: SeriesLine[];
}

export function fetchCountry(
  iso3: string,
  period: string,
  signal?: AbortSignal,
): Promise<CountryDetail> {
  return get<CountryDetail>(
    `/api/market/world-country?iso3=${encodeURIComponent(iso3)}&period=${encodeURIComponent(period)}`,
    signal,
  );
}

export function fetchEnergy(period: string, signal?: AbortSignal): Promise<EnergyPanel> {
  return get<EnergyPanel>(`/api/market/world-energy?period=${encodeURIComponent(period)}`, signal);
}

/** Trade values run from millions to trillions; one suffix, three significant figures. */
export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined || !isFinite(value)) return '—';
  const sign = value < 0 ? '−' : '';
  const size = Math.abs(value);
  const suffix = size >= 1e12 ? 'T' : size >= 1e9 ? 'bn' : size >= 1e6 ? 'M' : '';
  const divisor = { T: 1e12, bn: 1e9, M: 1e6, '': 1 }[suffix];
  const scaled = size / divisor;
  return `${sign}$${scaled.toFixed(scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2)}${suffix}`;
}

/** An index rebased to 100 — no decimals once it is past three digits. */
export function index(value: number): string {
  if (!isFinite(value)) return '—';
  return value >= 100 ? value.toFixed(0) : value.toFixed(1);
}

export function price(value: number): string {
  if (!isFinite(value)) return '—';
  return value >= 1000 ? value.toFixed(0) : value >= 10 ? value.toFixed(1) : value.toFixed(2);
}
