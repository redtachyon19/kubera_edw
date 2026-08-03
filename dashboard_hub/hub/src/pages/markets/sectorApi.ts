/** Sector and correlation endpoints on the hub's market API. */

import type { Period } from '../stock/api';

export interface SectorCard {
  slug: string;
  name: string;
  blurb: string;
  count: number;
  priced: number;
  averageReturn: number | null;
  best: { symbol: string; return: number } | null;
  worst: { symbol: string; return: number } | null;
}

export interface Constituent {
  symbol: string;
  currency: string;
  last: number;
  periodReturn: number;
  annualisedVol: number | null;
  maxDrawdown: number | null;
  /** Sensitivity to the equal-weighted sector basket. */
  beta: number | null;
  /** Share of the name's variance the basket explains. */
  r2: number | null;
}

export interface Rolling {
  min: number;
  median: number;
  max: number;
  window: number;
  series: number[];
}

export interface Pair {
  a: string;
  b: string;
  correlation: number;
  /** Correlation on days the basket fell — where diversification is tested. */
  downside: number | null;
  rolling: Rolling | null;
}

export const METHODS = ['pearson', 'spearman', 'downside', 'ewma'] as const;
export type Method = (typeof METHODS)[number];

export const METHOD_LABEL: Record<Method, string> = {
  pearson: 'Pearson',
  spearman: 'Spearman',
  downside: 'Downside',
  ewma: 'EWMA',
};

export const METHOD_HINT: Record<Method, string> = {
  pearson: 'Linear co-movement of daily returns across the whole window.',
  spearman: 'The same on ranks, so a few outsized days cannot dominate it.',
  downside: 'Only days the sector fell — diversification is tested on the way down.',
  ewma: 'Exponentially weighted (λ 0.94): recent weeks count for more than a year ago.',
};

export interface SectorDetail {
  slug: string;
  name: string;
  blurb: string;
  symbols: string[];
  constituents: Constituent[];
  labels: string[];
  matrices: Record<Method, (number | null)[][]>;
  pairs: Pair[];
  missing: string[];
  interval: string;
  start: string | null;
  observations: number;
  downDays: number;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(body.error ?? `API returned ${response.status}`);
  return body as T;
}

export function fetchSectors(period: Period, signal?: AbortSignal): Promise<SectorCard[]> {
  return get<{ sectors: SectorCard[] }>(`/api/market/sectors?period=${period}`, signal).then(
    (body) => body.sectors,
  );
}

export function fetchSector(
  slug: string,
  period: Period,
  signal?: AbortSignal,
): Promise<SectorDetail> {
  return get<SectorDetail>(`/api/market/sector?slug=${slug}&period=${period}`, signal);
}

