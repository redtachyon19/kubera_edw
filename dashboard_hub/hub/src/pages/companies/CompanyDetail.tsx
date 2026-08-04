import { useEffect, useMemo, useState } from 'react';

import NewsFeed from '../../components/NewsFeed';
import { fetchHistory, PERIODS } from '../stock/api';
import type { History, Period as PriceWindow } from '../stock/api';
import PriceChart from '../stock/PriceChart';
import {
  CADENCES,
  EMPTY_REVENUE,
  fetchCompany,
  fetchRevenue,
  money,
  pct,
  plain,
  REVENUE_WINDOWS,
  times,
} from './companyApi';
import type { Cadence, Company, RevenueHistory } from './companyApi';
import BackfillPanel from './BackfillPanel';
import FiledPanel from './FiledPanel';
import RevenueChart, { SERIES, SERIES_LABEL } from './RevenueChart';
import type { Series } from './RevenueChart';
import StatementTable from './StatementTable';
import type { Row } from './StatementTable';

// `key` marks the lines a statement is actually read for — what shows before the
// table is expanded. The rule for choosing them: a line earns its place if a
// reader would notice it missing at a glance, not if it is needed to reconcile
// the statement. Reconciliation is what the expanded view is for.
const INCOME: Row[] = [
  { line: 'revenue', label: 'Revenue', format: 'money', tone: 'total', key: true },
  { line: 'costOfRevenue', label: 'Cost of revenue', format: 'money', tone: 'sub' },
  { line: 'grossProfit', label: 'Gross profit', format: 'money', tone: 'total', key: true },
  { line: 'researchDevelopment', label: 'Research & development', format: 'money', tone: 'sub' },
  { line: 'sellingGeneralAdmin', label: 'Selling, general & admin', format: 'money', tone: 'sub' },
  { line: 'operatingExpense', label: 'Total operating expense', format: 'money', tone: 'sub' },
  {
    line: 'operatingIncome',
    label: 'Operating income',
    format: 'money',
    tone: 'total',
    signed: true,
    key: true,
  },
  { line: 'ebitda', label: 'EBITDA', format: 'money' },
  { line: 'interestExpense', label: 'Interest expense', format: 'money', tone: 'sub' },
  { line: 'pretaxIncome', label: 'Pre-tax income', format: 'money', tone: 'total', signed: true },
  { line: 'taxProvision', label: 'Tax provision', format: 'money', tone: 'sub' },
  {
    line: 'netIncome',
    label: 'Net income',
    format: 'money',
    tone: 'total',
    signed: true,
    key: true,
  },
  { line: 'dilutedEps', label: 'Diluted EPS', format: 'plain', signed: true, key: true },
  { line: 'dilutedShares', label: 'Diluted shares', format: 'money' },
];

const MARGINS: Row[] = [
  { line: 'grossMargin', label: 'Gross margin', format: 'pct', key: true },
  { line: 'operatingMargin', label: 'Operating margin', format: 'pct', signed: true, key: true },
  { line: 'ebitdaMargin', label: 'EBITDA margin', format: 'pct' },
  { line: 'netMargin', label: 'Net margin', format: 'pct', signed: true, key: true },
  { line: 'fcfMargin', label: 'Free cash flow margin', format: 'pct', signed: true },
  { line: 'effectiveTaxRate', label: 'Effective tax rate', format: 'pct' },
  {
    line: 'returnOnEquity',
    label: 'Return on equity',
    format: 'pct',
    signed: true,
    key: true,
    hint: 'Net income over closing shareholders’ equity for the same period.',
  },
];

