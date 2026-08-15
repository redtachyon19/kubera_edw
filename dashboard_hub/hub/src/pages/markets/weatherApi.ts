/** Weather desk endpoints on the hub's market API (`dashboard_hub/lib/weather.py`). */

/** How a capital's conditions group, for colouring and for filtering. */
export type Band =
  | 'clear'
  | 'cloud'
  | 'overcast'
  | 'fog'
  | 'rain'
  | 'snow'
  | 'thunderstorm'
  | 'unknown';

export interface Condition {
  /** The raw WMO 4677 code, or null where nothing was reported. */
  code: number | null;
  label: string;
  band: Band;
}

/** Current conditions at one capital. */
export interface WeatherPlace {
  iso3: string;
  name: string;
  capital: string | null;
  region: string;
  lat: number;
  lon: number;
  temperature: number | null;
  apparent: number | null;
  humidity: number | null;
  precipitation: number | null;
  wind: number | null;
  condition: Condition;
}

export interface WeatherSnapshot {
  countries: WeatherPlace[];
  /** The observation time the upstream reported, in UTC. */
  asOf: string | null;
  source: string;
  units: Record<string, string>;
}

/** One tropical cyclone the NHC is advising on. */
export interface Storm {
  id: string;
  name: string;
  classification: string;
  /** The classification spelled out — "Hurricane", "Tropical storm". */
  kind: string;
  /** Saffir-Simpson 1–5, or null below hurricane strength. */
  category: number | null;
  /** Sustained wind in knots. */
  intensity: number | null;
  /** Central pressure in millibars. */
  pressure: number | null;
  lat: number;
  lon: number;
  movementDir: number | null;
  movementSpeed: number | null;
  basin: string;
  lastUpdate: string | null;
}

export interface StormReport {
  storms: Storm[];
  /** Which basins the feed covers — the rest of the world is not "calm". */
  basins: string[];
  source?: string;
  /** Set when the feed could not be reached, which is not the same as no storms. */
  error?: string;
}

/** One significant wildfire, from GDACS. */
export interface Fire {
  id: string;
  name: string;
  country: string;
  iso3: string;
  lat: number;
  lon: number;
  /** Burned area — what "massive" actually means here. */
  hectares: number | null;
  /** GDACS alert level: Red, Orange or Green. */
  alert: string;
  alertRank: number;
  /** False for a fire GDACS still lists but no longer reports as burning. */
  current: boolean;
  from: string | null;
  to: string | null;
}

export interface FireReport {
  fires: Fire[];
  /** Records thrown away for having impossible coordinates. */
  dropped?: number;
  source?: string;
  error?: string;
}

export const LAYERS = ['temperature', 'apparent', 'humidity', 'precipitation', 'wind'] as const;
export type Layer = (typeof LAYERS)[number];

interface LayerSpec {
  label: string;
  unit: string;
  /** Where the colour ramp sits neutral, and how far from it saturates. */
  midpoint: number;
  spread: number;
  /**
   * Which end of the ramp a high reading takes. Every weather layer sets this
   * true: the ramp here is a physical scale, not a verdict, and the palette
   * below is what decides whether "high" is hot, wet or windy.
   */
  higherIsBetter: boolean;
  /** The two colours the ramp runs between. */
  palette: { low: string; high: string };
  digits: number;
  value: (place: WeatherPlace) => number | null;
}

