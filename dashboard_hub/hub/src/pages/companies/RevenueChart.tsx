import { useCallback, useMemo, useRef, useState } from 'react';

import { money, pct } from './companyApi';
import type { RevenuePoint } from './companyApi';

const WIDTH = 1000;
const HEIGHT = 320;
const PAD = { top: 20, right: 80, bottom: 30, left: 10 };

/** Round values a reader recognises — 20, 25, 50 — not 23.7143. */
function niceTicks(min: number, max: number, count = 4): number[] {
  if (!isFinite(min) || !isFinite(max) || min === max) return [min];
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const ticks: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max; v += step) ticks.push(v);
  return ticks;
}

/** The lines the chart can draw, top of the income statement downwards. */
export const SERIES = ['revenue', 'grossProfit', 'netIncome'] as const;
export type Series = (typeof SERIES)[number];

export const SERIES_LABEL: Record<Series, string> = {
  revenue: 'Revenue',
  grossProfit: 'Gross profit',
  netIncome: 'Net income',
};

export interface RevenueChartProps {
  points: RevenuePoint[];
  currency: string;
  /** Which lines to draw. Revenue is the axis the others are read against. */
  shownSeries: Series[];
  /**
   * How many points back a growth comparison looks: 4 for quarterly, 1 for
   * annual. A quarter is compared with the same quarter a year earlier —
   * against the previous quarter, every seasonal business looks like it
   * collapses and recovers on a four-period cycle.
   */
  lag: number;
}

/**
 * Revenue over time, as far back as the filings go.
 *
 * Drawn as a line on a real time axis rather than as evenly spaced bars,
 * because the series now runs to seventy-odd quarters and because the gaps in
 * it are not uniform — a filer changes its fiscal calendar, or a quarter is
 * missing entirely. Bars would space those equally and quietly redraw the
 * company's history; a time axis puts each point where it happened.
 *
 * Growth is read off the crosshair rather than printed on every point. At two
 * decades of quarters there is no room to label them, and the number that
 * matters is the one under the cursor.
 */