const BALANCE: Row[] = [
  { line: 'cash', label: 'Cash & equivalents', format: 'money', key: true },
  { line: 'totalDebt', label: 'Total debt', format: 'money', key: true },
  { line: 'netDebt', label: 'Net debt', format: 'money', tone: 'total', key: true },
  { line: 'currentAssets', label: 'Current assets', format: 'money' },
  { line: 'currentLiabilities', label: 'Current liabilities', format: 'money' },
  { line: 'workingCapital', label: 'Working capital', format: 'money', signed: true },
  { line: 'totalAssets', label: 'Total assets', format: 'money', tone: 'total', key: true },
  { line: 'totalLiabilities', label: 'Total liabilities', format: 'money' },
  { line: 'equity', label: 'Shareholders’ equity', format: 'money', tone: 'total', key: true },
  {
    line: 'netDebtToEbitda',
    label: 'Net debt / EBITDA',
    format: 'times',
    key: true,
    hint: 'Years of EBITDA it would take to clear the net debt.',
  },
  { line: 'debtToEquity', label: 'Debt / equity', format: 'times' },
  { line: 'currentRatio', label: 'Current ratio', format: 'times' },
];

const CASHFLOW: Row[] = [
  {
    line: 'operatingCashFlow',
    label: 'Operating cash flow',
    format: 'money',
    signed: true,
    key: true,
  },
  { line: 'capitalExpenditure', label: 'Capital expenditure', format: 'money', key: true },
  {
    line: 'freeCashFlow',
    label: 'Free cash flow',
    format: 'money',
    tone: 'total',
    signed: true,
    key: true,
  },
  { line: 'dividendsPaid', label: 'Dividends paid', format: 'money' },
  { line: 'buybacks', label: 'Share repurchases', format: 'money' },
  { line: 'investingCashFlow', label: 'Investing cash flow', format: 'money', signed: true },
  { line: 'financingCashFlow', label: 'Financing cash flow', format: 'money', signed: true },
];

const CADENCE_LABEL: Record<Cadence, string> = { annual: 'Annual', quarterly: 'Quarterly' };

/**
 * One company in depth: what the market pays for it, and what it earns.
 *
 * The price chart and the statements are deliberately adjacent — a multiple is
 * the ratio between them, and reading either alone is how a cheap company and a
 * shrinking one get confused. For an indexed issuer, the filed figures sit
 * below in their own panel rather than merged into these tables: they come from
 * a different source on a different basis, and blending them would hide that.
 */
