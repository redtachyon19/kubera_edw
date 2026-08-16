import { useCallback, useEffect, useMemo, useState } from 'react';

import Emblem from '../../components/Emblem';
import Globe from '../../components/Globe';
import type { GlobePoint, GlobeRibbon } from '../../components/Globe';
import TimeChart from '../../components/TimeChart';
import type { TimePoint } from '../../components/TimeChart';
import { useFetch } from '../../hooks/useFetch';
import {
  FINE_COLOUR,
  INDUSTRY,
  INDUSTRY_LEGEND,
  asOfLabel,
  count,
  dwt,
  fetchChokepoint,
  fetchCountryTrade,
  fetchPort,
  fetchRibbon,
  fetchTradeOverview,
  fetchUsPort,
  industryColour,
  industryGloss,
  industryLabel,
  tons,
} from './tradeApi';
import type {
  ChokepointDetail,
  CountryTradeDetail,
  PortDetail,
  RibbonDetail,
  TradeOverview,
  UsPortCommodities,
} from './tradeApi';
import { move, usd } from './worldApi';
import type { WorldCountry } from './worldApi';

/** Which layer the globe is drawing. */
const LAYERS = ['flows', 'ports', 'chokepoints'] as const;
type Layer = (typeof LAYERS)[number];

const LAYER_LABEL: Record<Layer, string> = {
  flows: 'Trade flows',
  ports: 'Ports',
  chokepoints: 'Chokepoints',
};

/**
 * What the ports layer measures by.
 *
 * Mass and money are different questions and they rank ports differently — a
 * crude terminal outweighs a container hub and is worth a fraction of it — so
 * both are offered rather than one standing in for "trade".
 */
const PORT_METRICS = ['mass', 'value', 'change'] as const;
type PortMetric = (typeof PORT_METRICS)[number];

const PORT_METRIC_LABEL: Record<PortMetric, string> = {
  mass: 'Tonnage',
  value: 'Value',
  change: 'Change',
};

/** What the chokepoints layer measures by. */
const CHOKE_METRICS = ['capacity', 'transits'] as const;
type ChokeMetric = (typeof CHOKE_METRICS)[number];

const CHOKE_METRIC_LABEL: Record<ChokeMetric, string> = {
  capacity: 'Deadweight',
  transits: 'Transits',
};

/** Volume is not a gain, so it gets a neutral ramp rather than the green/red one. */
const VOLUME_PALETTE = { low: 'var(--ink-4)', high: 'var(--gold)' };

/** One thing is open at a time — four kinds of thing can be. */
type Selection =
  | { kind: 'port'; id: string }
  | { kind: 'ribbon'; portId: string; partner: string; direction: string }
  | { kind: 'chokepoint'; id: string }
  | { kind: 'country'; iso3: string }
  | null;

/**
 * Trade value spans four orders of magnitude, from a $3-a-day link to a
 * $900M-a-day one. A linear width would draw all but the top twenty as
 * hairlines; a log one would flatten the top and imply Shanghai–Los Angeles is
 * comparable to Dover–Calais. A fractional power keeps the giants obviously
 * biggest while leaving the tail visible.
 */
function ribbonWeight(value: number | null, widest: number): number {
  if (!value || widest <= 0) return 0;
  return Math.pow(value / widest, 0.32);
}

/** Tonnage is just as skewed; the square root is enough to read it by area. */
function volumeScale(value: number | null, widest: number): number | null {
  if (value === null || !isFinite(value) || widest <= 0) return null;
  return Math.sqrt(Math.max(0, value) / widest) * 100;
}

/**
 * The trade desk.
 *
 * Three layers over one globe, all from IMF PortWatch and all backed by the
 * warehouse rather than a live call. **Flows** draws the ribbons — a real port at
 * one end, a partner country at the other, thickness for value and colour for
 * cargo. **Ports** ranks 2,000 quays by what actually moved across them.
 * **Chokepoints** is the 28 straits and canals the whole thing has to squeeze
 * through, which is where a disruption shows up first.
 *
 * Anything on the globe opens: a port, a ribbon, a chokepoint, or a country.
 * That is the point of the desk — the globe is the index, and the panel below is
 * the actual answer.
 *
 * **Nothing here is live.** PortWatch republishes weekly on Tuesdays and lags
 * several days behind the sea, so every panel prints the date its numbers stop
 * at rather than implying a feed.
 */
