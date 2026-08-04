import { useEffect, useMemo, useState } from 'react';

import Emblem from '../../components/Emblem';
import Globe from '../../components/Globe';
import type { GlobePoint } from '../../components/Globe';
import { PERIODS } from '../stock/api';
import type { Period } from '../stock/api';
import CountryPanel from './CountryPanel';
import EnergyLens from './EnergyLens';
import TradeLens from './TradeLens';
import {
  METRIC,
  METRICS,
  fetchCountry,
  fetchEnergy,
  fetchWorld,
  fetchWorldSectors,
  fxLevel,
  move,
  rate,
  tone,
} from './worldApi';
import type {
  Composition,
  EnergyPanel,
  Metric,
  TradeFlows,
  WorldCountry,
  WorldSectors,
  WorldSnapshot,
} from './worldApi';
import './World.css';

type Lens = 'governments' | 'trade' | 'sectors' | 'energy';

const LENS_LABEL: Record<Lens, string> = {
  governments: 'Governments',
  trade: 'Trade',
  sectors: 'Sectors',
  energy: 'Energy',
};

/** Sort orders offered over the country table. */
type SortKey = 'name' | Metric;

/**
 * The world desk: every government on one surface, and the sectors that lead
 * across all of them.
 *
 * Two lenses over one globe. **Governments** compares what a state reports —
 * inflation, growth, unemployment — against what its currency and its stock
 * market are doing, which are the three numbers that rarely agree. **Sectors**
 * ranks the ten global sector funds, each holding names from every market rather
 * than one, so the league table is genuinely worldwide and not a second reading
 * of the S&P.
 *
 * Macro is annual and lags by a year or two; markets and FX are live. The two
 * are deliberately shown side by side rather than blended — the gap between a
 * government's last published inflation print and what its currency has done
 * since is the interesting part, not a defect to be smoothed over.
 */
