/** Company endpoints on the hub's market API (`dashboard_hub/market_api.py`). */

/** One card in the grid: what `companies.json` knows, plus the live move. */
export interface CompanyCard {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  country: string;
  currency: string;
  exchange: string;
  /** Editorial sector slugs this name belongs to, from `sectors.json`. */
  sectors: string[];
  /** True when the warehouse carries filings for it. */
  warehouse: boolean;
  last: number | null;
  periodReturn: number | null;
}

export interface Profile {
  name: string;
  sector: string;
  industry: string;
  country: string;
  website: string;
  employees: number | null;
  exchange: string;
  /** What the shares trade in. */
  currency: string;
  /** What the statements are reported in — not always the same thing. */
  reportingCurrency: string;
  inWarehouse: boolean;
}

export interface Kpis {
  price: number | null;
  previousClose: number | null;
  marketCap: number | null;
  enterpriseValue: number | null;
  trailingPe: number | null;
  forwardPe: number | null;
  priceToBook: number | null;
  priceToSales: number | null;
  evToEbitda: number | null;
  dividendYield: number | null;
  payoutRatio: number | null;
  beta: number | null;
  high52: number | null;
  low52: number | null;
  eps: number | null;
  profitMargin: number | null;
  returnOnEquity: number | null;
  revenueGrowth: number | null;
  sharesOutstanding: number | null;
  averageVolume: number | null;
  /** True when the listing trades in one currency and reports in another. */
  mixedCurrency: boolean;
}

/** One reporting period across all three statements, with its ratios. */
export interface Period {
  end: string;
  label: string;

  revenue: number | null;
  costOfRevenue: number | null;
  grossProfit: number | null;
  researchDevelopment: number | null;
  sellingGeneralAdmin: number | null;
  operatingExpense: number | null;
  operatingIncome: number | null;
  ebitda: number | null;
  interestExpense: number | null;
  pretaxIncome: number | null;
  taxProvision: number | null;
  netIncome: number | null;
  dilutedEps: number | null;
  dilutedShares: number | null;

  cash: number | null;
  totalDebt: number | null;
  netDebt: number | null;
  totalAssets: number | null;
  totalLiabilities: number | null;
  equity: number | null;
  currentAssets: number | null;
  currentLiabilities: number | null;
  workingCapital: number | null;

  operatingCashFlow: number | null;
  investingCashFlow: number | null;
  financingCashFlow: number | null;
  capitalExpenditure: number | null;
  freeCashFlow: number | null;
  dividendsPaid: number | null;
  buybacks: number | null;

  grossMargin: number | null;
  operatingMargin: number | null;
  ebitdaMargin: number | null;
  netMargin: number | null;
  fcfMargin: number | null;
  effectiveTaxRate: number | null;
  netDebtToEbitda: number | null;
  debtToEquity: number | null;
  currentRatio: number | null;
  returnOnEquity: number | null;
}

/** Numeric keys of a period — every field a statement row can point at. */
export type Line = {
  [K in keyof Period]: Period[K] extends number | null ? K : never;
}[keyof Period];

/** A filed year from `marts.fact_financials`, reported and USD-converted. */
export interface FiledYear {
  fiscalYear: number | null;
  periodEnd: string | null;
  reportingCurrency: string;
  revenue: number | null;
  revenueUsd: number | null;
  grossProfit: number | null;
  operatingIncome: number | null;
  operatingIncomeUsd: number | null;
  netIncome: number | null;
  netIncomeUsd: number | null;
  ebitda: number | null;
  ebitdaUsd: number | null;
  cash: number | null;
  totalDebt: number | null;
  netDebt: number | null;
  netDebtUsd: number | null;
  grossMargin: number | null;
  ebitdaMargin: number | null;
  netMargin: number | null;
  netDebtToEbitda: number | null;
  ratePerUsd: number | null;
  /** True when no rate was published on the period end and the prior one was used. */
  rateCarriedForward: boolean;
}

export interface Filed {
  held: boolean;
  meta: {
    legalName: string;
    cik: string;
    sector: string;
    filerType: string;
    countryIso3: string;
    reportingCurrency: string;
    taxonomy: string;
    fiscalYearEnd: string;
  } | null;
  years: FiledYear[];
}