export default function TradeLens({ countries }: { countries: WorldCountry[] }) {
  const [layer, setLayer] = useState<Layer>('flows');
  const [portMetric, setPortMetric] = useState<PortMetric>('mass');
  const [chokeMetric, setChokeMetric] = useState<ChokeMetric>('capacity');
  const [selection, setSelection] = useState<Selection>(null);

  const desk = useFetch<TradeOverview>((signal) => fetchTradeOverview(signal), []);
  const data = desk.data;

  // Switching layer invalidates a selection made on a different one.
  useEffect(() => setSelection(null), [layer]);

  const countryName = useMemo(() => {
    const out: Record<string, string> = {};
    for (const country of countries) out[country.iso3] = country.name;
    return out;
  }, [countries]);

  const widestRibbon = useMemo(
    () => Math.max(...(data?.ribbons ?? []).map((r) => r.valueDaily ?? 0), 1),
    [data],
  );
  const widestPort = useMemo(
    () => Math.max(...(data?.ports ?? []).map((p) => p.tons ?? 0), 1),
    [data],
  );
  const richestPort = useMemo(
    () => Math.max(...(data?.ports ?? []).map((p) => p.valueDaily ?? 0), 1),
    [data],
  );

  const ribbons: GlobeRibbon[] = useMemo(() => {
    if (layer !== 'flows' || !data) return [];
    return data.ribbons.map((r) => ({
      id: r.id,
      fromLat: r.fromLat,
      fromLon: r.fromLon,
      toLat: r.toLat,
      toLon: r.toLon,
      weight: ribbonWeight(r.valueDaily, widestRibbon),
      colour: industryColour(r.industry),
      label: `${r.portName} ${r.direction === 'outbound' ? '→' : '←'} ${r.partnerName}`,
      // The readout names the cargo in words, so identity never rests on the
      // stroke colour alone.
      detail: r.industry
        ? `${usd(r.valueAnnual)} a year · ${industryLabel(r.industry)} (${INDUSTRY[r.industry]?.contains ?? ''})`
        : `${usd(r.valueAnnual)} a year · mixed cargo, none dominant`,
    }));
  }, [layer, data, widestRibbon]);

  const points: GlobePoint[] = useMemo(() => {
    if (!data) return [];

    if (layer === 'chokepoints') {
      return data.chokepoints.map((c) => ({
        id: c.chokepointId,
        name: c.name,
        lat: c.lat,
        lon: c.lon,
        value:
          chokeMetric === 'capacity'
            ? c.capacityChangeYoY === null
              ? null
              : c.capacityChangeYoY * 100
            : c.transitsChange === null
              ? null
              : c.transitsChange * 100,
        detail:
          chokeMetric === 'capacity'
            ? `${dwt(c.capacity)} · ${move(c.capacityChangeYoY)} on a year ago`
            : `${count(c.transits)} transits · ${move(c.transitsChange)} on the quarter`,
      }));
    }

    // On the flows layer the ports are still drawn, but quietly — they are the
    // anchors the ribbons land on, not the subject.
    if (layer === 'flows') {
      return data.ports.slice(0, 240).map((p) => ({
        id: p.portId,
        name: p.name,
        lat: p.lat,
        lon: p.lon,
        value: null,
        detail: `${tons(p.tons)} over 90 days`,
      }));
    }

    return data.ports.map((p) => ({
      id: p.portId,
      name: p.name,
      lat: p.lat,
      lon: p.lon,
      value:
        portMetric === 'mass'
          ? volumeScale(p.tons, widestPort)
          : portMetric === 'value'
            ? volumeScale(p.valueDaily, richestPort)
            : p.change === null
              ? null
              : p.change * 100,
      detail:
        portMetric === 'mass'
          ? `${tons(p.tons)} over 90 days · #${p.rank} by weight`
          : portMetric === 'value'
            ? `${usd(p.valueAnnual)} a year · #${p.valueRank} by value`
            : `${tons(p.tons)} · ${move(p.change)} on the prior quarter`,
    }));
  }, [layer, data, portMetric, chokeMetric, widestPort, richestPort]);

  const onSelectPoint = useCallback(
    (id: string | null) => {
      if (!id) return setSelection(null);
      setSelection(
        layer === 'chokepoints' ? { kind: 'chokepoint', id } : { kind: 'port', id },
      );
    },
    [layer],
  );

  const onSelectRibbon = useCallback((id: string | null) => {
    if (!id) return setSelection(null);
    const [portId, partner, direction] = id.split(':');
    setSelection({ kind: 'ribbon', portId, partner, direction });
  }, []);

  if (desk.error) {
    return (
      <div className="trade">
        <p className="world__error">
          The trade desk could not be loaded — {desk.error}
          <br />
          <span className="trade__hint">
            These panels read the warehouse rather than a live API. If it has not been built yet,
            run <code>make db-up &amp;&amp; make pipeline</code>.
          </span>
        </p>
      </div>
    );
  }

  if (desk.loading && !data) {
    return <p className="world__loading">Reading the world's ports…</p>;
  }
  if (!data) return null;

  const spec =
    layer === 'chokepoints'
      ? { midpoint: 0, spread: 25, higherIsBetter: true, palette: undefined }
      : layer === 'ports' && portMetric === 'change'
        ? { midpoint: 0, spread: 30, higherIsBetter: true, palette: undefined }
        : { midpoint: 50, spread: 50, higherIsBetter: true, palette: VOLUME_PALETTE };

  const caption =
    layer === 'flows'
      ? `${data.ribbons.length} largest flows · thickness is value, colour is cargo`
      : layer === 'chokepoints'
        ? chokeMetric === 'capacity'
          ? 'Deadweight through each strait, against the same period a year earlier'
          : 'Vessels transiting each strait, against the previous quarter'
        : portMetric === 'mass'
          ? 'Metric tons across the quay over the last 90 published days'
          : portMetric === 'value'
            ? 'What that cargo is worth, summed from the trade links'
            : 'Change against the previous 90 days';

  return (
    <div className="trade">
      <div className="trade__toolbar">
        <div className="world__metrics" role="group" aria-label="Layer">
          {LAYERS.map((option) => (
            <button
              key={option}
              type="button"
              className={layer === option ? 'is-on' : ''}
              onClick={() => setLayer(option)}
            >
              {LAYER_LABEL[option]}
            </button>
          ))}
        </div>

        {layer === 'ports' && (
          <div className="world__metrics" role="group" aria-label="Measure ports by">
            {PORT_METRICS.map((option) => (
              <button
                key={option}
                type="button"
                className={portMetric === option ? 'is-on' : ''}
                onClick={() => setPortMetric(option)}
              >
                {PORT_METRIC_LABEL[option]}
              </button>
            ))}
          </div>
        )}

        {layer === 'chokepoints' && (
          <div className="world__metrics" role="group" aria-label="Measure chokepoints by">
            {CHOKE_METRICS.map((option) => (
              <button
                key={option}
                type="button"
                className={chokeMetric === option ? 'is-on' : ''}
                onClick={() => setChokeMetric(option)}
              >
                {CHOKE_METRIC_LABEL[option]}
              </button>
            ))}
          </div>
        )}

        {/* No toggle on the flows layer, and a word about why rather than a
            control that silently does nothing: PortWatch values a port-to-country
            link in dollars only. The one dataset of its that carries tonnage is a
            different grain and a different set of links, so switching onto it
            would quietly change which flows are on screen. */}
        {layer === 'flows' && (
          <p className="trade__measure-note">
          Valued in dollars — PortWatch publishes no tonnage per link, and groups cargo into 13 HS
          sections, so fuels cannot be separated from ores here. A port’s tanker series does split
          energy out, with history.
        </p>
        )}

        <p className="trade__asof">
          {data.source}
          <br />
          Data to {asOfLabel(data.coverage.to)} · {count(data.coverage.observations)} port-days since{' '}
          {asOfLabel(data.coverage.from)}
        </p>
      </div>

      <div className="trade__stage">
        <div className="trade__globe">
          <Globe
            points={points}
            ribbons={ribbons}
            midpoint={spec.midpoint}
            spread={spec.spread}
            higherIsBetter={spec.higherIsBetter}
            palette={spec.palette}
            selected={
              selection?.kind === 'port' || selection?.kind === 'chokepoint' ? selection.id : null
            }
            onSelect={onSelectPoint}
            selectedRibbon={
              selection?.kind === 'ribbon'
                ? `${selection.portId}:${selection.partner}:${selection.direction}`
                : null
            }
            onSelectRibbon={onSelectRibbon}
            caption={caption}
            hint={
              layer === 'flows'
                ? 'Drag to rotate · click a ribbon for what it carries'
                : 'Drag to rotate · click a marker to open it'
            }
          />

          {layer === 'flows' && (
            <ul className="trade__legend">
              {INDUSTRY_LEGEND.map((entry) => (
                <li key={entry.name} title={`${entry.chapters} · ${entry.contains}`}>
                  <span className="trade__swatch" style={{ background: entry.colour }} />
                  <span className="trade__legendtext">
                    {entry.label}
                    {/* The HS names are opaque on their own — "Mineral Products"
                        is where the world's crude oil is. The gloss is part of
                        the label, not a tooltip nicety. */}
                    <em>{entry.contains}</em>
                  </span>
                </li>
              ))}
              <li title="No single cargo is a third or more of the flow">
                <span className="trade__swatch is-mixed" />
                <span className="trade__legendtext">
                  No dominant cargo
                  <em>a mixed service, too varied to colour honestly</em>
                </span>
              </li>
            </ul>
          )}
        </div>

        <RankingList
          data={data}
          layer={layer}
          portMetric={portMetric}
          chokeMetric={chokeMetric}
          selection={selection}
          onSelect={setSelection}
          countryName={countryName}
        />
      </div>

      <DetailPanel
        selection={selection}
        onClose={() => setSelection(null)}
        onSelect={setSelection}
        countryName={countryName}
      />
    </div>
  );
}