export default function CompanyDetail({
  symbol,
  onBack,
  onOpen,
}: {
  symbol: string;
  onBack: () => void;
  onOpen: (symbol: string) => void;
}) {
  const [company, setCompany] = useState<Company | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [range, setRange] = useState<PriceWindow>('5Y');
  const [history, setHistory] = useState<History | null>(null);
  const [cadence, setCadence] = useState<Cadence>('annual');
  // All three from the start: revenue alone says how big a company is, and the
  // steps down to gross profit and to what is finally kept are the whole
  // question of whether that matters.
  const [shownSeries, setShownSeries] = useState<Series[]>([...SERIES]);

  /** Toggle one line, never leaving the chart with nothing on it. */
  function toggleSeries(series: Series) {
    setShownSeries((current) =>
      current.includes(series)
        ? current.length > 1
          ? current.filter((item) => item !== series)
          : current
        : SERIES.filter((item) => current.includes(item) || item === series),
    );
  }
  const [revenue, setRevenue] = useState<RevenueHistory | null>(null);
  const [revenueError, setRevenueError] = useState<string | null>(null);
  // Opens on everything: the whole point of reading the filings is the run of
  // history behind them, and a reader can always narrow it.
  const [span, setSpan] = useState<number | null>(null);
  const [shown, setShown] = useState<Cadence>('quarterly');
  // Null means the listing's own trading currency, which is what a price is
  // quoted in and therefore the honest default.
  const [unit, setUnit] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setCompany(null);
    fetchCompany(symbol, unit ?? undefined, controller.signal)
      .then(setCompany)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [symbol, unit]);

  // A different company has a different native currency, so a unit chosen for
  // the last one should not follow the reader onto this one.
  useEffect(() => setUnit(null), [symbol]);

  useEffect(() => {
    const controller = new AbortController();
    fetchHistory([symbol], range, controller.signal)
      .then(setHistory)
      .catch(() => setHistory(null));
    return () => controller.abort();
  }, [symbol, range]);

  useEffect(() => {
    const controller = new AbortController();
    setRevenue(null);
    setRevenueError(null);
    setSpan(null);
    fetchRevenue(symbol, controller.signal)
      .then((history) => {
        setRevenue(history);
        // Open on whichever cadence covers the most ground for this filer.
        setShown(history.default);
        // And only on the lines it actually reports — a bank publishes no gross
        // profit, and a legend entry reading "—" is not information.
        const points = history[history.default].points;
        const carried = SERIES.filter((series) =>
          points.some((point) => point[series] !== null && point[series] !== undefined),
        );
        setShownSeries(carried.length > 0 ? carried : [...SERIES]);
      })
      .catch((err: Error) => {
        // A request that did not come back says nothing about the company. It
        // used to fall into the same empty state as a listing that files
        // nothing, which reported a stale API as "Apple does not file
        // statements" — a transport failure dressed up as a finding.
        if (err.name === 'AbortError') return;
        setRevenueError(err.message);
        setRevenue(EMPTY_REVENUE);
      });
    return () => controller.abort();
  }, [symbol]);

  const line = history?.series[0] ?? null;
  const colours = useMemo(
    () => ({ [symbol]: (line?.totalReturn ?? 0) >= 0 ? 'var(--up)' : 'var(--down)' }),
    [symbol, line],
  );

  if (loading && !company) return <p className="stock__error">Opening {symbol}…</p>;
  if (error) return <p className="stock__error">Could not open {symbol} — {error}</p>;
  if (!company) return null;

  const { profile, kpis, money: unitInfo, statements, warehouse, sectors, peers } = company;
  const periods = statements[cadence];
  const reported = profile.reportingCurrency || profile.currency;
  // One unit for the whole page: KPIs, statements and the chart all arrive
  // already converted, so nothing here has to be labelled twice.
  const shownCcy = unitInfo?.displayCurrency || profile.currency;
  const dayMove =
    kpis.price !== null && kpis.previousClose ? kpis.price / kpis.previousClose - 1 : null;

  const series = revenue?.[shown] ?? { points: [], source: '', derived: 0 };
  const revenuePoints = series.points;
  const revenueCurrency = revenue?.currency || reported;
  const latest = revenuePoints.length
    ? Date.parse(revenuePoints[revenuePoints.length - 1].end)
    : null;

  /** Points inside a window measured back from the most recent period. */
  const within = (years: number | null) => {
    if (years === null || latest === null) return revenuePoints;
    const cutoff = latest - years * 365.25 * 24 * 3600 * 1000;
    return revenuePoints.filter((point) => Date.parse(point.end) >= cutoff);
  };
  // A window is only offered when it actually narrows the series. On a listing
  // with five quarters to its name, 3Y, 5Y and 10Y all redraw the same chart,
  // and three buttons that do nothing read as broken controls.
  const hasHistory = (years: number | null) =>
    years === null
      ? revenuePoints.length >= 2
      : within(years).length >= 2 && within(years).length < revenuePoints.length;
  const windowed = within(span);

  // Where the price sits in its own year, as a fraction of the 52-week band.
  const band =
    kpis.high52 !== null && kpis.low52 !== null && kpis.price !== null && kpis.high52 > kpis.low52
      ? (kpis.price - kpis.low52) / (kpis.high52 - kpis.low52)
      : null;

  const kpi = (label: string, value: string, hint?: string) => (
    <div className="co__kpi" key={label} title={hint}>
      <span className="eyebrow">{label}</span>
      <span className="co__kpi-value num">{value}</span>
    </div>
  );

  return (
    <div className={`co co--detail${loading ? ' is-loading' : ''}`}>
      <div className="sectors__bar">
        <button type="button" className="sectors__back" onClick={onBack}>
          &larr; All companies
        </button>
        <div className="stock__switch" role="group" aria-label="Period">
          {PERIODS.map((option) => (
            <button
              key={option}
              type="button"
              className={range === option ? 'is-on' : ''}
              onClick={() => setRange(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <header className="co__head">
        <div className="co__ident">
          <p className="eyebrow">
            <span className="num">{symbol}</span>
            {profile.exchange && ` · ${profile.exchange}`}
            {profile.currency && ` · ${profile.currency}`}
          </p>
          <h2 className="co__name">{profile.name}</h2>
          <p className="co__meta">
            {[profile.sector, profile.industry, profile.country].filter(Boolean).join(' · ')}
            {profile.employees ? ` · ${plain(profile.employees, 0)} employees` : ''}
          </p>
        </div>
        <div className="co__last">
          <span className="co__price num">{plain(kpis.price)}</span>
          <span className={`co__daymove num ${dayMove === null ? '' : dayMove >= 0 ? 'up' : 'down'}`}>
            {pct(dayMove, 2, true)} today
          </span>
          {profile.inWarehouse && (
            <span className="co__held" title="This issuer is indexed — its filings are modelled in the warehouse">
              In the warehouse
            </span>
          )}
        </div>
      </header>

      {unitInfo?.options?.length > 0 && (
        <div className="co__unit" role="group" aria-label="Display currency">
          <span className="eyebrow">Shown in</span>
          {unitInfo.options.map((code) => (
            <button
              key={code}
              type="button"
              className={code === shownCcy ? 'is-on' : ''}
              onClick={() => setUnit(code === unitInfo.tradingCurrency ? null : code)}
            >
              {code}
              {code === unitInfo.tradingCurrency && <em>traded</em>}
              {code === unitInfo.reportingCurrency &&
                code !== unitInfo.tradingCurrency && <em>reported</em>}
            </button>
          ))}
        </div>
      )}

      <section className="co__kpis" aria-label="Valuation and market data">
        {kpi('Market cap', money(kpis.marketCap, shownCcy))}
        {kpi(
          'Enterprise value',
          money(kpis.enterpriseValue, shownCcy),
          'Market cap plus net debt, rebuilt in one currency rather than across two.',
        )}
        {kpi('P / E', times(kpis.trailingPe), 'Trailing twelve months')}
        {kpi('Forward P / E', times(kpis.forwardPe), 'On consensus forward earnings')}
        {kpi('P / B', times(kpis.priceToBook))}
        {kpi('P / S', times(kpis.priceToSales))}
        {kpi('EV / EBITDA', times(kpis.evToEbitda))}
        {kpi('Dividend yield', pct(kpis.dividendYield, 2))}
        {kpi('Payout ratio', pct(kpis.payoutRatio, 0))}
        {kpi('Beta', plain(kpis.beta), 'Sensitivity to the wider market')}
        {kpi('EPS', plain(kpis.eps))}
        {kpi('Shares out', money(kpis.sharesOutstanding))}
        <div className="co__kpi co__kpi--band">
          <span className="eyebrow">52-week range</span>
          <span className="co__kpi-value num">
            {plain(kpis.low52)} — {plain(kpis.high52)}
          </span>
          {band !== null && (
            <span className="co__band" aria-hidden="true">
              <i className="co__band-mark" style={{ left: `${Math.min(100, band * 100)}%` }} />
            </span>
          )}
        </div>
      </section>

      {kpis.mixedCurrency && (
        <p className="co__caveat">
          This listing trades in <span className="num">{unitInfo.tradingCurrency}</span> and reports
          in <span className="num">{unitInfo.reportingCurrency}</span>. Yahoo publishes
          price-to-book, price-to-sales and EV/EBITDA straight across those two without converting,
          which inflates them by the exchange rate — so they are recomputed here from the
          underlying figures with both sides in{' '}
          <span className="num">{shownCcy}</span>. A ratio does not depend on the unit once its two
          halves agree, so switching the currency above moves the levels and leaves the multiples
          where they are.
          {unitInfo.incomplete &&
            ' One of the rates needed was unavailable, so the figures that depend on it are blank rather than unconverted.'}
        </p>
      )}

      {line && history && (
        <>
          <div className="stock__chart">
            <PriceChart
              dates={history.dates}
              series={history.series}
              colours={colours}
              scale="price"
              intraday={history.intraday}
            />
          </div>
          <p className="co__stats">
            <span>
              <b className="eyebrow">Total return</b>
              <i className={`num ${line.totalReturn >= 0 ? 'up' : 'down'}`}>
                {pct(line.totalReturn, 1, true)}
              </i>
            </span>
            <span>
              <b className="eyebrow">CAGR</b>
              <i className="num">{pct(line.cagr, 1, true)}</i>
            </span>
            <span>
              <b className="eyebrow">Ann. vol</b>
              <i className="num">{pct(line.annualisedVol)}</i>
            </span>
            <span>
              <b className="eyebrow">Max drawdown</b>
              <i className="num down">{pct(line.maxDrawdown)}</i>
            </span>
            <span>
              <b className="eyebrow">Window</b>
              <i className="num">{history.start ?? '—'}</i>
            </span>
          </p>
        </>
      )}

      <section className="co__revenue" aria-label="Revenue history">
        <div className="sectors__bar">
          <p className="eyebrow">
            Revenue — {shown === 'annual' ? 'annual' : 'quarterly'}
            {revenueCurrency && (
              <>
                {' '}
                in <span className="num">{revenueCurrency}</span>
              </>
            )}
          </p>
          <div className="co__chartbar">
            {/* Offered whenever both exist: a US filer reads best quarterly, a
                20-F filer has twenty annual years and no quarters at all. */}
            <div className="stock__switch" role="group" aria-label="Revenue cadence">
              {CADENCES.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={shown === option ? 'is-on' : ''}
                  onClick={() => setShown(option)}
                  disabled={(revenue?.[option].points.length ?? 0) < 2}
                >
                  {CADENCE_LABEL[option]}
                </button>
              ))}
            </div>
            {/* Independent, unlike the other switches here: these are lines to
                lay over each other, not one choice among several. The last one
                showing cannot be turned off — an empty chart is not a view. */}
            <div className="stock__switch" role="group" aria-label="Series">
              {SERIES.map((series) => {
                const on = shownSeries.includes(series);
                // A filer that never reports a line gets no button for it —
                // a bank publishes no gross profit at all.
                const available = windowed.some(
                  (point) => point[series] !== null && point[series] !== undefined,
                );
                if (!available) return null;
                return (
                  <button
                    key={series}
                    type="button"
                    className={on ? 'is-on' : ''}
                    aria-pressed={on}
                    onClick={() => toggleSeries(series)}
                    disabled={on && shownSeries.length === 1}
                  >
                    {SERIES_LABEL[series]}
                  </button>
                );
              })}
            </div>
            <div className="stock__switch" role="group" aria-label="Revenue window">
              {REVENUE_WINDOWS.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  className={span === option.years ? 'is-on' : ''}
                  onClick={() => setSpan(option.years)}
                  disabled={!hasHistory(option.years)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {revenue === null && <p className="stock__warn">Reading the filings…</p>}
        {revenueError && (
          <p className="stock__error">
            Could not load revenue — {revenueError}. If the hub is running against an older market
            API, restart it: the Python half does not reload with the page.
          </p>
        )}
        {!revenueError && revenue !== null && !revenue.files && (
          <p className="stock__warn">
            {profile.name} does not file financial statements — an index, a fund or a currency has
            no revenue to report.
          </p>
        )}
        {revenue !== null && revenue.files && windowed.length < 2 && (
          <p className="stock__warn">
            No {shown} figures for this listing. Try the other cadence.
          </p>
        )}

        {windowed.length >= 2 && (
          <>
            <RevenueChart
              points={windowed}
              currency={revenueCurrency}
              shownSeries={shownSeries}
              lag={shown === 'annual' ? 1 : 4}
            />
            <p className="stock__footnote">
              {series.points.length} {shown} periods from {series.source}
              {series.points[0] && `, back to ${series.points[0].label}`}.
              {series.derived > 0 &&
                ` ${series.derived} fourth quarters are derived — a 10-K filer publishes three
                  quarters and an annual report, so the missing one is the year less the three.`}
              {revenue && !revenue.edgar && (
                <>
                  {' '}
                  <b className="co__flag">
                    SEC EDGAR is not configured, so this is capped at what the quote feed
                    publishes. Set <code>SEC_EDGAR_USER_AGENT</code> in <code>.env</code> and
                    restart the hub for the full filing history.
                  </b>
                </>
              )}
            </p>
          </>
        )}
      </section>

      <section className="co__financials" aria-label="Financial statements">
        <div className="sectors__bar">
          <p className="eyebrow">
            Statements — reported in <span className="num">{reported || 'n/a'}</span>
          </p>
          <div className="stock__switch" role="group" aria-label="Cadence">
            {CADENCES.map((option) => (
              <button
                key={option}
                type="button"
                className={cadence === option ? 'is-on' : ''}
                onClick={() => setCadence(option)}
              >
                {CADENCE_LABEL[option]}
              </button>
            ))}
          </div>
        </div>

        {periods.length === 0 ? (
          <p className="stock__warn">
            No {CADENCE_LABEL[cadence].toLowerCase()} statements published for this listing.
          </p>
        ) : (
          <>
            <StatementTable
              caption="Income statement"
              periods={periods}
              rows={INCOME}
              currency={reported}
            />
            <StatementTable
              caption="Margins & returns"
              periods={periods}
              rows={MARGINS}
              currency=""
            />
            <StatementTable
              caption="Balance sheet"
              periods={periods}
              rows={BALANCE}
              currency={reported}
            />
            <StatementTable
              caption="Cash flow"
              periods={periods}
              rows={CASHFLOW}
              currency={reported}
            />
          </>
        )}
      </section>

      {warehouse.held ? (
        <FiledPanel filed={warehouse} />
      ) : (
        <BackfillPanel symbol={symbol} name={profile.name} />
      )}

      {(sectors.length > 0 || peers.length > 0) && (
        <section className="co__peers" aria-label="Related names">
          <p className="eyebrow">
            {sectors.length > 0
              ? `Also in ${sectors.map((s) => s.name).join(', ')}`
              : 'Related names'}
          </p>
          <div className="sectors__news-rule" />
          <div className="co__peerlist">
            {peers.map((peer) => (
              <button
                key={peer.symbol}
                type="button"
                className="co__peer"
                onClick={() => onOpen(peer.symbol)}
              >
                <span className="num">{peer.symbol}</span>
                <span>{peer.name}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="co__news" aria-label="Company coverage">
        <p className="eyebrow">Coverage</p>
        <div className="sectors__news-rule" />
        <NewsFeed source={{ symbol }} empty="No recent coverage for this company." />
      </section>

      <p className="stock__footnote">
        Prices are split- and dividend-adjusted. Every amount on this page is shown in{' '}
        <span className="num">{shownCcy}</span>
        {unitInfo?.converted
          ? ` — converted at the spot rate from ${unitInfo.tradingCurrency}${
              unitInfo.reportingCurrency !== unitInfo.tradingCurrency
                ? ` for market figures and ${unitInfo.reportingCurrency} for filed ones`
                : ''
            }`
          : ', the currency the issuer both trades and reports in'}
        . Amounts are shown to three significant figures. Nothing here is investment advice.
      </p>
    </div>
  );
}