export interface Company {
  symbol: string;
  profile: Profile;
  kpis: Kpis;
  statements: { annual: Period[]; quarterly: Period[] };
  warehouse: Filed;
  sectors: { slug: string; name: string }[];
  peers: { symbol: string; name: string }[];
}

export const CADENCES = ['annual', 'quarterly'] as const;
export type Cadence = (typeof CADENCES)[number];

/** One period on the long-run revenue series. */
export interface RevenuePoint {
  end: string;
  label: string;
  revenue: number | null;
  grossProfit: number | null;
  netIncome: number | null;
  /** True for a fourth quarter derived from the annual report, not published. */
  derived: boolean;
}

export interface RevenueSeries {
  points: RevenuePoint[];
  /** Which of the three sources answered — they reach back different distances. */
  source: string;
  derived: number;
}

export interface RevenueHistory {
  quarterly: RevenueSeries;
  annual: RevenueSeries;
  currency: string;
  /** The cadence worth opening on — the one that covers the most ground. */
  default: Cadence;
  /** False for a listing that publishes no statements: an index, fund or currency. */
  files: boolean;
  /** False when SEC EDGAR is not configured, which caps every history at Yahoo's. */
  edgar: boolean;
}

export const EMPTY_REVENUE: RevenueHistory = {
  quarterly: { points: [], source: '', derived: 0 },
  annual: { points: [], source: '', derived: 0 },
  currency: '',
  default: 'quarterly',
  files: false,
  edgar: true,
};

/** Windows offered over the revenue series, in years. `null` is everything. */
export const REVENUE_WINDOWS: { label: string; years: number | null }[] = [
  { label: '3Y', years: 3 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: 10 },
  { label: 'All time', years: null },
];

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(body.error ?? `API returned ${response.status}`);
  return body as T;
}

export function fetchCompanies(period: string, signal?: AbortSignal): Promise<CompanyCard[]> {
  return get<{ companies: CompanyCard[] }>(`/api/market/companies?period=${period}`, signal).then(
    (body) => body.companies,
  );
}

export function fetchCompany(symbol: string, signal?: AbortSignal): Promise<Company> {
  return get<Company>(`/api/market/company?symbol=${encodeURIComponent(symbol)}`, signal);
}

/**
 * Fetched separately from the company itself: it may reach out to SEC EDGAR,
 * which is slower than the quote feed, and the rest of the page should not wait
 * on it.
 */
export function fetchRevenue(symbol: string, signal?: AbortSignal): Promise<RevenueHistory> {
  return get<RevenueHistory>(`/api/market/revenue?symbol=${encodeURIComponent(symbol)}`, signal);
}

// ── Formatting ───────────────────────────────────────────────────────────────
// Statement figures run from a few million to a few trillion, and a table that
// prints every digit of both cannot be read down a column. Everything scales to
// one suffix and keeps three significant figures.

export function money(value: number | null, currency = ''): string {
  if (value === null || !isFinite(value)) return '—';
  const sign = value < 0 ? '−' : '';
  const size = Math.abs(value);
  const suffix = size >= 1e12 ? 'T' : size >= 1e9 ? 'B' : size >= 1e6 ? 'M' : size >= 1e3 ? 'K' : '';
  const divisor = { T: 1e12, B: 1e9, M: 1e6, K: 1e3, '': 1 }[suffix];
  const scaled = size / divisor;
  const digits = scaled >= 100 ? 0 : scaled >= 10 ? 1 : 2;
  const prefix = currency ? `${currency} ` : '';
  return `${prefix}${sign}${scaled.toFixed(digits)}${suffix}`;
}

export function pct(value: number | null, digits = 1, signed = false): string {
  if (value === null || !isFinite(value)) return '—';
  const lead = signed && value >= 0 ? '+' : '';
  return `${lead}${(value * 100).toFixed(digits)}%`;
}

export function times(value: number | null, digits = 1): string {
  if (value === null || !isFinite(value)) return '—';
  return `${value.toFixed(digits)}×`;
}

export function plain(value: number | null, digits = 2): string {
  if (value === null || !isFinite(value)) return '—';
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function direction(value: number | null): string {
  return value === null ? '' : value > 0 ? 'up' : value < 0 ? 'down' : '';
}