/** The league table beside the globe — the globe finds things, this ranks them. */
function RankingList({
  data,
  layer,
  portMetric,
  chokeMetric,
  selection,
  onSelect,
  countryName,
}: {
  data: TradeOverview;
  layer: Layer;
  portMetric: PortMetric;
  chokeMetric: ChokeMetric;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  countryName: Record<string, string>;
}) {
  if (layer === 'chokepoints') {
    const byCapacity = chokeMetric === 'capacity';
    const sized = [...data.chokepoints].sort(
      (a, b) => (byCapacity ? (b.capacity ?? 0) - (a.capacity ?? 0) : (b.transits ?? 0) - (a.transits ?? 0)),
    );
    const widest = Math.max(
      ...sized.map((c) => (byCapacity ? (c.capacity ?? 0) : (c.transits ?? 0))),
      1,
    );
    return (
      <aside className="trade__list">
        <h4 className="cpanel__title">
          Chokepoints by {byCapacity ? 'deadweight' : 'transits'} · 90 days
        </h4>
        <ul className="trade__rows">
          {sized.map((c) => (
            <li
              key={c.chokepointId}
              className={
                selection?.kind === 'chokepoint' && selection.id === c.chokepointId
                  ? 'is-pinned'
                  : ''
              }
              onClick={() => onSelect({ kind: 'chokepoint', id: c.chokepointId })}
            >
              <span className="trade__rowname">{c.name}</span>
              <span className="trade__bar">
                <span
                  className="trade__fill"
                  style={{
                    width: `${(((byCapacity ? c.capacity : c.transits) ?? 0) / widest) * 100}%`,
                  }}
                />
              </span>
              <span className="trade__rowvalue">
                {byCapacity ? dwt(c.capacity) : count(c.transits)}
              </span>
              <span
                className={`trade__rowchange ${
                  ((byCapacity ? c.capacityChangeYoY : c.transitsChange) ?? 0) >= 0 ? 'up' : 'down'
                }`}
              >
                {move(byCapacity ? c.capacityChangeYoY : c.transitsChange)}
              </span>
            </li>
          ))}
        </ul>
        <p className="trade__note">
          Change is against the same 90 days a year earlier. Deadweight moves before transit counts
          do — during the Red Sea diversions the small ships kept sailing and the large ones went
          round the Cape.
        </p>
      </aside>
    );
  }

  if (layer === 'flows') {
    const widest = Math.max(...data.ribbons.map((r) => r.valueDaily ?? 0), 1);
    return (
      <aside className="trade__list">
        <h4 className="cpanel__title">Largest flows</h4>
        <ul className="trade__rows">
          {data.ribbons.slice(0, 40).map((r) => (
            <li
              key={r.id}
              className={
                selection?.kind === 'ribbon' &&
                `${selection.portId}:${selection.partner}:${selection.direction}` === r.id
                  ? 'is-pinned'
                  : ''
              }
              onClick={() =>
                onSelect({
                  kind: 'ribbon',
                  portId: r.portId,
                  partner: r.partnerIso3,
                  direction: r.direction,
                })
              }
            >
              <span className="trade__rowname">
                <Emblem id={r.portIso3} kind="flag" name={r.portCountry} size={12} />
                {r.portName}
                <span className="trade__arrow">{r.direction === 'outbound' ? '→' : '←'}</span>
                <Emblem id={r.partnerIso3} kind="flag" name={r.partnerName} size={12} />
                {countryName[r.partnerIso3] ?? r.partnerName}
              </span>
              <span className="trade__bar">
                <span
                  className="trade__fill"
                  style={{
                    width: `${((r.valueDaily ?? 0) / widest) * 100}%`,
                    background: industryColour(r.industry) ?? 'var(--goods-other)',
                  }}
                />
              </span>
              <span className="trade__rowvalue">{usd(r.valueAnnual)}</span>
            </li>
          ))}
        </ul>
        <p className="trade__note">
          Value is what PortWatch estimates crosses this quay for that partner, annualised from a
          daily figure. An arrow away from the port is cargo leaving it.
        </p>
      </aside>
    );
  }

  // Ranked by whichever measure is selected. The two orders genuinely differ:
  // by weight the list opens with bulk and crude terminals, by value with the
  // container hubs.
  const byValue = portMetric === 'value';
  const size = (p: TradeOverview['ports'][number]) => (byValue ? p.valueDaily : p.tons) ?? 0;
  const ranked = [...data.ports].sort((a, b) => size(b) - size(a));
  const widest = Math.max(...ranked.map(size), 1);

  return (
    <aside className="trade__list">
      <h4 className="cpanel__title">
        {byValue ? 'Most valuable ports' : 'Busiest ports'} · 90 days
      </h4>
      <ul className="trade__rows">
        {ranked.slice(0, 40).map((p) => (
          <li
            key={p.portId}
            className={selection?.kind === 'port' && selection.id === p.portId ? 'is-pinned' : ''}
            onClick={() => onSelect({ kind: 'port', id: p.portId })}
          >
            <span className="trade__rowname">
              <Emblem id={p.iso3} kind="flag" name={p.country} size={12} />
              {p.name}
            </span>
            <span className="trade__bar">
              <span className="trade__fill" style={{ width: `${(size(p) / widest) * 100}%` }} />
            </span>
            <span className="trade__rowvalue">
              {byValue ? usd(p.valueAnnual) : tons(p.tons)}
            </span>
            <span className={`trade__rowchange ${(p.change ?? 0) >= 0 ? 'up' : 'down'}`}>
              {move(p.change)}
            </span>
          </li>
        ))}
      </ul>
      <p className="trade__note">
        {byValue
          ? 'Value is summed from the trade links through each port, annualised. Tonnage and value rank ports differently — an oil terminal outweighs a container hub and is worth far less.'
          : 'Tonnage is estimated from vessel draft, so it measures what the hulls carried rather than what customs recorded.'}
      </p>
    </aside>
  );
}

