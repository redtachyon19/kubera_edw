import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { elapsedBetween, formatStamp } from './api';
import type { Series } from './api';

export type Scale = 'price' | 'rebased' | 'growth';

export interface PriceChartProps {
  dates: string[];
  series: Series[];
  colours: Record<string, string>;
  scale: Scale;
  intraday: boolean;
}

const PAD = { top: 16, right: 84, bottom: 30, left: 10 };
const WIDTH = 1000;
const HEIGHT = 400;

/** Transform a raw close series into whatever the chosen scale plots. */
function project(closes: number[], scale: Scale): number[] {
  if (scale === 'price') return closes;
  const base = closes[0];
  if (!base) return closes;
  return scale === 'growth'
    ? closes.map((v) => (v / base) * 100)
    : closes.map((v) => (v / base - 1) * 100);
}

/** Round values a reader recognises — 20, 25, 50 — not 23.7143. */
function niceTicks(min: number, max: number, count = 5): number[] {
  if (!isFinite(min) || !isFinite(max) || min === max) return [min];
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) ticks.push(v);
  return ticks;
}

/** Decade ticks — 100, 200, 500, 1000 — rather than five points evenly spaced in log space. */
function logTicks(min: number, max: number): number[] {
  if (!(min > 0) || !(max > min)) return [min, max].filter((v) => isFinite(v));
  const out: number[] = [];
  for (let e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) {
    for (const m of [1, 2, 5]) {
      const value = m * Math.pow(10, e);
      if (value >= min && value <= max) out.push(value);
    }
  }
  return out.length >= 2 ? out : niceTicks(min, max);
}

function padded(values: number[], log: boolean): [number, number] {
  const finite = values.filter((v) => isFinite(v));
  let lo = Math.min(...finite);
  let hi = Math.max(...finite);
  if (!isFinite(lo) || !isFinite(hi)) return [0, 1];
  if (lo === hi) return [lo - 1, hi + 1];
  if (log && lo > 0) {
    const factor = Math.pow(hi / lo, 0.05);
    return [lo / factor, hi * factor];
  }
  const pad = (hi - lo) * 0.06;
  return [lo - pad, hi + pad];
}

/**
 * Hand-drawn SVG so the chart carries the same hairlines and engraved labels as
 * the rest of the hub — a charting library would bring its own visual language.
 *
 * The three scales answer different questions and are drawn differently:
 *
 *   price    linear, anchored at zero — true to scale. Height is proportional to
 *            price, so a $4,100 instrument sits ~13x above a $300 one. Cheap
 *            series compress near the axis; that is the real proportion.
 *   rebased  linear, shared, zero line — every series starts level, for comparing
 *            movement rather than level.
 *   growth   log — an indexed scale where one large winner would otherwise
 *            flatten the rest.
 *
 * Click anchors a point; sweeping then draws a chord from the anchor to the
 * cursor and the readout reports the move between those two moments.
 */
