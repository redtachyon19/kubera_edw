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
  cagr: number | null;
  annualisedVol: number;
  maxDrawdown: number | null;
}

export interface History {
  dates: string[];
  series: Series[];
  start: string | null;
  limiting: string | null;
  missing: string[];
}

export const PERIODS = ['1Y', '5Y', '10Y', 'All time'] as const;
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
