import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { fetchHistory, GOLD_SYMBOL, PERIODS, searchSymbols } from './api';
import type { History, Period, SearchResult, Series } from './api';
import PriceChart from './PriceChart';
import type { Scale } from './PriceChart';
import './StockExplorer.css';

const SCALES: { id: Scale; label: string; hint: string }[] = [
  {
    id: 'price',
    label: 'Price',
    hint: 'Actual close in each listing’s own currency, each series on its own scale.',
  },
  { id: 'rebased', label: 'Rebased %', hint: 'Every series starts at 0%, so they compare.' },
  {
    id: 'growth',
    label: 'Growth of 100',
    hint: 'Log axis — use this over ten years, where one big winner flattens the rest.',
  },
];

const UP_SHADES = ['var(--up)', 'var(--up-2)', 'var(--up-3)'];
const DOWN_SHADES = ['var(--down)', 'var(--down-2)', 'var(--down-3)'];

/** Colour by direction: risers green, fallers red, gold always gold. */
function colourSeries(series: Series[]): Record<string, string> {
  const colours: Record<string, string> = {};
  let up = 0;
  let down = 0;
  for (const item of series) {
    if (item.isGold) {
      colours[item.symbol] = 'var(--gold)';
    } else if (item.totalReturn >= 0) {
      colours[item.symbol] = UP_SHADES[up++ % UP_SHADES.length];
    } else {
      colours[item.symbol] = DOWN_SHADES[down++ % DOWN_SHADES.length];
    }
  }
  return colours;
}

const pct = (value: number | null, digits = 1) =>
  value === null || !isFinite(value) ? '—' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;

const sign = (value: number | null) => (value === null ? '' : value > 0 ? 'up' : value < 0 ? 'down' : '');

