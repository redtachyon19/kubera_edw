import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import Select from '../../components/Select';
import { PERIODS, searchSymbols } from '../stock/api';
import type { Period, SearchResult } from '../stock/api';
import CompanyDetail from './CompanyDetail';
import { direction, fetchCompanies, pct, plain } from './companyApi';
import type { CompanyCard } from './companyApi';
import './Companies.css';

const SORTS = [
  { id: 'return', label: 'Return' },
  { id: 'name', label: 'Name' },
  { id: 'symbol', label: 'Ticker' },
] as const;
type Sort = (typeof SORTS)[number]['id'];

const ALL_SECTORS = 'All sectors';
const HELD_ONLY = 'In the book';

/**
 * Browse the universe, then open one name in full.
 *
 * The grid is the ~300 listings the hub carries names for — every sector
 * constituent plus the 38 the warehouse holds filings for — but the search box
 * is not limited to them: a ticker it does not recognise is looked up live and
 * opens the same detail page, because a desk should not refuse a company on the
 * grounds that a JSON file has not heard of it.
 *
 * The open company lives in the URL, so a detail page can be linked to and the
 * back button behaves the way a reader expects.
 */
export default function Companies() {
  const [params, setParams] = useSearchParams();
  const open = params.get('company');

  const [period, setPeriod] = useState<Period>('1Y');
  const [cards, setCards] = useState<CompanyCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState('');
  const [remote, setRemote] = useState<SearchResult[]>([]);
  const boxRef = useRef<HTMLDivElement>(null);

  const [sector, setSector] = useState(ALL_SECTORS);
  const [sort, setSort] = useState<Sort>('return');

  const show = useCallback(
    (symbol: string | null) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (symbol) next.set('company', symbol);
          else next.delete('company');
          return next;
        },
        { replace: false },
      );
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [setParams],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchCompanies(period, controller.signal)
      .then(setCards)
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [period]);

  // Anything the grid cannot match is looked up live, so the box opens any
  // listing rather than only the ones already in the universe.
  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setRemote([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchSymbols(term, controller.signal)
        .then(setRemote)
        .catch(() => setRemote([]));
    }, 280);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setRemote([]);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const sectorNames = useMemo(() => {
    const names = new Set(cards.map((card) => card.sector).filter(Boolean));
    return [ALL_SECTORS, HELD_ONLY, ...[...names].sort()];
  }, [cards]);

  const shown = useMemo(() => {
    const term = query.trim().toLowerCase();
    const filtered = cards.filter((card) => {
      if (sector === HELD_ONLY && !card.warehouse) return false;
      if (sector !== ALL_SECTORS && sector !== HELD_ONLY && card.sector !== sector) return false;
      if (!term) return true;
      return (
        card.symbol.toLowerCase().includes(term) ||
        card.name.toLowerCase().includes(term) ||
        card.industry.toLowerCase().includes(term)
      );
    });
    return filtered.sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name);
      if (sort === 'symbol') return a.symbol.localeCompare(b.symbol);
      return (b.periodReturn ?? -Infinity) - (a.periodReturn ?? -Infinity);
    });
  }, [cards, query, sector, sort]);

  // Live matches worth offering: only what the grid did not already find.
  const known = useMemo(() => new Set(cards.map((card) => card.symbol)), [cards]);
  const extra = remote.filter((result) => !known.has(result.symbol)).slice(0, 5);

  if (open) {
    return <CompanyDetail symbol={open} onBack={() => show(null)} onOpen={show} />;
  }

  return (
    <div className={`co${loading ? ' is-loading' : ''}`}>
      <section className="stock__controls">
        <div className="stock__search" ref={boxRef}>
          <label className="eyebrow" htmlFor="company-search">
            Find a company
          </label>
          <input
            id="company-search"
            className="stock__input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name, ticker or industry — toyota, TM, semiconductors"
            autoComplete="off"
          />
          {extra.length > 0 && (
            <ul className="stock__results">
              <li className="stock__result stock__result--note">Not in the universe — open live</li>
              {extra.map((result) => (
                <li key={result.symbol}>
                  <button type="button" className="stock__result" onClick={() => show(result.symbol)}>
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

        <div className="stock__switches">
          <Select label="Sector" value={sector} options={sectorNames} onChange={setSector} />

          <div className="stock__switch" role="group" aria-label="Sort by">
            {SORTS.map((option) => (
              <button
                key={option.id}
                type="button"
                className={sort === option.id ? 'is-on' : ''}
                onClick={() => setSort(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="stock__switch" role="group" aria-label="Period">
            {PERIODS.filter((option) => option !== '1D' && option !== '1W').map((option) => (
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
        </div>
      </section>

      {error && <p className="stock__error">Could not load the universe — {error}</p>}
      {!error && cards.length === 0 && <p className="stock__error">Loading companies…</p>}

      {cards.length > 0 && (
        <p className="sectors__lead">
          {shown.length === cards.length
            ? `${cards.length} companies, ranked by return over the window.`
            : `${shown.length} of ${cards.length} companies.`}{' '}
          {shown.length === 0 && 'Nothing matches — try the live lookup above.'}
        </p>
      )}

      <div className="co__grid">
        {shown.map((card) => (
          <button
            key={card.symbol}
            type="button"
            className="company-card"
            onClick={() => show(card.symbol)}
            title={`${card.name} — ${card.industry || card.sector}`}
          >
            <span className="company-card__symbol num">{card.symbol}</span>
            <span className={`company-card__return num ${direction(card.periodReturn)}`}>
              {pct(card.periodReturn, 1, true)}
            </span>
            <span className="company-card__name">{card.name}</span>
            <span className="company-card__foot">
              <span className="company-card__sector">{card.sector || card.country || '—'}</span>
              <span className="company-card__last num">
                {card.last === null ? '—' : `${plain(card.last)} ${card.currency}`}
              </span>
              {card.warehouse && (
                <i className="company-card__held" title="Kubera holds this name">
                  ●
                </i>
              )}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
