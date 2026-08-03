import { useMemo, useRef, useState } from 'react';

import type { Series } from './api';

export type Scale = 'rebased' | 'growth' | 'price';

export interface PriceChartProps {
  dates: string[];
  series: Series[];
  colours: Record<string, string>;
  scale: Scale;
}

const PAD = { top: 16, right: 74, bottom: 30, left: 10 };
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

function niceTicks(min: number, max: number, count = 5): number[] {
  if (!isFinite(min) || !isFinite(max) || min === max) return [min];
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) ticks.push(v);
  return ticks;
}

/**
 * Hand-drawn SVG so the chart carries the same hairlines and engraved labels as
 * the rest of the hub — a charting library would bring its own visual language.
 * A log scale is used for growth and price, where a single large winner would
 * otherwise flatten every other line.
 */
export default function PriceChart({ dates, series, colours, scale }: PriceChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const model = useMemo(() => {
    const projected = series.map((s) => ({ ...s, values: project(s.closes, scale) }));
    const flat = projected.flatMap((s) => s.values).filter((v) => isFinite(v));
    const useLog = scale !== 'rebased' && flat.every((v) => v > 0);

    let min = Math.min(...flat);
    let max = Math.max(...flat);
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const pad = (max - min) * 0.06;
    min -= pad;
    max += pad;
    if (useLog && min <= 0) min = Math.min(...flat.filter((v) => v > 0)) * 0.9;

    const plotW = WIDTH - PAD.left - PAD.right;
    const plotH = HEIGHT - PAD.top - PAD.bottom;
    const toY = (v: number) => {
      const t = useLog
        ? (Math.log(Math.max(v, 1e-9)) - Math.log(min)) / (Math.log(max) - Math.log(min))
        : (v - min) / (max - min);
      return PAD.top + plotH - t * plotH;
    };
    const toX = (i: number) =>
      PAD.left + (dates.length < 2 ? 0 : (i / (dates.length - 1)) * plotW);

    const ticks = useLog
      ? Array.from({ length: 5 }, (_, k) =>
          Math.exp(Math.log(min) + ((Math.log(max) - Math.log(min)) * k) / 4),
        )
      : niceTicks(min, max);

    return { projected, toX, toY, ticks, plotW, plotH, useLog };
  }, [dates, series, scale]);

  const xTicks = useMemo(() => {
    const count = Math.min(7, dates.length);
    if (count < 2) return [];
    return Array.from({ length: count }, (_, k) =>
      Math.round((k / (count - 1)) * (dates.length - 1)),
    );
  }, [dates]);

  function onMove(event: React.MouseEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || dates.length < 2) return;
    const ratio = (event.clientX - rect.left) / rect.width;
    const x = ratio * WIDTH - PAD.left;
    const index = Math.round((x / model.plotW) * (dates.length - 1));
    setHover(Math.max(0, Math.min(dates.length - 1, index)));
  }

  const fmt = (v: number) =>
    scale === 'rebased'
      ? `${v >= 0 ? '+' : ''}${v.toFixed(0)}%`
      : v.toLocaleString(undefined, { maximumFractionDigits: v < 10 ? 2 : 0 });

  return (
    <figure className="chart">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="chart__svg"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Price comparison chart"
      >
        {model.ticks.map((tick) => (
          <g key={tick}>
            <line
              className="chart__grid"
              x1={PAD.left}
              x2={PAD.left + model.plotW}
              y1={model.toY(tick)}
              y2={model.toY(tick)}
            />
            <text
              className="chart__ylabel"
              x={PAD.left + model.plotW + 8}
              y={model.toY(tick)}
              dominantBaseline="middle"
            >
              {fmt(tick)}
            </text>
          </g>
        ))}

        {/* Zero line only means something on the rebased scale. */}
        {scale === 'rebased' && (
          <line
            className="chart__zero"
            x1={PAD.left}
            x2={PAD.left + model.plotW}
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
            {dates[index]?.slice(0, 7)}
          </text>
        ))}

        {model.projected.map((s) => (
          <path
            key={s.symbol}
            className="chart__line"
            stroke={colours[s.symbol]}
            d={s.values
              .map((v, i) => `${i === 0 ? 'M' : 'L'}${model.toX(i)},${model.toY(v)}`)
              .join(' ')}
          />
        ))}

        {hover !== null && (
          <>
            <line
              className="chart__crosshair"
              x1={model.toX(hover)}
              x2={model.toX(hover)}
              y1={PAD.top}
              y2={PAD.top + model.plotH}
            />
            {model.projected.map((s) => (
              <circle
                key={s.symbol}
                r={3.5}
                cx={model.toX(hover)}
                cy={model.toY(s.values[hover])}
                fill={colours[s.symbol]}
              />
            ))}
          </>
        )}
      </svg>

      <figcaption className="chart__readout">
        <span className="chart__readout-date num">
          {hover !== null ? dates[hover] : `${dates[0]} — ${dates[dates.length - 1]}`}
        </span>
        {model.projected.map((s) => {
          const value = hover !== null ? s.values[hover] : s.values[s.values.length - 1];
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
      </figcaption>
    </figure>
  );
}
