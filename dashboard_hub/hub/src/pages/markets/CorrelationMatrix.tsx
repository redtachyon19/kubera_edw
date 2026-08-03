import { useState } from 'react';

import { METHOD_HINT, METHOD_LABEL, METHODS } from './sectorApi';
import type { Method } from './sectorApi';

/**
 * Pairwise correlation as a ruled grid.
 *
 * Correlation is computed on **returns**, not prices: two names can both drift
 * up and look related on a price chart while their day-to-day moves are
 * unconnected. Shade runs green for names that travel together and red for those
 * that move against each other, so the eye reads blocks of related businesses.
 */
export default function CorrelationMatrix({
  labels,
  matrices,
  onPick,
}: {
  labels: string[];
  matrices: Record<Method, (number | null)[][]>;
  onPick?: (a: string, b: string) => void;
}) {
  const [hover, setHover] = useState<{ row: number; col: number } | null>(null);
  const [method, setMethod] = useState<Method>('pearson');
  const available = METHODS.filter((m) => (matrices[m]?.length ?? 0) > 0);
  const active = matrices[method]?.length ? method : (available[0] ?? 'pearson');
  const matrix = matrices[active] ?? [];

  function tone(value: number | null): string {
    if (value === null) return 'transparent';
    // Diagonal and near-perfect pairs saturate; weak ones stay close to paper.
    const strength = Math.min(Math.abs(value), 1);
    const colour = value >= 0 ? 'var(--up)' : 'var(--down)';
    return `color-mix(in srgb, ${colour} ${Math.round(strength * 82)}%, transparent)`;
  }

  return (
    <div className="corr">
      <div className="corr__methods">
        <div className="stock__switch" role="group" aria-label="Correlation method">
          {available.map((option) => (
            <button
              key={option}
              type="button"
              title={METHOD_HINT[option]}
              className={active === option ? 'is-on' : ''}
              onClick={() => setMethod(option)}
            >
              {METHOD_LABEL[option]}
            </button>
          ))}
        </div>
        <p className="corr__hint">{METHOD_HINT[active]}</p>
      </div>

      <table className="corr__table">
        <thead>
          <tr>
            <th />
            {labels.map((label, col) => (
              <th key={label} className={hover?.col === col ? 'is-lit' : undefined}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((rowLabel, row) => (
            <tr key={rowLabel}>
              <th scope="row" className={hover?.row === row ? 'is-lit' : undefined}>
                {rowLabel}
              </th>
              {labels.map((colLabel, col) => {
                const value = matrix[row]?.[col] ?? null;
                const self = row === col;
                return (
                  <td
                    key={colLabel}
                    className={`corr__cell${self ? ' is-self' : ''}`}
                    style={{ background: self ? 'transparent' : tone(value) }}
                    title={`${rowLabel} ~ ${colLabel}: ${value === null ? 'n/a' : value.toFixed(3)}`}
                    onMouseEnter={() => setHover({ row, col })}
                    onMouseLeave={() => setHover(null)}
                    onClick={() => !self && onPick?.(rowLabel, colLabel)}
                  >
                    <span className="num">
                      {self ? '·' : value === null ? '' : value.toFixed(2).replace('0.', '.')}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="corr__key">
        <span className="corr__swatch" style={{ background: 'var(--down)' }} /> move apart
        <span className="corr__scale" />
        <span className="corr__swatch" style={{ background: 'var(--up)' }} /> move together
        <em>— correlation of daily returns, never of price. Click a cell to chart the pair.</em>
      </p>
    </div>
  );
}
