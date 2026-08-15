import { useCallback, useEffect, useMemo, useState } from 'react';

import Emblem from '../../components/Emblem';
import Globe from '../../components/Globe';
import type { GlobePoint, GlobeRibbon } from '../../components/Globe';
import TimeChart from '../../components/TimeChart';
import { useFetch } from '../../hooks/useFetch';
import {
  INDUSTRY_LEGEND,
  asOfLabel,
  count,
  dwt,
  fetchChokepoint,
  fetchCountryTrade,
  fetchPort,
  fetchRibbon,
  fetchTradeOverview,
  industryColour,
  tons,
} from './tradeApi';
import type {
  ChokepointDetail,
  CountryTradeDetail,
  PortDetail,
  RibbonDetail,
  TradeOverview,
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

/** What the ports layer colours by. */
const PORT_METRICS = ['volume', 'change'] as const;
type PortMetric = (typeof PORT_METRICS)[number];

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
  const [portMetric, setPortMetric] = useState<PortMetric>('volume');
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
      detail: `${usd(r.valueAnnual)} a year · ${r.industry ?? 'mixed cargo'}`,
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
        value: c.capacityChangeYoY === null ? null : c.capacityChangeYoY * 100,
        detail:
          c.capacityChangeYoY === null
            ? `${dwt(c.capacity)} over 90 days`
            : `${dwt(c.capacity)} · ${move(c.capacityChangeYoY)} on a year ago`,
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
        portMetric === 'volume'
          ? volumeScale(p.tons, widestPort)
          : p.change === null
            ? null
            : p.change * 100,
      detail:
        portMetric === 'volume'
          ? `${tons(p.tons)} over 90 days · #${p.rank} worldwide`
          : `${tons(p.tons)} · ${move(p.change)} on the prior quarter`,
    }));
  }, [layer, data, portMetric, widestPort]);

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
        ? 'Deadweight through each strait, against the same period a year earlier'
        : portMetric === 'volume'
          ? 'Metric tons across the quay over the last 90 published days'
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
          <div className="world__metrics" role="group" aria-label="Colour ports by">
            {PORT_METRICS.map((option) => (
              <button
                key={option}
                type="button"
                className={portMetric === option ? 'is-on' : ''}
                onClick={() => setPortMetric(option)}
              >
                {option === 'volume' ? 'Volume' : 'Change'}
              </button>
            ))}
          </div>
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
                <li key={entry.name}>
                  <span className="trade__swatch" style={{ background: entry.colour }} />
                  {entry.name}
                </li>
              ))}
              <li>
                <span className="trade__swatch is-mixed" />
                No dominant cargo
              </li>
            </ul>
          )}
        </div>

        <RankingList
          data={data}
          layer={layer}
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
  selection,
  onSelect,
  countryName,
}: {
  data: TradeOverview;
  layer: Layer;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  countryName: Record<string, string>;
}) {
  if (layer === 'chokepoints') {
    const widest = Math.max(...data.chokepoints.map((c) => c.capacity ?? 0), 1);
    return (
      <aside className="trade__list">
        <h4 className="cpanel__title">Chokepoints by deadweight · 90 days</h4>
        <ul className="trade__rows">
          {data.chokepoints.map((c) => (
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
                  style={{ width: `${((c.capacity ?? 0) / widest) * 100}%` }}
                />
              </span>
              <span className="trade__rowvalue">{dwt(c.capacity)}</span>
              <span className={`trade__rowchange ${(c.capacityChangeYoY ?? 0) >= 0 ? 'up' : 'down'}`}>
                {move(c.capacityChangeYoY)}
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

  const widest = Math.max(...data.ports.map((p) => p.tons ?? 0), 1);
  return (
    <aside className="trade__list">
      <h4 className="cpanel__title">Busiest ports · 90 days</h4>
      <ul className="trade__rows">
        {data.ports.slice(0, 40).map((p) => (
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
              <span className="trade__fill" style={{ width: `${((p.tons ?? 0) / widest) * 100}%` }} />
            </span>
            <span className="trade__rowvalue">{tons(p.tons)}</span>
            <span className={`trade__rowchange ${(p.change ?? 0) >= 0 ? 'up' : 'down'}`}>
              {move(p.change)}
            </span>
          </li>
        ))}
      </ul>
      <p className="trade__note">
        Tonnage is estimated from vessel draft, so it measures what the hulls carried rather than
        what customs recorded.
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
  const port = detail.data;

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
        <Figure label="Tonnage · 90 days" value={tons(port.tons)} note={move(port.change)} tone={(port.change ?? 0) >= 0 ? 'up' : 'down'} />
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
            value={flow.topIndustry}
            note={`${((flow.topIndustryShare ?? 0) * 100).toFixed(0)}% of the flow`}
          />
        )}
      </div>

      <h4 className="cpanel__title">What it carries</h4>
      <ul className="trade__mix">
        {flow.industries.map((industry) => (
          <li key={industry.name}>
            <span className="trade__mixlabel">
              <span
                className="trade__swatch"
                style={{ background: industryColour(industry.name) ?? 'var(--goods-other)' }}
              />
              {industry.name}
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

      <button
        type="button"
        className="trade__link"
        onClick={() => onSelect({ kind: 'port', id: flow.portId })}
      >
        Open {flow.portName} →
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
