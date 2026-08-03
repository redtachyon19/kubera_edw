import { useCallback, useEffect, useState } from 'react';

import { PERIODS } from '../stock/api';
import type { Period } from '../stock/api';
import CorrelationMatrix from './CorrelationMatrix';
import SectorNews from './SectorNews';
import Sparkline from './Sparkline';
import { fetchSector, fetchSectors } from './sectorApi';
import type { Pair, SectorCard, SectorDetail } from './sectorApi';
import './Sectors.css';

const pct = (v: number | null, digits = 1) =>
  v === null || !isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`;

const sign = (v: number | null) => (v === null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');

/**
 * Browse the market by industry, then by what actually moves together.
 *
 * Two levels: a grid of sectors ranked by performance, and a sector view with
 * its constituents, the pairs that travel closest, and the full correlation
 * grid. Any of it can be pushed into the Explorer to chart.
 */
export default function Sectors({ onCompare }: { onCompare?: (symbols: string[]) => void }) {
  const [period, setPeriod] = useState<Period>('1Y');
  const [cards, setCards] = useState<SectorCard[]>([]);
  const [openSlug, setOpenSlug] = useState<string | null>(null);
  const [detail, setDetail] = useState<SectorDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchSectors(period, controller.signal)
      .then(setCards)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [period]);

  useEffect(() => {
    if (!openSlug) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    fetchSector(openSlug, period, controller.signal)
      .then(setDetail)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [openSlug, period]);

  const ranked = [...cards].sort(
    (a, b) => (b.averageReturn ?? -Infinity) - (a.averageReturn ?? -Infinity),
  );

  const compare = useCallback(
    (symbols: string[]) => onCompare?.(symbols),
    [onCompare],
  );

  const periodBar = (
    <div className="stock__switch" role="group" aria-label="Period">
      {PERIODS.filter((p) => p !== '1D' && p !== '1W').map((option) => (
        <button
          key={option}
          type="button"
          className={period === option ? 'is-on' : ''}
          onClick={() => setPeriod(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );

  // ── Sector detail ──────────────────────────────────────────────────────────
  if (openSlug && detail) {
    const strongest = detail.pairs.slice(0, 5);
    const loosest = [...detail.pairs].slice(-5).reverse();

    // Headline, the downside reading, and how far the pair actually roams — the
    // range is often the part that changes what you would conclude.
    const pairRow = (p: Pair) => (
      <li key={`${p.a}-${p.b}`}>
        <button type="button" onClick={() => compare([p.a, p.b])}>
          <span className="sectors__pairname num">
            {p.a} ~ {p.b}
          </span>
          {p.rolling && <Sparkline series={p.rolling.series} />}
          <span className="sectors__pairstats">
            <b className={`num ${sign(p.correlation)}`}>{p.correlation.toFixed(2)}</b>
            {p.downside !== null && (
              <i className="num" title="On days the sector fell">
                ↓{p.downside.toFixed(2)}
              </i>
            )}
            {p.rolling && (
              <i className="num" title={`Rolling ${p.rolling.window}-day range`}>
                {p.rolling.min.toFixed(2)}–{p.rolling.max.toFixed(2)}
              </i>
            )}
          </span>
        </button>
      </li>
    );

    return (
      <div className={`sectors${loading ? ' is-loading' : ''}`}>
        <div className="sectors__bar">
          <button type="button" className="sectors__back" onClick={() => setOpenSlug(null)}>
            &larr; All sectors
          </button>
          {periodBar}
        </div>

        <header className="sectors__head">
          <h2 className="sectors__title">{detail.name}</h2>
          <p className="sectors__blurb">{detail.blurb}</p>
          <button
            type="button"
            className="sectors__cta"
            onClick={() => compare(detail.constituents.map((c) => c.symbol))}
          >
            Chart all {detail.constituents.length} in Explorer &rarr;
          </button>
        </header>

        {detail.missing.length > 0 && (
          <p className="stock__warn">No data for {detail.missing.join(', ')}.</p>
        )}

        <table className="stock__table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Ccy</th>
              <th className="ta-r">Last</th>
              <th className="ta-r">Return</th>
              <th className="ta-r">Ann. vol</th>
              <th className="ta-r" title="Sensitivity to the equal-weighted sector basket">
                Beta
              </th>
              <th className="ta-r" title="Share of the name's variance the basket explains">
                R²
              </th>
              <th className="ta-r">Max drawdown</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {detail.constituents.map((row) => (
              <tr key={row.symbol}>
                <td className="num">{row.symbol}</td>
                <td className="num">{row.currency || '—'}</td>
                <td className="num ta-r">{row.last.toFixed(2)}</td>
                <td className={`num ta-r ${sign(row.periodReturn)}`}>{pct(row.periodReturn)}</td>
                <td className="num ta-r">
                  {row.annualisedVol === null ? '—' : pct(row.annualisedVol).replace('+', '')}
                </td>
                <td className="num ta-r">{row.beta === null ? '—' : row.beta.toFixed(2)}</td>
                <td className="num ta-r">{row.r2 === null ? '—' : row.r2.toFixed(2)}</td>
                <td className="num ta-r down">{pct(row.maxDrawdown)}</td>
                <td className="ta-r">
                  <button
                    type="button"
                    className="sectors__mini"
                    onClick={() => compare([row.symbol])}
                  >
                    Chart
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="sectors__pairs">
          <div>
            <p className="eyebrow">Travel together</p>
            <ul className="sectors__pairlist">{strongest.map(pairRow)}</ul>
          </div>
          <div>
            <p className="eyebrow">Least related</p>
            <ul className="sectors__pairlist">{loosest.map(pairRow)}</ul>
          </div>
        </div>

        <CorrelationMatrix
          labels={detail.labels}
          matrices={detail.matrices}
          onPick={(a, b) => compare([a, b])}
        />

        <section className="sectors__news" aria-label="Sector coverage">
          <p className="eyebrow">Coverage</p>
          <div className="sectors__news-rule" />
          <SectorNews slug={detail.slug} />
        </section>

        <p className="stock__footnote">
          {detail.observations} daily observations, {detail.downDays} of them down days for the
          sector. Beta and R² are measured against the equal-weighted basket of these names.
        </p>
      </div>
    );
  }

  // ── Sector grid ────────────────────────────────────────────────────────────
  return (
    <div className={`sectors${loading ? ' is-loading' : ''}`}>
      <div className="sectors__bar">
        <p className="sectors__lead">
          {cards.length} sectors, ranked by equal-weighted return over the window.
        </p>
        {periodBar}
      </div>

      {error && <p className="stock__error">Could not load sectors — {error}</p>}
      {!error && cards.length === 0 && <p className="stock__error">Loading sectors…</p>}

      <div className="sectors__grid">
        {ranked.map((card) => (
          <button
            key={card.slug}
            type="button"
            className="sector-card"
            onClick={() => setOpenSlug(card.slug)}
          >
            <span className="sector-card__name">{card.name}</span>
            <span className={`sector-card__return num ${sign(card.averageReturn)}`}>
              {pct(card.averageReturn)}
            </span>
            <span className="sector-card__blurb">{card.blurb}</span>
            <span className="sector-card__foot">
              <span>
                {card.best && (
                  <>
                    <b className="num">{card.best.symbol}</b>{' '}
                    <i className={`num ${sign(card.best.return)}`}>{pct(card.best.return, 0)}</i>
                  </>
                )}
              </span>
              <span>
                {card.worst && (
                  <>
                    <b className="num">{card.worst.symbol}</b>{' '}
                    <i className={`num ${sign(card.worst.return)}`}>{pct(card.worst.return, 0)}</i>
                  </>
                )}
              </span>
              <span className="sector-card__count num">{card.priced}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