export default function PriceChart({ dates, series, colours, scale, intraday }: PriceChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);

  useEffect(() => setPinned(null), [dates, scale]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setPinned(null);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;

  const model = useMemo(() => {
    const projected = series.map((s) => ({ ...s, values: project(s.closes, scale) }));

    const all = projected.flatMap((s) => s.values);

    // Price is drawn true to scale: one linear axis anchored at zero, so twice
    // the height means twice the price and $4,100 gold sits ~13x above a $300
    // share. Neither log nor a min-anchored axis preserves that — both make the
    // picture easier to read by making the proportions wrong. A cheap series
    // will look flat down at the bottom; that is the honest shape of it, and
    // Rebased % is the scale for reading its movement.
    const log = scale === 'growth' && all.every((v) => v > 0);

    const shared: [number, number] =
      scale === 'price'
        ? [0, Math.max(...all.filter(isFinite)) * 1.04]
        : padded(all, log);

    const toY = (value: number) => {
      const [lo, hi] = shared;
      const t = log
        ? (Math.log(Math.max(value, 1e-9)) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))
        : (value - lo) / (hi - lo);
      return PAD.top + plotH - t * plotH;
    };
    const toX = (i: number) => PAD.left + (dates.length < 2 ? 0 : (i / (dates.length - 1)) * plotW);

    const ticks = (log ? logTicks(shared[0], shared[1]) : niceTicks(shared[0], shared[1])).map(
      (v) => ({ value: v, y: toY(v) }),
    );

    return { projected, toX, toY, ticks, log };
  }, [dates, series, scale, plotW, plotH]);

  const xTicks = useMemo(() => {
    const count = Math.min(7, dates.length);
    if (count < 2) return [];
    return Array.from({ length: count }, (_, k) =>
      Math.round((k / (count - 1)) * (dates.length - 1)),
    );
  }, [dates]);

  const inRange = useCallback(
    (index: number | null): number | null => {
      if (index === null || !Number.isFinite(index)) return null;
      return Math.max(0, Math.min(dates.length - 1, Math.round(index)));
    },
    [dates.length],
  );

  const indexAt = useCallback(
    (clientX: number) => {
      const rect = svgRef.current?.getBoundingClientRect();
      // A zero-width box makes the ratio 0/0 — and `Math.max(0, Math.min(n, NaN))`
      // is NaN, not a clamp, so an unguarded NaN would index past the array.
      if (!rect || !rect.width || dates.length < 2) return null;
      const x = ((clientX - rect.left) / rect.width) * WIDTH - PAD.left;
      return inRange((x / plotW) * (dates.length - 1));
    },
    [dates.length, plotW, inRange],
  );

  const pin = inRange(pinned);
  const cur = inRange(hover);
  const comparing = pin !== null && cur !== null && cur !== pin;

  const money = (v: number) => {
    if (v === 0) return '0';
    const decimals = v < 10 ? 2 : v < 1000 ? 2 : 0;
    return v.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  };
  const fmt = (v: number) =>
    scale === 'rebased' ? `${v >= 0 ? '+' : ''}${v.toFixed(0)}%` : money(v);

  return (
    <figure className="chart">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className={`chart__svg${pin !== null ? ' is-pinned' : ''}`}
        onMouseMove={(event) => setHover(indexAt(event.clientX))}
        onMouseLeave={() => setHover(null)}
        onClick={(event) => {
          const index = indexAt(event.clientX);
          setPinned((current) => (current === index ? null : index));
        }}
        role="img"
        aria-label="Price comparison chart"
      >
        {model.ticks.map((tick) => (
          <g key={tick.value}>
            <line
              className="chart__grid"
              x1={PAD.left}
              x2={PAD.left + plotW}
              y1={tick.y}
              y2={tick.y}
            />
            <text
              className="chart__ylabel"
              x={PAD.left + plotW + 8}
              y={tick.y}
              dominantBaseline="middle"
            >
              {fmt(tick.value)}
            </text>
          </g>
        ))}

        {scale === 'rebased' && (
          <line
            className="chart__zero"
            x1={PAD.left}
            x2={PAD.left + plotW}
            y1={model.toY(0)}
            y2={model.toY(0)}
          />
        )}

        {xTicks.map((index) => (
          <text
            key={index}
            className="chart__xlabel"
            x={model.toX(index)}
            y={HEIGHT - 10}
            textAnchor={index === 0 ? 'start' : index === dates.length - 1 ? 'end' : 'middle'}
          >
            {formatStamp(dates[index], intraday, true)}
          </text>
        ))}

        {model.projected.map((s) => (
          <path
            key={s.symbol}
            className="chart__line"
            stroke={colours[s.symbol]}
            d={s.values
              .map((v, k) => `${k === 0 ? 'M' : 'L'}${model.toX(k)},${model.toY(v)}`)
              .join(' ')}
          />
        ))}

        {comparing &&
          model.projected.map((s) => (
            <line
              key={`chord-${s.symbol}`}
              className="chart__chord"
              stroke={colours[s.symbol]}
              x1={model.toX(pin!)}
              y1={model.toY(s.values[pin!])}
              x2={model.toX(cur!)}
              y2={model.toY(s.values[cur!])}
            />
          ))}

        {pin !== null && (
          <>
            <line
              className="chart__anchor"
              x1={model.toX(pin)}
              x2={model.toX(pin)}
              y1={PAD.top}
              y2={PAD.top + plotH}
            />
            {model.projected.map((s) => (
              <circle
                key={`pin-${s.symbol}`}
                className="chart__anchor-dot"
                r={4}
                cx={model.toX(pin)}
                cy={model.toY(s.values[pin])}
                fill={colours[s.symbol]}
              />
            ))}
          </>
        )}

        {cur !== null && (
          <>
            <line
              className="chart__crosshair"
              x1={model.toX(cur)}
              x2={model.toX(cur)}
              y1={PAD.top}
              y2={PAD.top + plotH}
            />
            {model.projected.map((s) => (
              <circle
                key={`hov-${s.symbol}`}
                r={3.5}
                cx={model.toX(cur)}
                cy={model.toY(s.values[cur])}
                fill={colours[s.symbol]}
              />
            ))}
          </>
        )}
      </svg>

      <figcaption className="chart__readout">
        {comparing ? (
          <>
            <span className="chart__readout-date num">
              {formatStamp(dates[pin!], intraday)} → {formatStamp(dates[cur!], intraday)}
              <em> · {elapsedBetween(dates[pin!], dates[cur!])}</em>
            </span>
            {model.projected.map((s) => {
              const from = s.closes[pin!];
              const to = s.closes[cur!];
              const change = from ? (to / from - 1) * 100 : 0;
              return (
                <span key={s.symbol} className="chart__readout-item">
                  <i className="chart__swatch" style={{ background: colours[s.symbol] }} />
                  {s.label}
                  <b className={`num ${change > 0 ? 'up' : change < 0 ? 'down' : ''}`}>
                    {change >= 0 ? '+' : ''}
                    {change.toFixed(2)}%
                  </b>
                </span>
              );
            })}
          </>
        ) : (
          <>
            <span className="chart__readout-date num">
              {cur !== null
                ? formatStamp(dates[cur], intraday)
                : `${formatStamp(dates[0], intraday)} — ${formatStamp(dates[dates.length - 1], intraday)}`}
            </span>
            {model.projected.map((s) => {
              const value = cur !== null ? s.values[cur] : s.values[s.values.length - 1];
              const direction = scale === 'price' ? 0 : value - (scale === 'growth' ? 100 : 0);
              return (
                <span key={s.symbol} className="chart__readout-item">
                  <i className="chart__swatch" style={{ background: colours[s.symbol] }} />
                  {s.label}
                  <b className={`num ${direction > 0 ? 'up' : direction < 0 ? 'down' : ''}`}>
                    {fmt(value)}
                  </b>
                </span>
              );
            })}
          </>
        )}
      </figcaption>

      <p className="chart__hint">
        {pin !== null ? (
          <>
            Anchored at <b className="num">{formatStamp(dates[pin], intraday)}</b> — sweep to
            measure from it. Click again or press <kbd>Esc</kbd> to release.
          </>
        ) : (
          <>Click any point to anchor it, then sweep to compare against it.</>
        )}
      </p>
    </figure>
  );
}