export const LAYER: Record<Layer, LayerSpec> = {
  temperature: {
    label: 'Temperature',
    unit: '°C',
    // Neutral at 15°C, saturating around freezing and around 35 — the range a
    // populated capital actually spans. Centring on zero would paint most of
    // the inhabited world the same colour.
    midpoint: 15,
    spread: 20,
    higherIsBetter: true,
    palette: { low: 'var(--cold)', high: 'var(--hot)' },
    digits: 1,
    value: (p) => p.temperature,
  },
  apparent: {
    label: 'Feels like',
    unit: '°C',
    midpoint: 15,
    spread: 20,
    higherIsBetter: true,
    palette: { low: 'var(--cold)', high: 'var(--hot)' },
    digits: 1,
    value: (p) => p.apparent,
  },
  humidity: {
    label: 'Humidity',
    unit: '%',
    midpoint: 55,
    spread: 40,
    higherIsBetter: true,
    // Dry reads warm and sandy, humid reads blue — the same axis as rain, which
    // is what the reader is actually asking about.
    palette: { low: 'var(--hot)', high: 'var(--cold)' },
    digits: 0,
    value: (p) => p.humidity,
  },
  precipitation: {
    label: 'Precipitation',
    unit: 'mm',
    // Most capitals report exactly zero at any given moment, so the ramp starts
    // at nothing and saturates fast — 4mm in the last hour is genuinely wet.
    midpoint: 0,
    spread: 4,
    higherIsBetter: true,
    palette: { low: 'var(--globe-neutral)', high: 'var(--cold)' },
    digits: 1,
    value: (p) => p.precipitation,
  },
  wind: {
    label: 'Wind',
    unit: 'km/h',
    midpoint: 12,
    spread: 30,
    higherIsBetter: true,
    palette: { low: 'var(--globe-neutral)', high: 'var(--storm)' },
    digits: 1,
    value: (p) => p.wind,
  },
};

/** The bands that count as weather worth naming, strongest first. */
export const SEVERE: Band[] = ['thunderstorm', 'snow', 'rain', 'fog'];

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(body.error ?? `API returned ${response.status}`);
  return body as T;
}

export function fetchWeather(signal?: AbortSignal): Promise<WeatherSnapshot> {
  return get<WeatherSnapshot>('/api/market/weather', signal);
}

/**
 * The storm feed, which is allowed to fail without taking the desk down.
 *
 * An unreachable NHC is not an empty ocean, and the two must not look the same
 * on screen — so the error is carried in the payload rather than thrown, and
 * the panel says which one happened.
 */
export async function fetchStorms(signal?: AbortSignal): Promise<StormReport> {
  try {
    return await get<StormReport>('/api/market/storms', signal);
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    return { storms: [], basins: [], error: (err as Error).message };
  }
}

/** The fire feed, which like the storms may fail without taking the desk down. */
export async function fetchFires(signal?: AbortSignal): Promise<FireReport> {
  try {
    return await get<FireReport>('/api/market/fires', signal);
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    return { fires: [], error: (err as Error).message };
  }
}

/**
 * Burned area on a 0–1 scale for the globe glyph.
 *
 * Logarithmic, because the range runs from a few hundred hectares to well over
 * a hundred thousand: on a linear scale every fire but the largest two or three
 * would draw at the floor and the layer would say nothing.
 */
export function fireWeight(hectares: number | null): number {
  if (hectares === null || !isFinite(hectares) || hectares <= 0) return 0;
  const t = Math.log10(hectares / 500) / Math.log10(200);
  return Math.max(0, Math.min(1, t));
}

/** Hectares, printed the way an area that size is actually read. */
export function area(hectares: number | null): string {
  if (hectares === null || !isFinite(hectares)) return '—';
  if (hectares >= 10000) return `${Math.round(hectares / 1000).toLocaleString()}k ha`;
  return `${Math.round(hectares).toLocaleString()} ha`;
}

/** A reading with its unit, or an em dash where there is none. */
export function reading(value: number | null, unit: string, digits = 1): string {
  if (value === null || !isFinite(value)) return '—';
  return `${value.toFixed(digits)}${unit === '%' ? '' : ' '}${unit}`;
}

/** Knots as the two units a reader actually thinks in. */
export function windSpeed(knots: number | null): string {
  if (knots === null || !isFinite(knots)) return '—';
  return `${Math.round(knots)} kt · ${Math.round(knots * 1.852)} km/h`;
}

/** "Cat 4 hurricane", or the plain classification below hurricane strength. */
export function stormTitle(storm: Storm): string {
  return storm.category ? `Cat ${storm.category} ${storm.kind.toLowerCase()}` : storm.kind;
}

/** A compass point, which is how a bearing is actually read. */
export function bearing(degrees: number | null): string {
  if (degrees === null || !isFinite(degrees)) return '—';
  const points = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
  return points[Math.round(((degrees % 360) + 360) % 360 / 22.5) % 16];
}