/** Whichever of the four things is open. */
function DetailPanel({
  selection,
  onClose,
  onSelect,
  countryName,
}: {
  selection: Selection;
  onClose: () => void;
  onSelect: (selection: Selection) => void;
  countryName: Record<string, string>;
}) {
  if (!selection) {
    return (
      <p className="trade__hint">
        Click a ribbon, a port, or a chokepoint on the globe — or a row in the table — for its
        history, its cargo and what has disrupted it.
      </p>
    );
  }

  if (selection.kind === 'port') {
    return <PortPanel portId={selection.id} onClose={onClose} onSelect={onSelect} countryName={countryName} />;
  }
  if (selection.kind === 'ribbon') {
    return (
      <RibbonPanel
        portId={selection.portId}
        partner={selection.partner}
        direction={selection.direction}
        onClose={onClose}
        onSelect={onSelect}
      />
    );
  }
  if (selection.kind === 'chokepoint') {
    return <ChokepointPanel chokepointId={selection.id} onClose={onClose} />;
  }
  return <CountryPanel iso3={selection.iso3} onClose={onClose} onSelect={onSelect} countryName={countryName} />;
}

function PanelShell({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="trade__panel">
      <header className="trade__panelhead">
        <div>
          <h3>{title}</h3>
          {subtitle && <p className="trade__panelsub">{subtitle}</p>}
        </div>
        <button type="button" className="trade__close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      {children}
    </section>
  );
}

/**
 * The five vessel classes PortWatch splits tonnage by, and the colours they take.
 *
 * Reused from the cargo palette so a container series on a port's chart is the
 * same blue as machinery on the globe, and dry bulk the same slate as minerals.
 * These are hulls rather than commodities — a "container" is a box, not a
 * cargo — but they are the only cargo breakdown with real history behind it, and
 * they line up closely enough with the industries that one palette serves both.
 */
