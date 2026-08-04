import { useEffect, useMemo, useState } from 'react';

import Emblem from '../../components/Emblem';
import Globe from '../../components/Globe';
import type { GlobePoint } from '../../components/Globe';
import Select from '../../components/Select';
import { move, rate, tone, usd } from './worldApi';
import type { Composition, TradeFlows, WorldCountry } from './worldApi';

/** How the globe is coloured when a reporter is chosen. */
const VIEWS = ['balance', 'volume'] as const;
type View = (typeof VIEWS)[number];

const VIEW_LABEL: Record<View, string> = {
  balance: 'Trade balance',
  volume: 'Trade volume',
};

interface Props {
  countries: WorldCountry[];
  reporter: string;
  onReporter: (iso3: string) => void;
  flows: TradeFlows | null;
  composition: Composition | null;
  loading: boolean;
}

/**
 * Bilateral trade, on the globe.
 *
 * Pick a country and the world recolours around it: green where that country
 * sells more than it buys, red where it buys more than it sells, and the size of
 * each marker is how much trade there is at all. It answers the two questions a
 * trade table cannot — *who* matters, and *which way does the money run* —
 * without the reader having to hold 190 rows in their head.
 */
export default function TradeLens({
  countries,
  reporter,
  onReporter,
  flows,
  composition,
  loading,
}: Props) {
  const [view, setView] = useState<View>('balance');
  const [pinned, setPinned] = useState<string | null>(null);

  // A reporter change invalidates whichever partner was pinned against the old one.
  useEffect(() => setPinned(null), [reporter]);

  const byIso3 = useMemo(() => {
    const out: Record<string, (typeof partners)[number]> = {};
    for (const partner of flows?.partners ?? []) out[partner.iso3] = partner;
    return out;
  }, [flows]);
  const partners = flows?.partners ?? [];

  // Scale is set by the largest relationship, so one dominant partner does not
  // flatten every other marker to the same dot.
  const widest = Math.max(...partners.map((p) => p.total), 1);
  const widestBalance = Math.max(...partners.map((p) => Math.abs(p.balance ?? 0)), 1);

  const points: GlobePoint[] = useMemo(
    () =>
      countries
        .filter((c) => isFinite(c.lat) && isFinite(c.lon))
        .map((country) => {
          const partner = byIso3[country.iso3];
          const isReporter = country.iso3 === reporter;
          const value = !partner
            ? null
            : view === 'balance'
              ? ((partner.balance ?? 0) / widestBalance) * 100
              : (partner.total / widest) * 100;

          return {
            iso3: country.iso3,
            name: country.name,
            lat: country.lat,
            lon: country.lon,
            value: isReporter ? null : value,
            detail: isReporter
              ? 'Reporting country'
              : !partner
                ? 'No recorded trade'
                : view === 'balance'
                  ? `${(partner.balance ?? 0) >= 0 ? 'Surplus' : 'Deficit'} ${usd(Math.abs(partner.balance ?? 0))}`
                  : `${usd(partner.total)} two-way`,
          };
        }),
    [countries, byIso3, reporter, view, widest, widestBalance],
  );

  const reporterName = countries.find((c) => c.iso3 === reporter)?.name ?? reporter;
  // `Select` is a list of strings, so the country name is the value the control
  // carries and the ISO3 is looked back up on change.
  const names = useMemo(
    () => countries.map((c) => c.name).sort((a, b) => a.localeCompare(b)),
    [countries],
  );
  const top = partners.slice(0, 12);
  const pinnedPartner = pinned ? byIso3[pinned] : null;

  const surplus = partners.filter((p) => (p.balance ?? 0) > 0).reduce((a, p) => a + (p.balance ?? 0), 0);
  const deficit = partners.filter((p) => (p.balance ?? 0) < 0).reduce((a, p) => a + (p.balance ?? 0), 0);

  return (
    <div className="world__trade">
      <div className="world__tradebar">
        <Select
          label="Reporting country"
          value={reporterName}
          onChange={(name) => {
            const match = countries.find((c) => c.name === name);
            if (match) onReporter(match.iso3);
          }}
          options={names}
        />
        <div className="world__metrics" role="group" aria-label="Colour by">
          {VIEWS.map((option) => (
            <button
              key={option}
              type="button"
              className={view === option ? 'is-on' : ''}
              onClick={() => setView(option)}
            >
              {VIEW_LABEL[option]}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="world__loading">Reading {reporterName}’s trade…</p>}

      {!loading && partners.length === 0 && (
        <p className="world__loading">
          No bilateral trade is published for {reporterName} in the years WITS covers.
        </p>
      )}

      {partners.length > 0 && (
        <>
          <p className="world__tradesum">
            <strong>{reporterName}</strong> sold {usd(flows?.totalExports)} and bought{' '}
            {usd(flows?.totalImports)} in {flows?.year}. It runs a surplus of {usd(surplus)} with the
            countries it sells to and a deficit of {usd(Math.abs(deficit))} with the ones it buys
            from.
          </p>

          <div className="world__stage">
            <div className="world__globe">
              <Globe
                points={points}
                midpoint={0}
                spread={view === 'balance' ? 45 : 55}
                higherIsBetter
                selected={pinned}
                onSelect={setPinned}
                caption={
                  view === 'balance'
                    ? `Green: ${reporterName} sells more than it buys · Red: it buys more`
                    : `Marker size and colour: two-way trade with ${reporterName}`
                }
              />
            </div>

            <aside className="world__tradelist">
              <h4 className="cpanel__title">Largest counterparties · {flows?.year}</h4>
              <ul className="cpanel__partners">
                {top.map((partner) => (
                  <li
                    key={partner.iso3}
                    className={partner.iso3 === pinned ? 'is-pinned' : ''}
                    onClick={() => setPinned((c) => (c === partner.iso3 ? null : partner.iso3))}
                  >
                    <span className="cpanel__pname">
                      <Emblem id={partner.iso3} kind="flag" name={partner.name} size={14} />
                      {partner.name}
                    </span>
                    <span className="cpanel__pbar">
                      <span
                        className="cpanel__pfill is-exports"
                        style={{ width: `${((partner.exports ?? 0) / widest) * 100}%` }}
                      />
                      <span
                        className="cpanel__pfill is-imports"
                        style={{ width: `${((partner.imports ?? 0) / widest) * 100}%` }}
                      />
                    </span>
                    <span className={`cpanel__pbal ${tone(partner.balance)}`}>
                      {partner.balance === null
                        ? '—'
                        : `${partner.balance >= 0 ? '+' : '−'}${usd(Math.abs(partner.balance))}`}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="cpanel__key">
                <span className="cpanel__swatch is-exports" /> {reporterName} sells
                <span className="cpanel__swatch is-imports" /> buys
              </p>

              {pinnedPartner && (
                <p className="world__tradepin">
                  <strong>{reporterName} ↔ {pinnedPartner.name}</strong>
                  <br />
                  Sells {usd(pinnedPartner.exports)}, buys {usd(pinnedPartner.imports)} —{' '}
                  <span className={tone(pinnedPartner.balance)}>
                    {(pinnedPartner.balance ?? 0) >= 0 ? 'surplus' : 'deficit'} of{' '}
                    {usd(Math.abs(pinnedPartner.balance ?? 0))}
                  </span>
                  .
                </p>
              )}
            </aside>
          </div>

          {composition && (composition.exports.length > 0 || composition.imports.length > 0) && (
            <section className="cpanel__block">
              <h4 className="cpanel__title">
                What {reporterName} trades
                {composition.years?.exports ? ` · ${composition.years.exports}` : ''}
              </h4>
              <div className="cpanel__mix">
                {(['exports', 'imports'] as const).map((flow) => (
                  <div key={flow} className="cpanel__mixside">
                    <h5>{flow === 'exports' ? 'Sells' : 'Buys'}</h5>
                    <ul>
                      {composition[flow].map((entry) => (
                        <li key={entry.key}>
                          <span className="cpanel__mixlabel">{entry.label}</span>
                          <span className="cpanel__mixbar">
                            <span
                              className={`cpanel__mixfill is-${flow}`}
                              style={{ width: `${Math.min(100, entry.share)}%` }}
                            />
                          </span>
                          <span className="cpanel__mixvalue">{rate(entry.share)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

/** Re-exported so World.tsx can format the same way without a second import. */
export { move };
