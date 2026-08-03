import { useState } from 'react';

import { direction, money, pct, plain, times } from './companyApi';
import type { Line, Period } from './companyApi';

export interface Row {
  line: Line;
  label: string;
  format: 'money' | 'pct' | 'times' | 'plain';
  /** Shown before the table is expanded. Everything else is behind the toggle. */
  key?: true;
  /** `total` rules off above the row; `sub` indents it under the one before. */
  tone?: 'total' | 'sub';
  /** Colour the figure by sign — for results that can be a loss, not for levels. */
  signed?: boolean;
  hint?: string;
}

export interface StatementTableProps {
  caption: string;
  periods: Period[];
  rows: Row[];
  currency: string;
}

/**
 * One statement, periods across and line items down.
 *
 * It opens on the handful of lines the statement is actually read for and keeps
 * the rest a click away. A full income statement is forty rows once margins,
 * balance sheet and cash flow are stacked with it, and a page that opens on all
 * of them buries the four figures most readers came for. The full detail is one
 * button away and the button says how much is behind it.
 *
 * Rows an issuer does not report are dropped rather than drawn empty: Yahoo
 * normalises the line items but not every filer has them, and a bank's income
 * statement with a blank Gross profit row implies a figure was lost rather than
 * never published.
 */
export default function StatementTable({ caption, periods, rows, currency }: StatementTableProps) {
  const [expanded, setExpanded] = useState(false);

  const present = rows.filter((row) => periods.some((period) => period[row.line] !== null));
  if (present.length === 0 || periods.length === 0) return null;

  const headline = present.filter((row) => row.key);
  // A statement with nothing marked, or with everything reported anyway, has no
  // second tier to hide.
  const collapsible = headline.length > 0 && headline.length < present.length;
  const shown = collapsible && !expanded ? headline : present;
  const hidden = present.length - headline.length;

  function draw(row: Row, period: Period): string {
    const value = period[row.line];
    if (row.format === 'money') return money(value, '');
    if (row.format === 'pct') return pct(value);
    if (row.format === 'times') return times(value);
    return plain(value);
  }

  return (
    <div className="co__statement">
      <div className="co__tablewrap">
        <table className="stock__table co__table">
          <caption className="co__caption">
            {caption}
            {currency && <span className="co__caption-ccy num">{currency}</span>}
          </caption>
          <thead>
            <tr>
              <th>Line item</th>
              {periods.map((period) => (
                <th key={period.end} className="ta-r num" title={period.end}>
                  {period.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.line} className={row.tone ? `co__row--${row.tone}` : undefined}>
                <th scope="row" className="co__line" title={row.hint}>
                  {row.label}
                </th>
                {periods.map((period) => (
                  <td
                    key={period.end}
                    className={`num ta-r ${row.signed ? direction(period[row.line]) : ''}`}
                  >
                    {draw(row, period)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {collapsible && (
        <button type="button" className="co__more" onClick={() => setExpanded((on) => !on)}>
          {expanded ? 'Show key lines' : `Show all ${present.length} lines`}
          <span aria-hidden="true">{expanded ? ' ↑' : ` (+${hidden}) ↓`}</span>
        </button>
      )}
    </div>
  );
}