const VESSEL_CLASSES = [
  {
    key: 'Tanker — oil, fuels, gas',
    field: 'tankerTons',
    colour: 'var(--goods-mineral)',
  },
  {
    key: 'Dry bulk — coal, ore, grain',
    field: 'dryBulkTons',
    colour: 'var(--goods-wood)',
  },
  {
    key: 'Container — manufactured goods',
    field: 'containerTons',
    colour: 'var(--goods-machinery)',
  },
  {
    key: 'General cargo — breakbulk, steel',
    field: 'generalCargoTons',
    colour: 'var(--goods-vegetable)',
  },
  { key: 'Ro-ro — vehicles', field: 'roroTons', colour: 'var(--goods-vehicles)' },
] as const;

/** How the composition chart reads: absolute tonnage, or share of the total. */
const MIX_MODES = ['tonnage', 'share'] as const;
type MixMode = (typeof MIX_MODES)[number];

function PortPanel({
  portId,
  onClose,
  onSelect,
  countryName,
}: {
  portId: string;
  onClose: () => void;
  onSelect: (selection: Selection) => void;
  countryName: Record<string, string>;
}) {
  const detail = useFetch<PortDetail>((signal) => fetchPort(portId, signal), [portId]);
  const [mixMode, setMixMode] = useState<MixMode>('tonnage');
  const port = detail.data;

  // Composition over time, from the vessel-class split. In `share` mode each
  // week is normalised to 100%, which is what actually answers "did this port
  // used to carry something else" — in absolute tonnage a shift in mix is
  // swamped by the port simply growing.
  const mix = useMemo(
    () =>
      (port?.history ?? []).map((week) => {
        const row: TimePoint = { date: week.week };
        const total = VESSEL_CLASSES.reduce(
          (sum, c) => sum + ((week[c.field] as number | null) ?? 0),
          0,
        );
        for (const c of VESSEL_CLASSES) {
          const value = (week[c.field] as number | null) ?? null;
          row[c.key] =
            mixMode === 'share'
              ? value === null || total <= 0
                ? null
                : (value / total) * 100
              : value;
        }
        return row;
      }),
    [port, mixMode],
  );

  if (detail.loading && !port) return <p className="world__loading">Opening the port…</p>;
  if (!port?.found) return <p className="world__loading">No record for this port.</p>;

  const chart = port.history.map((week) => ({
    date: week.week,
    Tonnage: week.tons,
    '13-week average': week.trend,
  }));

  return (
    <PanelShell
      title={
        <>
          <Emblem id={port.iso3} kind="flag" name={port.country} size={18} /> {port.name}
        </>
      }
      subtitle={
        <>
          {port.country} · #{port.rank} worldwide, #{port.rankInCountry} in {port.country}
          {port.locode && <> · LOCODE {port.locode}</>} · to {asOfLabel(port.asOf)}
        </>
      }
      onClose={onClose}
    >
      <div className="trade__figures">
        <Figure
          label="Tonnage · 90 days"
          value={tons(port.tons)}
          note={`${move(port.change)} · #${port.rank} by weight`}
          tone={(port.change ?? 0) >= 0 ? 'up' : 'down'}
        />
        <Figure
          label="Cargo value"
          value={`${usd(port.valueAnnual)} / yr`}
          note={`#${port.valueRank} by value`}
        />
        <Figure label="Landed" value={tons(port.importTons)} />
        <Figure label="Loaded" value={tons(port.exportTons)} />
        <Figure label="Port calls" value={count(port.portCalls)} />
        {port.shareOfCountryExports !== null && (
          <Figure
            label={`Share of ${port.country}'s exports`}
            value={`${(port.shareOfCountryExports * 100).toFixed(0)}%`}
          />
        )}
      </div>

      {port.industries.length > 0 && (
        <p className="trade__industries">
          Chiefly {port.industries.join(' · ')}
        </p>
      )}

      {chart.length > 1 && (
        <TimeChart
          points={chart}
          lines={[
            { key: 'Tonnage', label: 'Weekly tonnage' },
            { key: '13-week average', label: '13-week average' },
          ]}
          format={(value) => tons(value)}
          height={200}
          caption="Weekly import plus export tonnage. The newest bar is a partial week — PortWatch publishes mid-week."
        />
      )}

      {mix.length > 1 && (
        <section className="trade__mixchart">
          <header className="trade__mixhead">
            <h4 className="cpanel__title">What moves through here, over time</h4>
            <div className="world__metrics" role="group" aria-label="Composition as">
              {MIX_MODES.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={mixMode === option ? 'is-on' : ''}
                  onClick={() => setMixMode(option)}
                >
                  {option === 'tonnage' ? 'Tonnage' : 'Share'}
                </button>
              ))}
            </div>
          </header>

          <TimeChart
            points={mix}
            lines={VESSEL_CLASSES.map((c) => ({ key: c.key, label: c.key }))}
            format={(value) => (mixMode === 'share' ? `${value.toFixed(0)}%` : tons(value))}
            height={240}
            caption={
              mixMode === 'share'
                ? 'Each class as a share of the port’s weekly tonnage, so a change of mix shows even where the port itself grew or shrank.'
                : 'Weekly tonnage by vessel class since 2019 — the cargo breakdown that has real history behind it.'
            }
          />

          <p className="trade__note">
            Split by hull type, which is what AIS can actually see — and it is the one place
            <strong> energy separates cleanly</strong>: tankers are crude, refined fuels and gas,
            apart from the coal and ore that ride in dry bulk. Worldwide that is 28% of seaborne
            tonnage against dry bulk's 40%. The ribbons cannot make this split, because PortWatch
            aggregates them to HS section and section 5 welds fuels, ores and stone into one
            figure before publishing. The thirteen-industry view also has no past — this desk
            began recording its own on {asOfLabel(port.asOf)} and will deepen from there.
          </p>
        </section>
      )}

      <div className="trade__cols">
        {port.links.length > 0 && (
          <div>
            <h4 className="cpanel__title">Largest flows through here</h4>
            <ul className="trade__rows is-compact">
              {port.links.slice(0, 10).map((link) => (
                <li
                  key={`${link.partnerIso3}:${link.direction}`}
                  onClick={() =>
                    onSelect({
                      kind: 'ribbon',
                      portId: port.portId,
                      partner: link.partnerIso3,
                      direction: link.direction,
                    })
                  }
                >
                  <span className="trade__rowname">
                    <Emblem id={link.partnerIso3} kind="flag" name={link.partnerName} size={12} />
                    {countryName[link.partnerIso3] ?? link.partnerName}
                    <span className="trade__arrow">{link.direction === 'outbound' ? '→' : '←'}</span>
                  </span>
                  <span className="trade__rowvalue">{usd(link.valueAnnual)}</span>
                  <span className="trade__rowtag">{link.industry ?? 'mixed'}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <h4 className="cpanel__title">Disruptions</h4>
          {port.disruptions.length === 0 ? (
            <p className="trade__note">Nothing on record has closed this port since 2019.</p>
          ) : (
            <ul className="trade__events">
              {port.disruptions.map((event) => (
                <li key={event.eventId}>
                  <span className={`trade__alert is-${(event.alertLevel ?? '').toLowerCase()}`}>
                    {event.alertLevel ?? '—'}
                  </span>
                  <span>
                    <strong>{event.type}</strong>
                    {event.name && ` · ${event.name}`}
                    <br />
                    <span className="trade__note">
                      {asOfLabel(event.from)} — {asOfLabel(event.to)} ({event.days} days)
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {port.iso3 === 'USA' && <UsCustomsPanel portName={port.name} />}

      <button
        type="button"
        className="trade__link"
        onClick={() => onSelect({ kind: 'country', iso3: port.iso3 })}
      >
        See all of {port.country}'s seaborne trade →
      </button>
    </PanelShell>
  );
}

function RibbonPanel({
  portId,
  partner,
  direction,
  onClose,
  onSelect,
}: {
  portId: string;
  partner: string;
  direction: string;
  onClose: () => void;
  onSelect: (selection: Selection) => void;
}) {
  const detail = useFetch<RibbonDetail>(
    (signal) => fetchRibbon(portId, partner, direction, signal),
    [portId, partner, direction],
  );
  const flow = detail.data;

  if (detail.loading && !flow) return <p className="world__loading">Opening the flow…</p>;
  if (!flow?.found) return <p className="world__loading">No record for this flow.</p>;

  const widest = Math.max(...flow.industries.map((i) => i.valueDaily ?? 0), 1);
  // PortWatch's published total and the sum of its named industries do not
  // always agree, because coverage of the parts is uneven. Where the gap is
  // material the panel says so rather than quietly showing one of the two.
  const gap =
    flow.publishedTotal && flow.industrySum
      ? Math.abs(flow.publishedTotal - flow.industrySum) / flow.publishedTotal
      : 0;

  return (
    <PanelShell
      title={
        <>
          {flow.portName}
          <span className="trade__arrow">{flow.direction === 'outbound' ? '→' : '←'}</span>
          <Emblem id={flow.partnerIso3} kind="flag" name={flow.partnerName} size={18} />{' '}
          {flow.partnerName}
        </>
      }
      subtitle={
        <>
          {flow.direction === 'outbound' ? 'Loaded at' : 'Landed at'} {flow.portName},{' '}
          {flow.portCountry} · #{flow.rank} flow worldwide, #{flow.rankInPort} through this port
        </>
      }
      onClose={onClose}
    >
      <div className="trade__figures">
        <Figure label="Value" value={`${usd(flow.valueAnnual)} / yr`} note={`${usd(flow.valueDaily)} a day`} />
        <Figure label="Cargo types" value={String(flow.industryCount)} />
        {flow.topIndustry && (
          <Figure
            label="Dominant cargo"
            value={industryLabel(flow.topIndustry)}
            note={`${((flow.topIndustryShare ?? 0) * 100).toFixed(0)}% of the flow`}
          />
        )}
        <Figure
          label="Rank"
          value={`#${flow.rank}`}
          note={`worldwide · #${flow.rankInPort} through this port · #${flow.rankInCountry} for ${flow.portCountry}`}
        />
      </div>

      {flow.topIndustry && INDUSTRY[flow.topIndustry] && (
        <p className="trade__industries">
          <strong>{industryLabel(flow.topIndustry)}</strong> is {INDUSTRY[flow.topIndustry].chapters} —{' '}
          {INDUSTRY[flow.topIndustry].contains}.
        </p>
      )}

      <h4 className="cpanel__title">What it carries</h4>
      <ul className="trade__mix">
        {flow.industries.map((industry) => (
          <li key={industry.name}>
            <span className="trade__mixlabel" title={industryGloss(industry.name) ?? undefined}>
              <span
                className="trade__swatch"
                style={{ background: industryColour(industry.name) ?? 'var(--goods-other)' }}
              />
              <span className="trade__legendtext">
                {industryLabel(industry.name)}
                <em>{INDUSTRY[industry.name]?.contains}</em>
              </span>
            </span>
            <span className="trade__bar">
              <span
                className="trade__fill"
                style={{
                  width: `${((industry.valueDaily ?? 0) / widest) * 100}%`,
                  background: industryColour(industry.name) ?? 'var(--goods-other)',
                }}
              />
            </span>
            <span className="trade__rowvalue">{usd(industry.valueAnnual)}</span>
            <span className="trade__rowtag">{((industry.share ?? 0) * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>

      <p className="trade__note">
        Cargo is grouped into the thirteen industries PortWatch reports, each mapping to HS
        sections.{' '}
        {gap > 0.02 && (
          <>
            Its published total for this flow ({usd(flow.publishedTotal)}/day) and the sum of the
            named cargoes ({usd(flow.industrySum)}/day) differ by{' '}
            {(gap * 100).toFixed(0)}% — coverage of the individual industries is uneven, and the
            total is the more reliable of the two.
          </>
        )}
      </p>

      <p className="trade__note">
        <strong>This breakdown has no history yet.</strong> PortWatch values a link as a single
        current figure and publishes no past versions, so there is nothing to backfill — the
        composition above is as it stands today. The desk snapshots it on every weekly refresh, so
        this panel will grow a real "what did this route used to carry" series from here. The
        tonnage crossing {flow.portName} does have history back to 2019, and that is on the port's
        own page.
      </p>

      <button
        type="button"
        className="trade__link"
        onClick={() => onSelect({ kind: 'port', id: flow.portId })}
      >
        Open {flow.portName} for its tonnage since 2019 →
      </button>
    </PanelShell>
  );
}

function ChokepointPanel({ chokepointId, onClose }: { chokepointId: string; onClose: () => void }) {
  const detail = useFetch<ChokepointDetail>(
    (signal) => fetchChokepoint(chokepointId, signal),
    [chokepointId],
  );
  const point = detail.data;

  if (detail.loading && !point) return <p className="world__loading">Opening the chokepoint…</p>;
  if (!point?.found) return <p className="world__loading">No record for this chokepoint.</p>;

  const chart = point.history.map((day) => ({
    date: day.date,
    Deadweight: day.capacity,
    '7-day average': day.capacityTrend,
    'A year earlier': day.capacityYearAgo,
  }));

  return (
    <PanelShell
      title={point.name}
      subtitle={<>{point.fullName ?? point.country} · to {asOfLabel(point.asOf)}</>}
      onClose={onClose}
    >
      <div className="trade__figures">
        <Figure
          label="Deadweight · 90 days"
          value={dwt(point.capacity)}
          note={`${move(point.capacityChangeYoY)} on a year ago`}
          tone={(point.capacityChangeYoY ?? 0) >= 0 ? 'up' : 'down'}
        />
        <Figure
          label="Transits"
          value={count(point.transits)}
          note={`${move(point.transitsChange)} on the quarter`}
          tone={(point.transitsChange ?? 0) >= 0 ? 'up' : 'down'}
        />
        <Figure label="Tankers" value={count(point.tankerTransits)} />
        <Figure label="Container ships" value={count(point.containerTransits)} />
        <Figure label="Dry bulk" value={count(point.dryBulkTransits)} />
      </div>

      {chart.length > 1 && (
        <TimeChart
          points={chart}
          lines={[
            { key: 'Deadweight', label: 'Daily deadweight' },
            { key: '7-day average', label: '7-day average' },
            { key: 'A year earlier', label: 'A year earlier' },
          ]}
          format={(value) => dwt(value)}
          height={220}
          caption="Aggregate deadweight of everything that transited, daily. Deadweight falls before transit counts do — a diverted ULCV is one ship and a great deal of capacity."
        />
      )}
    </PanelShell>
  );
}

function CountryPanel({
  iso3,
  onClose,
  onSelect,
  countryName,
}: {
  iso3: string;
  onClose: () => void;
  onSelect: (selection: Selection) => void;
  countryName: Record<string, string>;
}) {
  const detail = useFetch<CountryTradeDetail>((signal) => fetchCountryTrade(iso3, signal), [iso3]);
  const country = detail.data;

  if (detail.loading && !country) return <p className="world__loading">Opening the country…</p>;
  if (!country?.found) return <p className="world__loading">No seaborne trade on record here.</p>;

  const chart = country.history.map((week) => ({
    date: week.week,
    Landed: week.importTons,
    Loaded: week.exportTons,
  }));

  const widestPort = Math.max(...country.ports.map((p) => p.tons ?? 0), 1);
  const exports = country.partners.filter((p) => p.direction === 'outbound').slice(0, 10);
  const imports = country.partners.filter((p) => p.direction === 'inbound').slice(0, 10);

  return (
    <PanelShell
      title={
        <>
          <Emblem id={iso3} kind="flag" name={countryName[iso3] ?? iso3} size={18} />{' '}
          {countryName[iso3] ?? iso3}
        </>
      }
      subtitle={`${country.ports.length} ports on record`}
      onClose={onClose}
    >
      {chart.length > 1 && (
        <TimeChart
          points={chart}
          lines={[
            { key: 'Landed', label: 'Landed (imports)' },
            { key: 'Loaded', label: 'Loaded (exports)' },
          ]}
          format={(value) => tons(value)}
          height={200}
          caption="Weekly tonnage across every port in the country."
        />
      )}

      <div className="trade__cols">
        <div>
          <h4 className="cpanel__title">Ports</h4>
          <ul className="trade__rows is-compact">
            {country.ports.slice(0, 12).map((port) => (
              <li key={port.portId} onClick={() => onSelect({ kind: 'port', id: port.portId })}>
                <span className="trade__rowname">{port.name}</span>
                <span className="trade__bar">
                  <span
                    className="trade__fill"
                    style={{ width: `${((port.tons ?? 0) / widestPort) * 100}%` }}
                  />
                </span>
                <span className="trade__rowvalue">{tons(port.tons)}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h4 className="cpanel__title">Largest counterparties</h4>
          <div className="trade__partners">
            <div>
              <h5>Ships to</h5>
              <ul className="trade__rows is-compact">
                {exports.map((partner) => (
                  <li key={partner.iso3}>
                    <span className="trade__rowname">
                      <Emblem id={partner.iso3} kind="flag" name={partner.name} size={12} />
                      {countryName[partner.iso3] ?? partner.name}
                    </span>
                    <span className="trade__rowvalue">{usd(partner.valueAnnual)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h5>Receives from</h5>
              <ul className="trade__rows is-compact">
                {imports.map((partner) => (
                  <li key={partner.iso3}>
                    <span className="trade__rowname">
                      <Emblem id={partner.iso3} kind="flag" name={partner.name} size={12} />
                      {countryName[partner.iso3] ?? partner.name}
                    </span>
                    <span className="trade__rowvalue">{usd(partner.valueAnnual)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}

function Figure({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: 'up' | 'down';
}) {
  return (
    <div className="trade__figure">
      <span className="trade__figlabel">{label}</span>
      <span className="trade__figvalue">{value}</span>
      {note && <span className={`trade__fignote ${tone ?? ''}`}>{note}</span>}
    </div>
  );
}


/**
 * US customs detail, and the only place on this desk where energy stands alone.
 *
 * Everything else groups cargo by HS section, which welds crude oil, gas and
 * coal together with iron ore, cement and salt — one is the energy trade and the
 * other is rocks, and PortWatch publishes them pre-summed so they cannot be
 * separated. Census reports chapters, so here chapter 27 is its own line with a
 * decade of monthly history behind it.
 *
 * US ports only, and only once `CENSUS_API_KEY` is set; the panel simply does
 * not render otherwise.
 */
function UsCustomsPanel({ portName }: { portName: string }) {
  // Census port codes are not PortWatch port ids, and the two are joined on
  // name. Resolved server-side would be better; matching here keeps the extra
  // round trip off every non-US port.
  const [byValue, setByValue] = useState(true);
  const detail = useFetch<UsPortCommodities>(
    (signal) => fetchUsPort(portName, signal),
    [portName],
  );
  const us = detail.data;

  if (detail.loading && !us) return null;
  if (!us?.found || us.months.length < 2) return null;

  // Value and mass rank commodities very differently — coal is heavy and cheap,
  // pharmaceuticals the reverse — so both are offered on real customs figures.
  const lines = us.categories.map((c) => ({
    key: byValue ? c.name : `${c.name}__kg`,
    label: c.name,
  }));

  // TimeChart keys its x axis on `date`; the API speaks in months. Mapped here
  // rather than renamed upstream, so the payload keeps saying what it means.
  const points = us.months.map((row) => ({ ...row, date: String(row.month) }));

  return (
    <section className="trade__mixchart">
      <header className="trade__mixhead">
        <h4 className="cpanel__title">What customs actually recorded</h4>
        <div className="world__metrics" role="group" aria-label="Measure US trade by">
          <button type="button" className={byValue ? 'is-on' : ''} onClick={() => setByValue(true)}>
            Value
          </button>
          <button type="button" className={!byValue ? 'is-on' : ''} onClick={() => setByValue(false)}>
            Mass
          </button>
        </div>
      </header>

      <TimeChart
        points={points as never}
        lines={lines}
        format={(value) => (byValue ? usd(value) : tons(value / 1000))}
        height={240}
        caption={
          byValue
            ? 'Monthly customs value by commodity group. Energy — crude, refined fuels, gas and coal — is its own line here, which the global ribbons cannot do.'
            : 'The same trade by waterborne weight. Heavy-and-cheap swaps places with light-and-dear — coal against pharmaceuticals — so the two readings rank commodities quite differently.'
        }
      />

      <div className="trade__cols">
        <div>
          <h4 className="cpanel__title">Largest commodities on record</h4>
          <ul className="trade__rows is-compact">
            {us.topChapters.slice(0, 10).map((c) => (
              <li key={c.chapter}>
                <span className="trade__rowname">
                  <span
                    className="trade__swatch"
                    style={{ background: FINE_COLOUR[c.category ?? ''] ?? 'var(--goods-other)' }}
                  />
                  HS {c.chapter} · {c.name}
                </span>
                <span className="trade__rowvalue">{usd(c.valueUsd)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="trade__note">
        US Census Bureau, port of entry × partner × HS chapter, monthly since 2013. Public domain.
        This is what was declared to customs rather than inferred from how deep the hulls sat, so
        it is the one layer that can separate fuels from ores.
        {us.matchedPorts && us.matchedPorts.length > 0 && (
          <>
            {' '}The two sources share no port identifier, so this counts the Census ports whose
            names sit inside <strong>{portName}</strong>: {us.matchedPorts.join(' · ')}.
          </>
        )}
      </p>
    </section>
  );
}
