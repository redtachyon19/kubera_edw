import { direction, money, pct, plain, times } from './companyApi';
import type { Filed } from './companyApi';

/**
 * The warehouse's own view of an issuer: figures parsed from its SEC filings.
 *
 * This is the half of the page that is not Yahoo. It exists for two reasons.
 * It is auditable — every figure traces to a filing, a taxonomy and a CIK, all
 * printed below. And it is normalised: a 20-F filer reports in its own currency,
 * so both the reported and the USD figure are shown side by side with the rate
 * that converted them. The gap between those two columns is the exchange rate,
 * not the business, and that is a distinction a single USD column erases.
 */
export default function FiledPanel({ filed }: { filed: Filed }) {
  const { meta, years } = filed;
  if (!meta || years.length === 0) return null;

  const foreign = meta.reportingCurrency !== 'USD';
  const carried = years.filter((year) => year.rateCarriedForward).length;

  return (
    <section className="co__filed" aria-label="Filed figures from the warehouse">
      <div className="sectors__bar">
        <p className="eyebrow">As filed — Kubera warehouse</p>
        <p className="co__provenance num">
          {meta.filerType} · CIK {meta.cik} · {meta.taxonomy} · FY end {meta.fiscalYearEnd}
        </p>
      </div>

      <p className="co__filed-lead">
        {meta.legalName} reports in <span className="num">{meta.reportingCurrency}</span>.
        {foreign
          ? ' Each year is converted at the rate on its own period end, so the USD column moves with the currency as well as the business.'
          : ' Reported and USD figures are the same, so no conversion is applied.'}
      </p>

      <div className="co__tablewrap">
        <table className="stock__table co__table">
          <thead>
            <tr>
              <th>FY</th>
              <th>Period end</th>
              <th className="ta-r">Revenue ({meta.reportingCurrency})</th>
              {foreign && <th className="ta-r">Revenue (USD)</th>}
              <th className="ta-r">Net income (USD)</th>
              <th className="ta-r">EBITDA margin</th>
              <th className="ta-r">Net margin</th>
              <th className="ta-r" title="Years of EBITDA it would take to clear the net debt">
                Net debt / EBITDA
              </th>
              {foreign && <th className="ta-r">Rate per USD</th>}
            </tr>
          </thead>
          <tbody>
            {[...years].reverse().map((year) => (
              <tr key={year.fiscalYear ?? year.periodEnd}>
                <td className="num">{year.fiscalYear ?? '—'}</td>
                <td className="num">{year.periodEnd ?? '—'}</td>
                <td className="num ta-r">{money(year.revenue)}</td>
                {foreign && <td className="num ta-r">{money(year.revenueUsd)}</td>}
                <td className={`num ta-r ${direction(year.netIncomeUsd)}`}>
                  {money(year.netIncomeUsd)}
                </td>
                <td className="num ta-r">{pct(year.ebitdaMargin)}</td>
                <td className={`num ta-r ${direction(year.netMargin)}`}>{pct(year.netMargin)}</td>
                <td className="num ta-r">{times(year.netDebtToEbitda)}</td>
                {foreign && (
                  <td className="num ta-r" title={year.rateCarriedForward ? 'Carried forward' : ''}>
                    {plain(year.ratePerUsd)}
                    {year.rateCarriedForward && <sup>†</sup>}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="stock__footnote">
        {years.length} filed years from <code>marts.fact_financials</code>, built from SEC EDGAR
        company facts and converted with the daily FX series.
        {carried > 0 &&
          ` † ${carried} of them fall on a day with no published rate — a weekend or a holiday — and carry the previous rate forward.`}{' '}
        These are annual periods only, and they will not tie exactly to the statements above: those
        come from Yahoo, on Yahoo's line-item mapping.
      </p>
    </section>
  );
}
