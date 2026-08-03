/** Client for the hub's market API (`dashboard_hub/market_api.py`). */

export interface SearchResult {
  symbol: string;
  name: string;
  type: string;
  exchange: string;
}

export interface Series {
  symbol: string;
  label: string;
  isGold: boolean;
  currency: string;
  closes: number[];
  startPrice: number;
  endPrice: number;
  totalReturn: number;
  /** Null on windows too short to annualise honestly. */
  cagr: number | null;
  annualisedVol: number | null;
  maxDrawdown: number | null;
}

export interface History {
  dates: string[];
  series: Series[];
  start: string | null;
  limiting: string | null;
  missing: string[];
  /** True when bars are sub-daily, which changes how dates are labelled. */
  intraday: boolean;
  interval: string;
}

export const PERIODS = ['1D', '1W', '1M', '3M', '6M', '1Y', '5Y', '10Y', 'All time'] as const;
export type Period = (typeof PERIODS)[number];

export const GOLD_SYMBOL = 'GC=F';

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error(`Market API returned ${response.status}`);
  const body = await response.json();
  if (body.error) throw new Error(body.error);
  return body as T;
}

export function searchSymbols(query: string, signal?: AbortSignal): Promise<SearchResult[]> {
  return get<{ results: SearchResult[] }>(
    `/api/market/search?q=${encodeURIComponent(query)}`,
    signal,
  ).then((body) => body.results);
}

export function fetchHistory(
  symbols: string[],
  period: Period,
  signal?: AbortSignal,
): Promise<History> {
  const query = new URLSearchParams({ symbols: symbols.join(','), period });
  return get<History>(`/api/market/history?${query}`, signal);
}

/** Axis and readout labels — intraday windows need the clock, long ones do not. */
export function formatStamp(stamp: string | undefined, intraday: boolean, short = false): string {
  if (!stamp) return '—';
  const [day, clock] = stamp.split('T');
  if (!intraday) return short ? day.slice(0, 7) : day;
  const [, month, date] = day.split('-');
  return short ? `${month}-${date} ${clock}` : `${day} ${clock}`;
}

/** Human gap between two stamps, for the pinned-comparison readout. */
export function elapsedBetween(from: string | undefined, to: string | undefined): string {
  if (!from || !to) return '—';
  const ms = Math.abs(new Date(to).getTime() - new Date(from).getTime());
  if (!Number.isFinite(ms)) return '—';
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hr`;
  const days = Math.round(hours / 24);
  if (days < 60) return `${days} days`;
  const months = Math.round(days / 30.44);
  if (months < 24) return `${months} mo`;
  return `${(days / 365.25).toFixed(1)} yr`;
}
