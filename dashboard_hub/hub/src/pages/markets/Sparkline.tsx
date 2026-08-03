/**
 * A pair's rolling correlation as a hairline trace.
 *
 * A headline of +0.71 can be a band from +0.40 to +0.90, so the shape of the
 * relationship over time says more than its average. Fixed to a -1..+1 scale so
 * every sparkline in a list is directly comparable, with a rule at zero.
 */
export default function Sparkline({ series, width = 92, height = 22 }: {
  series: number[];
  width?: number;
  height?: number;
}) {
  if (series.length < 2) return null;
  const toY = (v: number) => height - ((Math.max(-1, Math.min(1, v)) + 1) / 2) * height;
  const toX = (i: number) => (i / (series.length - 1)) * width;
  const d = series.map((v, i) => `${i === 0 ? 'M' : 'L'}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(' ');
  const last = series[series.length - 1];

  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <line className="spark__zero" x1={0} x2={width} y1={toY(0)} y2={toY(0)} />
      <path className="spark__line" d={d} />
      <circle className="spark__dot" cx={toX(series.length - 1)} cy={toY(last)} r={1.8} />
    </svg>
  );
}
