import { useMemo, useState } from 'react';

import Emblem from '../../components/Emblem';
import Globe from '../../components/Globe';
import type { GlobeMark, GlobePoint } from '../../components/Globe';
import {
  LAYER,
  LAYERS,
  SEVERE,
  area,
  bearing,
  fireWeight,
  reading,
  stormTitle,
  windSpeed,
} from './weatherApi';
import type {
  Band,
  FireReport,
  Layer,
  StormReport,
  WeatherPlace,
  WeatherSnapshot,
} from './weatherApi';
import './Weather.css';

/**
 * How many fires get a glyph. Off-season this is every one of them; at the peak
 * of a bad northern summer GDACS can carry well over a hundred, and a globe with
 * a hundred flames on it has stopped being a map. The list below keeps them all.
 */
const FIRES_ON_GLOBE = 40;

/** What each band is called in the conditions strip, in the order it is shown. */
const BAND_LABEL: Record<Band, string> = {
  thunderstorm: 'Thunderstorms',
  snow: 'Snow',
  rain: 'Rain',
  fog: 'Fog',
  overcast: 'Overcast',
  cloud: 'Cloud',
  clear: 'Clear',
  unknown: 'No reading',
};

/**
 * The weather lens: what it is doing right now, everywhere, on the same globe.
 *
 * Two feeds with deliberately different reach, kept visibly apart rather than
 * blended. Conditions come from Open-Meteo at all 212 capitals, which is a
 * genuinely worldwide reading. Named cyclones come from the US National
 * Hurricane Center, which only advises on the Atlantic and the eastern and
 * central Pacific — so a quiet storm panel means quiet *there*, and the panel
 * says so rather than letting an empty list imply a calm planet.
 *
 * A capital is not a country's weather, and the desk does not pretend otherwise:
 * these are point readings at 212 named cities, which is what a globe of dots
 * can honestly carry. Colouring whole landmasses would imply a gridded field
 * this page never fetched.
 */