export default function StockExplorer() {
  const [symbols, setSymbols] = useState<string[]>(['AAPL', 'MSFT']);
  const [period, setPeriod] = useState<Period>('5Y');
  const [scale, setScale] = useState<Scale>('price');
  const [withGold, setWithGold] = useState(true);

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  const [history, setHistory] = useState<History | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  const wanted = useMemo(
    () => (withGold && !symbols.includes(GOLD_SYMBOL) ? [...symbols, GOLD_SYMBOL] : symbols),
    [symbols, withGold],
  );

  // Debounced lookup — one request per pause in typing, not per keystroke.
  useEffect(() => {
    const term = query.trim();
    if (!term) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const timer = setTimeout(() => {
      searchSymbols(term, controller.signal)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => {
      controller.abort();
      clearTimeout(timer);
      setSearching(false);
    };
  }, [query]);

  useEffect(() => {
    if (wanted.length === 0) {
      setHistory(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchHistory(wanted, period, controller.signal)
      .then(setHistory)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [wanted, period]);

  // Close the results list on an outside click, the way a search field should.
  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setResults([]);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const add = useCallback((symbol: string) => {
    setSymbols((current) => (current.includes(symbol) ? current : [...current, symbol]));
    setQuery('');
    setResults([]);
  }, []);

  const remove = useCallback(
    (symbol: string) => setSymbols((current) => current.filter((s) => s !== symbol)),
    [],
  );

  const series = history?.series ?? [];
  const colours = useMemo(() => colourSeries(series), [series]);

  return (
    <div className="stock">
      <section className="stock__controls">
        <div className="stock__search" ref={boxRef}>
          <label className="eyebrow" htmlFor="stock-search">
            Add a security
          </label>
          <input
            id="stock-search"
            className="stock__input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Company name or ticker — apple, tesla, AAPL, 7203.T, ^GSPC"
            autoComplete="off"
          />
          {query.trim() && (
            <ul className="stock__results">
              {searching && <li className="stock__result stock__result--note">Searching…</li>}
              {!searching && results.length === 0 && (
                <li className="stock__result stock__result--note">
                  No matches — try a ticker directly.
                </li>
              )}
              {results.map((result) => (
                <li key={result.symbol}>
                  <button
                    type="button"
                    className="stock__result"
                    onClick={() => add(result.symbol)}
                    disabled={symbols.includes(result.symbol)}
                  >
                    <span className="stock__result-symbol num">{result.symbol}</span>
                    <span className="stock__result-name">{result.name}</span>
                    <span className="stock__result-meta">
                      {[result.type, result.exchange].filter(Boolean).join(' · ')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="stock__chips">
          {symbols.map((symbol) => (
            <button
              key={symbol}
              type="button"
              className="stock__chip"
              onClick={() => remove(symbol)}
              title={`Remove ${symbol}`}
            >
              <span className="num">{symbol}</span>
              <span aria-hidden="true">×</span>
            </button>
          ))}
          <button
            type="button"
            className={`stock__chip stock__chip--gold${withGold ? ' is-on' : ''}`}
            onClick={() => setWithGold((on) => !on)}
          >
            Gold {withGold ? '×' : '+'}
          </button>
        </div>

        <div className="stock__switches">
          <div className="stock__switch" role="group" aria-label="Period">
            {PERIODS.map((option) => (
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
          <div className="stock__switch" role="group" aria-label="Scale">
            {SCALES.map((option) => (
              <button
                key={option.id}
                type="button"
                title={option.hint}
                className={scale === option.id ? 'is-on' : ''}
                onClick={() => setScale(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error && <p className="stock__error">Could not load prices — {error}</p>}
      {!error && wanted.length === 0 && (
        <p className="stock__error">Nothing selected. Search above, or switch gold back on.</p>
      )}
      {history && history.missing.length > 0 && (
        <p className="stock__warn">No data returned for {history.missing.join(', ')}.</p>
      )}

      {series.length > 0 && (
        <>
          <div className={`stock__chart${loading ? ' is-loading' : ''}`}>
            <PriceChart
              dates={history!.dates}
              series={series}
              colours={colours}
              scale={scale}
              intraday={history!.intraday}
            />
          </div>

          <p className="stock__note">
            Window starts <span className="num">{history!.start}</span> ·{' '}
            <span className="num">{history!.interval}</span> bars
            {history!.intraday && ', times UTC'}
            {history!.limiting && series.length > 1 && (
              <>
                {' '}
                — the earliest date{' '}
                <b>{series.find((s) => s.symbol === history!.limiting)?.label ?? history!.limiting}</b>{' '}
                has data for in this period
              </>
            )}
            . {SCALES.find((s) => s.id === scale)?.hint}
          </p>

          <table className="stock__table">
            <thead>
              <tr>
                <th>Security</th>
                <th>Ccy</th>
                <th className="ta-r">Start</th>
                <th className="ta-r">Last</th>
                <th className="ta-r">Total return</th>
                <th className="ta-r">CAGR</th>
                <th className="ta-r">Ann. vol</th>
                <th className="ta-r">Max drawdown</th>
              </tr>
            </thead>
            <tbody>
              {series.map((row) => (
                <tr key={row.symbol}>
                  <td>
                    <i className="stock__swatch" style={{ background: colours[row.symbol] }} />
                    {row.label}
                  </td>
                  <td className="num">{row.currency || '—'}</td>
                  <td className="num ta-r">{row.startPrice.toFixed(2)}</td>
                  <td className="num ta-r">{row.endPrice.toFixed(2)}</td>
                  <td className={`num ta-r ${sign(row.totalReturn)}`}>{pct(row.totalReturn)}</td>
                  <td className={`num ta-r ${sign(row.cagr)}`}>{pct(row.cagr)}</td>
                  <td className="num ta-r">
                    {row.annualisedVol === null ? '—' : pct(row.annualisedVol).replace('+', '')}
                  </td>
                  <td className="num ta-r down">{pct(row.maxDrawdown)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="stock__footnote">
            Prices are split- and dividend-adjusted. Returns are in each security’s own listing
            currency, so a non-USD listing mixes business performance with the exchange rate.
            CAGR and annualised volatility are left blank on windows too short to annualise
            without misleading — a three-month move is not an annual rate.
          </p>
        </>
      )}

      {loading && series.length === 0 && <p className="stock__error">Fetching prices…</p>}
    </div>
  );
}