export default function RevenueChart({ points, currency, shownSeries, lag }: RevenueChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  /**
   * A figure the axis can actually be built from.
   *
   * Not just a null check: a series the API did not send at all arrives as
   * `undefined`, and one of those in the domain makes every bound NaN and
   * collapses the whole chart to a line. An older API that predates a series is
   * exactly the case this has to survive.
   */
  const value = (point: RevenuePoint, series: Series): number | null => {
    const raw = point[series];
    return typeof raw === 'number' && isFinite(raw) ? raw : null;
  };

  const priced = useMemo(
    () => points.filter((point) => SERIES.some((series) => value(point, series) !== null)),
    // `value` is pure and depends on nothing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [points],
  );

  const model = useMemo(() => {
    if (priced.length < 2) return null;

    const times = priced.map((point) => Date.parse(point.end));
    const from = Math.min(...times);
    const to = Math.max(...times);
    const span = to - from || 1;

    const values = priced.flatMap((point) =>
      shownSeries.map((series) => value(point, series)).filter((v): v is number => v !== null),
    );
    if (values.length === 0) return null;
    const top = Math.max(...values, 0);
    const bottom = Math.min(...values, 0);
    const headroom = (top - bottom) * 0.08 || 1;
    const hi = top + headroom;
    const lo = bottom < 0 ? bottom - headroom : 0;

    const plotW = WIDTH - PAD.left - PAD.right;
    const plotH = HEIGHT - PAD.top - PAD.bottom;
    const toX = (time: number) => PAD.left + ((time - from) / span) * plotW;
    const toY = (value: number) => PAD.top + plotH - ((value - lo) / (hi - lo)) * plotH;

    const path = (pick: (point: RevenuePoint) => number | null) => {
      let out = '';
      let open = false;
      priced.forEach((point, index) => {
        const at = pick(point);
        if (at === null) {
          open = false;
          return;
        }
        out += `${open ? 'L' : 'M'}${toX(times[index]).toFixed(1)},${toY(at).toFixed(1)}`;
        open = true;
      });
      return out;
    };

    // Whole years across the window, at whatever spacing keeps the labels apart.
    const startYear = new Date(from).getUTCFullYear();
    const endYear = new Date(to).getUTCFullYear();
    const every = Math.ceil((endYear - startYear + 1) / 8) || 1;
    const years: { year: number; x: number }[] = [];
    for (let year = startYear + 1; year <= endYear; year += 1) {
      if ((year - startYear - 1) % every !== 0) continue;
      const at = Date.UTC(year, 0, 1);
      if (at >= from && at <= to) years.push({ year, x: toX(at) });
    }

    const paths = Object.fromEntries(
      shownSeries.map((series) => [series, path((point) => value(point, series))]),
    ) as Record<Series, string>;

    return { times, toX, toY, plotW, plotH, lo, hi, years, paths, zero: toY(0) };
  }, [priced, shownSeries]);

  const indexAt = useCallback(
    (clientX: number) => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect || !rect.width || !model) return null;
      const x = ((clientX - rect.left) / rect.width) * WIDTH;
      let best = 0;
      let gap = Infinity;
      model.times.forEach((time, index) => {
        const distance = Math.abs(model.toX(time) - x);
        if (distance < gap) {
          gap = distance;
          best = index;
        }
      });
      return best;
    },
    [model],
  );

  if (!model) return null;

  /**
   * A series is only green while it is in the black.
   *
   * Green means gain everywhere else in this terminal, so a line that ends
   * below zero cannot keep it — Ford's most recent quarter is a loss, and a
   * green line running under the zero rule says the opposite of what happened.
   * Judged on the latest period rather than on any dip along the way: the
   * colour states where the company stands now, and the shape of the line
   * already says where it has been.
   */
  const endsBelowZero = (pick: (point: RevenuePoint) => number | null) => {
    for (let i = priced.length - 1; i >= 0; i -= 1) {
      const at = pick(priced[i]);
      if (at !== null) return at < 0;
    }
    return false;
  };
  const tone = Object.fromEntries(
    SERIES.map((series) => [
      series,
      endsBelowZero((point) => value(point, series)) ? ' is-loss' : '',
    ]),
  ) as Record<Series, string>;

  const at = hover === null ? priced.length - 1 : hover;
  const current = priced[at];
  const before = priced[at - lag];
  const now = current ? value(current, 'revenue') : null;
  const then = before ? value(before, 'revenue') : null;
  const growth = now !== null && then !== null && then !== 0 ? now / then - 1 : null;

  return (
    <figure className="chart co__chart">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="chart__svg"
        onMouseMove={(event) => setHover(indexAt(event.clientX))}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label={`${shownSeries.map((series) => SERIES_LABEL[series]).join(', ')} over time`}
      >
        {niceTicks(model.lo, model.hi).map((tick) => (
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
              {money(tick)}
            </text>
          </g>
        ))}

        {model.lo < 0 && (
          <line
            className="chart__zero"
            x1={PAD.left}
            x2={PAD.left + model.plotW}
            y1={model.zero}
            y2={model.zero}
          />
        )}

        {model.years.map((tick) => (
          <text key={tick.year} className="chart__xlabel" x={tick.x} y={HEIGHT - 9} textAnchor="middle">
            {tick.year}
          </text>
        ))}

        {hover !== null && (
          <line
            className="chart__crosshair"
            x1={model.toX(model.times[at])}
            x2={model.toX(model.times[at])}
            y1={PAD.top}
            y2={PAD.top + model.plotH}
          />
        )}

        {shownSeries.map((series) => (
          <path
            key={series}
            className={`co__line co__line--${series}${tone[series]}`}
            d={model.paths[series]}
          />
        ))}

        {/* Every period is marked, so the reader can see where the filings
            actually are — a line alone hides whether a stretch is four
            quarters or one annual figure drawn across four years. The markers
            are hollow until swept, which keeps seventy of them quiet. */}
        {priced.map((point, index) => {
          const on = hover !== null && index === at;
          return shownSeries.map((series) =>
            value(point, series) === null ? null : (
              <circle
                key={`${series}-${point.end}`}
                className={`co__marker co__marker--${series}${tone[series]}${on ? ' is-on' : ''}`}
                r={on ? 4.5 : 3}
                cx={model.toX(model.times[index])}
                cy={model.toY(value(point, series) as number)}
              />
            ),
          );
        })}
      </svg>

      <figcaption className="chart__readout">
        <span className="chart__readout-date num">
          {current?.label ?? '—'}
          {current?.derived && <em> · derived</em>}
        </span>
        {shownSeries.map((series) => (
          <span key={series} className="chart__readout-item">
            <i className={`chart__swatch co__swatch--${series}${tone[series]}`} />
            {SERIES_LABEL[series]}
            <b className={`num ${current && (value(current, series) ?? 0) < 0 ? 'down' : ''}`}>
              {money(current ? value(current, series) : null, currency)}
            </b>
          </span>
        ))}
        {growth !== null && (
          <span className="chart__readout-item">
            {lag === 1 ? 'vs year before' : 'vs year-ago quarter'}
            <b className={`num ${growth >= 0 ? 'up' : 'down'}`}>{pct(growth, 1, true)}</b>
          </span>
        )}
      </figcaption>

      <p className="chart__hint">
        {hover === null
          ? 'Sweep the chart to read any quarter.'
          : `${priced.length} periods shown, ending ${priced[priced.length - 1].label}.`}
      </p>
    </figure>
  );
}