export default function World() {
  const [lens, setLens] = useState<Lens>('governments');
  const [period, setPeriod] = useState<Period>('1Y');
  const [metric, setMetric] = useState<Metric>('market');
  const [sortKey, setSortKey] = useState<SortKey>('market');
  // Columns open best-first, which is the reading most people want. But "best"
  // for inflation is the low end, and the interesting end is the other one —
  // so clicking the active column turns it around.
  const [reversed, setReversed] = useState(false);
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null);
  const [sectors, setSectors] = useState<WorldSectors | null>(null);
  const [energy, setEnergy] = useState<EnergyPanel | null>(null);
  const [reporter, setReporter] = useState('USA');
  const [flows, setFlows] = useState<TradeFlows | null>(null);
  const [composition, setComposition] = useState<Composition | null>(null);
  const [tradeLoading, setTradeLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      fetchWorld(period, controller.signal),
      fetchWorldSectors(period, controller.signal),
    ])
      .then(([world, legs]) => {
        setSnapshot(world);
        setSectors(legs);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [period]);

  // Energy is its own lens and its own request — the governments view should not
  // wait on the pits, and vice versa.
  useEffect(() => {
    if (lens !== 'energy') return undefined;
    const controller = new AbortController();
    fetchEnergy(period, controller.signal)
      .then(setEnergy)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      });
    return () => controller.abort();
  }, [lens, period]);

  // Trade is annual and does not move with the period selector, so it is keyed
  // only on which country is reporting.
  useEffect(() => {
    if (lens !== 'trade') return undefined;
    const controller = new AbortController();
    setTradeLoading(true);
    fetchCountry(reporter, period, controller.signal)
      .then((detail) => {
        setFlows(detail.trade);
        setComposition(detail.composition);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setTradeLoading(false));
    return () => controller.abort();
  }, [lens, reporter, period]);

  const spec = METRIC[metric];

  const points: GlobePoint[] = useMemo(() => {
    if (!snapshot) return [];
    return snapshot.countries
      .filter((c) => isFinite(c.lat) && isFinite(c.lon))
      .map((country) => {
        const value = spec.value(country);
        return {
          iso3: country.iso3,
          name: country.name,
          lat: country.lat,
          lon: country.lon,
          value,
          detail:
            value === null
              ? 'No reading'
              : spec.fractional
                ? move(value)
                : rate(value, 2),
        };
      });
  }, [snapshot, spec]);

  // Only countries that actually report the metric belong in the table; the
  // globe still shows the rest as bare fixes so the world keeps its shape.
  const rows: WorldCountry[] = useMemo(() => {
    if (!snapshot) return [];
    const listed = snapshot.countries.filter(
      (c) =>
        c.inflation != null ||
        c.gdpGrowth != null ||
        c.marketChange != null ||
        c.fxChange != null,
    );

    const flip = reversed ? -1 : 1;
    if (sortKey === 'name') return [...listed].sort((a, b) => flip * a.name.localeCompare(b.name));

    const rank = METRIC[sortKey];
    return [...listed].sort((a, b) => {
      const left = rank.value(a);
      const right = rank.value(b);
      if (left === null && right === null) return a.name.localeCompare(b.name);
      // Countries with no reading sink to the bottom either way, rather than
      // sorting as zero and landing in the middle of the run.
      if (left === null) return 1;
      if (right === null) return -1;
      return flip * (rank.higherIsBetter ? right - left : left - right);
    });
  }, [snapshot, sortKey, reversed]);

  function sortBy(key: SortKey) {
    setReversed((current) => (key === sortKey ? !current : false));
    setSortKey(key);
  }

  const pinned = selected ? (snapshot?.countries.find((c) => c.iso3 === selected) ?? null) : null;

  const periodBar = (
    <div className="stock__switch" role="group" aria-label="Period">
      {PERIODS.filter((p) => p !== '1D' && p !== '1W').map((option) => (
        <button
          key={option}
          type="button"
          className={period === option ? 'is-on' : ''}
          onClick={() => setPeriod(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );

  const header = (
    <header className="world__head">
      <div className="world__lens" role="group" aria-label="View">
        {(Object.keys(LENS_LABEL) as Lens[]).map((option) => (
          <button
            key={option}
            type="button"
            className={lens === option ? 'is-on' : ''}
            onClick={() => setLens(option)}
          >
            {LENS_LABEL[option]}
          </button>
        ))}
      </div>
      {periodBar}
    </header>
  );

  if (error) {
    return (
      <section className="world">
        {header}
        <p className="world__error">The world desk could not be loaded — {error}</p>
      </section>
    );
  }

  return (
    <section className="world">
      {header}

      {lens === 'governments' ? (
        <>
          <div className="world__metrics" role="group" aria-label="Metric">
            {METRICS.map((option) => (
              <button
                key={option}
                type="button"
                className={metric === option ? 'is-on' : ''}
                onClick={() => {
                  setMetric(option);
                  sortBy(option);
                }}
              >
                {METRIC[option].label}
              </button>
            ))}
          </div>

          <div className="world__globe">
            <Globe
              points={points}
              midpoint={spec.midpoint}
              spread={spec.spread}
              higherIsBetter={spec.higherIsBetter}
              selected={selected}
              onSelect={setSelected}
              caption={snapshot ? spec.caption(snapshot) : 'Loading'}
            />
            <p className="world__legend">
              <span className="world__swatch is-down" />
              {spec.higherIsBetter ? 'Weaker' : 'Higher'}
              <span className="world__swatch is-mid" />
              <span className="world__swatch is-up" />
              {spec.higherIsBetter ? 'Stronger' : 'Lower'}
            </p>
          </div>

          {/* Opening a country is the point of the globe, so its detail gets the
              full width rather than a column beside it — there are four charts
              and a news list in there. */}
          {selected && pinned && (
            <CountryPanel iso3={selected} period={period} onClose={() => setSelected(null)} />
          )}
          {!selected && (
            <p className="world__hint">
              Click a country on the globe, or a row below, for its purchasing power in gold, what
              it trades, who with, and its news.
            </p>
          )}

          <div className="world__tablewrap">
            <table className="world__table">
              <caption className="world__caption">
                {rows.length} countries ·{' '}
                {snapshot ? `macro from ${snapshot.macroSource}` : 'loading'} · FX and equity
                markets live from Yahoo over {period}
              </caption>
              <thead>
                <tr>
                  <Th
                    label="Country"
                    active={sortKey === 'name'}
                    reversed={reversed}
                    onClick={() => sortBy('name')}
                  />
                  <Th
                    label="Inflation"
                    active={sortKey === 'inflation'}
                    reversed={reversed}
                    onClick={() => sortBy('inflation')}
                    numeric
                  />
                  <Th
                    label="GDP growth"
                    active={sortKey === 'gdpGrowth'}
                    reversed={reversed}
                    onClick={() => sortBy('gdpGrowth')}
                    numeric
                  />
                  <Th
                    label="Unemployment"
                    active={sortKey === 'unemployment'}
                    reversed={reversed}
                    onClick={() => sortBy('unemployment')}
                    numeric
                  />
                  <th scope="col" className="is-numeric">
                    Currency
                  </th>
                  <Th
                    label={`vs USD ${period}`}
                    active={sortKey === 'fx'}
                    reversed={reversed}
                    onClick={() => sortBy('fx')}
                    numeric
                  />
                  <th scope="col">Benchmark</th>
                  <Th
                    label={`Market ${period}`}
                    active={sortKey === 'market'}
                    reversed={reversed}
                    onClick={() => sortBy('market')}
                    numeric
                  />
                </tr>
              </thead>
              <tbody>
                {rows.map((country) => (
                  <tr
                    key={country.iso3}
                    className={country.iso3 === selected ? 'is-pinned' : ''}
                    onClick={() =>
                      setSelected((current) => (current === country.iso3 ? null : country.iso3))
                    }
                  >
                    <th scope="row">
                      <span className="world__country">
                        <Emblem id={country.iso3} kind="flag" name={country.name} size={14} />
                        {country.name}
                      </span>
                      {country.hasIssuer && (
                        <span className="world__held" title="An issuer here is indexed in the warehouse">
                          ●
                        </span>
                      )}
                    </th>
                    <td className={`is-numeric ${tone(country.inflation, false)}`}>
                      {rate(country.inflation)}
                    </td>
                    <td className={`is-numeric ${tone(country.gdpGrowth)}`}>
                      {rate(country.gdpGrowth)}
                    </td>
                    <td className={`is-numeric ${tone(country.unemployment, false)}`}>
                      {rate(country.unemployment)}
                    </td>
                    <td className="is-numeric world__fx">
                      {country.currency ? (
                        <>
                          <span className="world__ccy">{country.currency}</span>
                          {fxLevel(country.fxPerUsd)}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className={`is-numeric ${tone(country.fxChange)}`}>
                      {move(country.fxChange)}
                    </td>
                    <td className="world__bench">{country.index ?? '—'}</td>
                    <td className={`is-numeric ${tone(country.marketChange)}`}>
                      {move(country.marketChange)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : lens === 'trade' ? (
        <TradeLens
          countries={snapshot?.countries ?? []}
          reporter={reporter}
          onReporter={setReporter}
          flows={flows}
          composition={composition}
          loading={tradeLoading}
        />
      ) : lens === 'energy' ? (
        <EnergyLens panel={energy} period={period} loading={loading} />
      ) : (
        <SectorLens sectors={sectors} period={period} loading={loading} />
      )}

      {loading && <p className="world__loading">Reading the world…</p>}
    </section>
  );
}

function Th({
  label,
  active,
  reversed,
  onClick,
  numeric = false,
}: {
  label: string;
  active: boolean;
  reversed: boolean;
  onClick: () => void;
  numeric?: boolean;
}) {
  return (
    <th
      scope="col"
      className={`${numeric ? 'is-numeric' : ''}${active ? ' is-sorted' : ''}${
        active && reversed ? ' is-reversed' : ''
      }`}
      aria-sort={active ? (reversed ? 'ascending' : 'descending') : 'none'}
    >
      <button type="button" onClick={onClick}>
        {label}
      </button>
    </th>
  );
}

/** The global sector league table, and the same window read by region. */
function SectorLens({
  sectors,
  period,
  loading,
}: {
  sectors: WorldSectors | null;
  period: string;
  loading: boolean;
}) {
  if (!sectors) {
    return <p className="world__loading">{loading ? 'Ranking the world…' : 'No sector data.'}</p>;
  }

  const widest = Math.max(
    ...sectors.sectors.map((s) => Math.abs(s.change)),
    ...sectors.regions.map((r) => Math.abs(r.change)),
    0.01,
  );

  const bars = (legs: typeof sectors.sectors, caption: string, note: string) => (
    <div className="world__ranking">
      <h3 className="world__ranking-title">{caption}</h3>
      <p className="world__ranking-note">{note}</p>
      <ol className="world__bars">
        {legs.map((leg) => {
          const width = (Math.abs(leg.change) / widest) * 50;
          return (
            <li key={leg.slug} className={leg.change >= 0 ? 'up' : 'down'}>
              <span className="world__bar-name">{leg.name}</span>
              <span className="world__bar-track">
                <span
                  className="world__bar-fill"
                  style={{
                    width: `${width}%`,
                    // Losses grow leftwards from the centre line, gains right,
                    // so the zero axis is a real axis and not just a colour.
                    left: leg.change >= 0 ? '50%' : `${50 - width}%`,
                  }}
                />
              </span>
              <span className="world__bar-value">{move(leg.change)}</span>
              <span className="world__bar-symbol">{leg.symbol}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );

  return (
    <div className="world__sectors">
      {bars(
        sectors.sectors,
        `Global sectors · ${period}`,
        'The ten iShares global sector funds — one per GICS sector, each holding names from every listed market. Total return in USD.',
      )}
      {bars(
        sectors.regions,
        `By region · ${period}`,
        'Broad regional funds over the same window, all USD-denominated, so the two tables read on one scale.',
      )}
    </div>
  );
}
