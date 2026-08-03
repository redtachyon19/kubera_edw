import { useMemo, useRef, useState } from 'react';

import './TimeChart.css';

/** One observation. Keys beyond `date` are series values; missing ones are gaps. */
export interface TimePoint {
  date: string;
  [key: string]: string | number | null | undefined;
}

export interface TimeLine {
  key: string;
  label: string;
}

interface Props {
  points: TimePoint[];
  lines: TimeLine[];
  /** How a value is written in the readout and on the axis. */
  format: (value: number) => string;
  /** Drawn as a dashed rule — 100 for a rebased index, 0 for a change. */
  baseline?: number | null;
  height?: number;
  caption?: string;
}

const W = 1000;
const PAD = { top: 14, right: 12, bottom: 26, left: 52 };

// Four colours, in the order series are declared. The house palette carries
// meaning in green and red, so a multi-series chart that is not about direction
// uses the neutral metals instead and lets the legend do the work.
const STROKE = ['var(--ink)', 'var(--gold)', 'var(--steel)', 'var(--bronze)'];

function value(point: TimePoint, key: string): number | null {
  const raw = point[key];
  return typeof raw === 'number' && isFinite(raw) ? raw : null;
}

/** Ticks that land on round numbers rather than wherever the data happens to end. */
function ticks(low: number, high: number, count = 4): number[] {
  const span = high - low;
  if (!isFinite(span) || span <= 0) return [low];
  const rough = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? magnitude * 10;
  const out: number[] = [];
  for (let t = Math.ceil(low / step) * step; t <= high; t += step) out.push(Number(t.toFixed(10)));
  return out;
}

/**
 * A multi-series time chart, drawn by hand.
 *
 * The x axis is proportional to real elapsed time, not to the index of the
 * point: these series come from trading days, and spacing them evenly would
 * quietly stretch every weekend and holiday.
 */
export default function TimeChart({
  points,
  lines,
  format,
  baseline = null,
  height = 260,
  caption,
}: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);

  const model = useMemo(() => {
    const stamps = points.map((p) => new Date(p.date).getTime()).filter((t) => isFinite(t));
    if (stamps.length < 2) return null;

    const t0 = stamps[0];
    const t1 = stamps[stamps.length - 1];
    const span = t1 - t0 || 1;

    let low = Infinity;
    let high = -Infinity;
    for (const point of points) {
      for (const line of lines) {
        const v = value(point, line.key);
        if (v === null) continue;
        if (v < low) low = v;
        if (v > high) high = v;
      }
    }
    if (baseline !== null) {
      low = Math.min(low, baseline);
      high = Math.max(high, baseline);
    }
    if (!isFinite(low) || !isFinite(high)) return null;
    if (low === high) {
      low -= 1;
      high += 1;
    }
    // A little air so the extremes are not drawn on the frame.
    const pad = (high - low) * 0.08;
    low -= pad;
    high += pad;

    const x = (t: number) => PAD.left + ((t - t0) / span) * (W - PAD.left - PAD.right);
    const y = (v: number) =>
      height - PAD.bottom - ((v - low) / (high - low)) * (height - PAD.top - PAD.bottom);

    const paths = lines.map((line) => {
      const segments: string[] = [];
      let drawing = false;
      points.forEach((point, i) => {
        const v = value(point, line.key);
        if (v === null) {
          drawing = false;
          return;
        }
        segments.push(`${drawing ? 'L' : 'M'}${x(stamps[i]).toFixed(1)} ${y(v).toFixed(1)}`);
        drawing = true;
      });
      return { ...line, d: segments.join('') };
    });

    return { stamps, x, y, low, high, paths, t0, span };
  }, [points, lines, baseline, height]);

  if (!model) {
    return <p className="tchart__empty">Not enough history to chart.</p>;
  }

  const { stamps, x, y, low, high, paths } = model;
  const active = hover === null ? null : points[hover];

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const box = svg.current?.getBoundingClientRect();
    if (!box) return;
    // The SVG scales to its container, so the pointer has to be mapped back
    // into viewBox units before it can be compared with the plotted positions.
    const at = ((event.clientX - box.left) / box.width) * W;
    let best = 0;
    let bestGap = Infinity;
    stamps.forEach((stamp, i) => {
      const gap = Math.abs(x(stamp) - at);
      if (gap < bestGap) {
        bestGap = gap;
        best = i;
      }
    });
    setHover(best);
  }

  const year = (stamp: number) => new Date(stamp).getFullYear();
  const yearTicks: { at: number; label: string }[] = [];
  let seen = -1;
  stamps.forEach((stamp) => {
    const y0 = year(stamp);
    if (y0 !== seen) {
      seen = y0;
      yearTicks.push({ at: x(stamp), label: String(y0) });
    }
  });

  return (
    <figure className="tchart">
      <svg
        ref={svg}
        viewBox={`0 0 ${W} ${height}`}
        className="tchart__svg"
        style={{ height }}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label={caption ?? 'Time series'}
      >
        {ticks(low, high).map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="tchart__grid" />
            <text x={PAD.left - 8} y={y(t) + 3} className="tchart__ylabel">
              {format(t)}
            </text>
          </g>
        ))}

        {baseline !== null && (
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(baseline)}
            y2={y(baseline)}
            className="tchart__baseline"
          />
        )}

        {yearTicks.map((tick) => (
          <text key={tick.label} x={tick.at} y={height - 8} className="tchart__xlabel">
            {tick.label}
          </text>
        ))}

        {paths.map((path, i) => (
          <path
            key={path.key}
            d={path.d}
            className="tchart__line"
            style={{ stroke: STROKE[i % STROKE.length] }}
          />
        ))}

        {hover !== null && (
          <>
            <line
              x1={x(stamps[hover])}
              x2={x(stamps[hover])}
              y1={PAD.top}
              y2={height - PAD.bottom}
              className="tchart__cursor"
            />
            {paths.map((path, i) => {
              const v = value(points[hover], path.key);
              return v === null ? null : (
                <circle
                  key={path.key}
                  cx={x(stamps[hover])}
                  cy={y(v)}
                  r={3.5}
                  className="tchart__dot"
                  style={{ fill: STROKE[i % STROKE.length] }}
                />
              );
            })}
          </>
        )}
      </svg>

      <figcaption className="tchart__legend">
        {lines.map((line, i) => (
          <span key={line.key} className="tchart__key">
            <span className="tchart__swatch" style={{ background: STROKE[i % STROKE.length] }} />
            {line.label}
            <span className="tchart__reading">
              {active ? format(value(active, line.key) ?? NaN) : ''}
            </span>
          </span>
        ))}
        <span className="tchart__when">{active ? active.date : (caption ?? '')}</span>
      </figcaption>
    </figure>
  );
}