export default function WeatherLens({
  snapshot,
  report,
  fireReport,
  loading,
}: {
  snapshot: WeatherSnapshot | null;
  report: StormReport | null;
  fireReport: FireReport | null;
  loading: boolean;
}) {
  const [layer, setLayer] = useState<Layer>('temperature');
  const [selected, setSelected] = useState<string | null>(null);

  const spec = LAYER[layer];

  const points: GlobePoint[] = useMemo(() => {
    if (!snapshot) return [];
    return snapshot.countries
      .filter((place) => isFinite(place.lat) && isFinite(place.lon))
      .map((place) => {
        const value = spec.value(place);
        return {
          id: place.iso3,
          name: place.capital ? `${place.capital}, ${place.name}` : place.name,
          lat: place.lat,
          lon: place.lon,
          value,
          detail:
            value === null
              ? 'No reading'
              : `${reading(value, spec.unit, spec.digits)} · ${place.condition.label}`,
        };
      });
  }, [snapshot, spec]);

  const marks: GlobeMark[] = useMemo(() => {
    const cyclones: GlobeMark[] = (report?.storms ?? []).map((storm) => ({
      id: `storm-${storm.id}`,
      kind: 'cyclone' as const,
      lat: storm.lat,
      lon: storm.lon,
      label: storm.name,
      detail: `${stormTitle(storm)} · ${windSpeed(storm.intensity)}`,
      // A hurricane runs the top of the scale; anything weaker sits near the
      // floor rather than at it, so a tropical storm is still findable.
      weight: storm.category ? storm.category / 5 : 0.15,
      heading: storm.movementDir,
    }));

    const blazes: GlobeMark[] = (fireReport?.fires ?? [])
      .slice(0, FIRES_ON_GLOBE)
      .map((fire) => ({
        id: `fire-${fire.id}`,
        kind: 'fire' as const,
        lat: fire.lat,
        lon: fire.lon,
        label: fire.name,
        detail: `${area(fire.hectares)} · ${fire.alert} alert${fire.current ? ' · burning' : ''}`,
        weight: fireWeight(fire.hectares),
        heading: null,
      }));

    return [...blazes, ...cyclones];
  }, [report, fireReport]);

  // The bands worth naming, and who is in them. A reader asking "where are the
  // storms" wants the list, not to hunt a spinning globe for purple dots.
  const bands = useMemo(() => {
    const groups = new Map<Band, WeatherPlace[]>();
    for (const place of snapshot?.countries ?? []) {
      const band = place.condition.band;
      if (!SEVERE.includes(band)) continue;
      const bucket = groups.get(band) ?? [];
      bucket.push(place);
      groups.set(band, bucket);
    }
    return SEVERE.map((band) => ({ band, places: groups.get(band) ?? [] })).filter(
      (group) => group.places.length > 0,
    );
  }, [snapshot]);

  const ranked = useMemo(() => {
    const listed = (snapshot?.countries ?? []).filter((place) => spec.value(place) !== null);
    // Extremes first and both ends kept: the hottest and the coldest capital are
    // each the answer to a question somebody has, and a single-ended sort throws
    // one of them away.
    return [...listed].sort((a, b) => (spec.value(b) ?? 0) - (spec.value(a) ?? 0));
  }, [snapshot, spec]);

  const extremes = useMemo(() => {
    if (ranked.length < 2) return null;
    return { hottest: ranked.slice(0, 5), coldest: ranked.slice(-5).reverse() };
  }, [ranked]);

  const pinned = selected
    ? (snapshot?.countries.find((place) => place.iso3 === selected) ?? null)
    : null;

  const asOf = snapshot?.asOf ? `${snapshot.asOf.replace('T', ' ')} UTC` : 'loading';

  return (
    <div className="weather">
      <div className="world__metrics" role="group" aria-label="Weather layer">
        {LAYERS.map((option) => (
          <button
            key={option}
            type="button"
            className={layer === option ? 'is-on' : ''}
            onClick={() => setLayer(option)}
          >
            {LAYER[option].label}
          </button>
        ))}
      </div>

      <div className="world__globe">
        <Globe
          points={points}
          midpoint={spec.midpoint}
          spread={spec.spread}
          higherIsBetter={spec.higherIsBetter}
          palette={spec.palette}
          marks={marks}
          selected={selected}
          onSelect={setSelected}
          hint="Drag to rotate · click a capital to pin it"
          caption={`${spec.label} at 212 capitals · ${asOf}`}
        />
        <p className="world__legend">
          <span className="weather__swatch" style={{ background: spec.palette.low }} />
          {spec.label === 'Humidity' ? 'Dry' : 'Low'}
          <span className="weather__swatch is-mid" />
          <span className="weather__swatch" style={{ background: spec.palette.high }} />
          {spec.label === 'Humidity' ? 'Humid' : 'High'}
        </p>
      </div>

      {pinned && (
        <div className="weather__pinned">
          <h3 className="weather__pinned-title">
            <Emblem id={pinned.iso3} kind="flag" name={pinned.name} size={16} />
            {pinned.capital ? `${pinned.capital}, ${pinned.name}` : pinned.name}
          </h3>
          <dl className="weather__facts">
            <Fact label="Condition" value={pinned.condition.label} />
            <Fact label="Temperature" value={reading(pinned.temperature, '°C')} />
            <Fact label="Feels like" value={reading(pinned.apparent, '°C')} />
            <Fact label="Humidity" value={reading(pinned.humidity, '%', 0)} />
            <Fact label="Precipitation" value={reading(pinned.precipitation, 'mm')} />
            <Fact label="Wind" value={reading(pinned.wind, 'km/h')} />
          </dl>
          <button type="button" className="weather__close" onClick={() => setSelected(null)}>
            Close
          </button>
        </div>
      )}

      <FirePanel report={fireReport} loading={loading} />

      <StormPanel report={report} loading={loading} />

      <section className="weather__bands">
        <h3 className="weather__section-title">Live conditions</h3>
        <p className="weather__note">
          Grouped from the WMO code each capital is reporting now. This reading is worldwide —
          unlike the cyclone feed above, nothing here is limited to one ocean.
        </p>
        {bands.length === 0 ? (
          <p className="weather__quiet">
            {loading ? 'Reading the sky…' : 'Nothing but clear, cloud and overcast at every capital.'}
          </p>
        ) : (
          <ul className="weather__band-list">
            {bands.map(({ band, places }) => (
              <li key={band} className={`weather__band is-${band}`}>
                <span className="weather__band-name">{BAND_LABEL[band]}</span>
                <span className="weather__band-count">{places.length}</span>
                <span className="weather__band-places">
                  {places.slice(0, 14).map((place) => (
                    <button
                      key={place.iso3}
                      type="button"
                      className="weather__chip"
                      onClick={() => setSelected(place.iso3)}
                      title={`${place.condition.label} · ${reading(place.temperature, '°C')}`}
                    >
                      <Emblem id={place.iso3} kind="flag" name={place.name} size={11} />
                      {place.capital ?? place.name}
                    </button>
                  ))}
                  {places.length > 14 && (
                    <span className="weather__chip is-more">+{places.length - 14}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {extremes && (
        <section className="weather__extremes">
          <Extreme
            title={`Highest ${spec.label.toLowerCase()}`}
            places={extremes.hottest}
            spec={spec}
            onSelect={setSelected}
          />
          <Extreme
            title={`Lowest ${spec.label.toLowerCase()}`}
            places={extremes.coldest}
            spec={spec}
            onSelect={setSelected}
          />
        </section>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="weather__fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/**
 * Significant wildfires worldwide, largest burn first.
 *
 * GDACS keeps an event listed after the flames are out, which is the right call
 * — a fire that took 66,000 hectares last week is still the story — but the two
 * states are marked rather than merged, because "burning now" and "burned" are
 * different answers to the question the reader is asking.
 */
function FirePanel({ report, loading }: { report: FireReport | null; loading: boolean }) {
  if (report?.error) {
    return (
      <section className="weather__fires">
        <h3 className="weather__section-title">Wildfires</h3>
        <p className="weather__storm-error">
          The GDACS wildfire feed could not be reached — {report.error}. Nothing is known about
          fires right now; this is not a report that there are none.
        </p>
      </section>
    );
  }

  if (!report || report.fires.length === 0) {
    return (
      <section className="weather__fires">
        <h3 className="weather__section-title">Wildfires</h3>
        <p className="weather__quiet">
          {loading ? 'Reading the fire alerts…' : 'No significant wildfires listed.'}
        </p>
      </section>
    );
  }

  const burning = report.fires.filter((fire) => fire.current).length;

  return (
    <section className="weather__fires">
      <h3 className="weather__section-title">Wildfires</h3>
      <ul className="weather__fire-list">
        {report.fires.map((fire) => (
          <li
            key={fire.id}
            className={`${fire.current ? 'is-burning' : ''} is-${fire.alert.toLowerCase()}`}
          >
            <span className="weather__fire-flag">
              {fire.iso3 && <Emblem id={fire.iso3} kind="flag" name={fire.country} size={12} />}
            </span>
            <span className="weather__fire-name">{fire.name}</span>
            <span className="weather__fire-area num">{area(fire.hectares)}</span>
            <span className={`weather__fire-alert is-${fire.alert.toLowerCase()}`}>
              {fire.alert}
            </span>
            <span className="weather__fire-state">{fire.current ? 'Burning' : 'Contained'}</span>
          </li>
        ))}
      </ul>
      <p className="weather__note">
        {report.fires.length} significant fires · {burning} still burning · worldwide, from GDACS
        and the Global Wildfire Information System, sized by hectares burned.
        {report.dropped ? ` ${report.dropped} dropped for impossible coordinates.` : ''}
        {report.fires.length > FIRES_ON_GLOBE
          ? ` The globe shows the ${FIRES_ON_GLOBE} largest; all are listed here.`
          : ''}
      </p>
    </section>
  );
}

/**
 * Active tropical cyclones, and — just as important — what the feed cannot see.
 *
 * Three states that must not look alike: storms running, no storms in the
 * covered basins, and a feed that could not be reached at all. The last is the
 * dangerous one to render as an empty list.
 */
function StormPanel({ report, loading }: { report: StormReport | null; loading: boolean }) {
  const basins = report?.basins?.length ? report.basins.join(', ') : 'Atlantic and Pacific';

  return (
    <section className="weather__storms">
      <h3 className="weather__section-title">Tropical cyclones</h3>

      {report?.error ? (
        <p className="weather__storm-error">
          The National Hurricane Center feed could not be reached — {report.error}. This is not the
          same as no storms; the ocean is unread, not quiet.
        </p>
      ) : !report ? (
        <p className="weather__quiet">{loading ? 'Reading the advisories…' : 'No storm data.'}</p>
      ) : report.storms.length === 0 ? (
        <p className="weather__quiet">
          No active cyclones in the {basins}. The NHC does not advise on other basins, so a typhoon
          in the western Pacific would not appear here — the thunderstorm list below is the
          worldwide reading.
        </p>
      ) : (
        <>
          <ul className="weather__storm-list">
            {report.storms.map((storm) => (
              <li key={storm.id} className={storm.category ? 'is-hurricane' : ''}>
                <span className="weather__storm-name">{storm.name}</span>
                <span className="weather__storm-kind">{stormTitle(storm)}</span>
                <span className="weather__storm-wind num">{windSpeed(storm.intensity)}</span>
                <span className="weather__storm-pressure num">
                  {storm.pressure === null ? '—' : `${Math.round(storm.pressure)} mb`}
                </span>
                <span className="weather__storm-move">
                  {storm.movementSpeed === null
                    ? 'Stationary'
                    : `${bearing(storm.movementDir)} at ${Math.round(storm.movementSpeed)} kt`}
                </span>
                <span className="weather__storm-basin">{storm.basin}</span>
              </li>
            ))}
          </ul>
          <p className="weather__note">
            {report.storms.length} active · National Hurricane Center, covering the {basins} only.
          </p>
        </>
      )}
    </section>
  );
}

function Extreme({
  title,
  places,
  spec,
  onSelect,
}: {
  title: string;
  places: WeatherPlace[];
  spec: (typeof LAYER)[Layer];
  onSelect: (iso3: string) => void;
}) {
  return (
    <div className="weather__extreme">
      <h3 className="weather__section-title">{title}</h3>
      <ol className="weather__extreme-list">
        {places.map((place) => (
          <li key={place.iso3}>
            <button type="button" onClick={() => onSelect(place.iso3)}>
              <Emblem id={place.iso3} kind="flag" name={place.name} size={12} />
              <span className="weather__extreme-name">{place.capital ?? place.name}</span>
              <span className="weather__extreme-value num">
                {reading(spec.value(place), spec.unit, spec.digits)}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
