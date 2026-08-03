import { useEffect, useState } from 'react';

import type { TapeEntry } from '../../config/dashboards';
import './Ticker.css';

interface Quote {
  symbol: string;
  price: number;
  previousClose: number;
  change: number;
  changePct: number;
  currency: string;
}

const REFRESH_MS = 45_000;

function format(entry: TapeEntry, quote: Quote): { price: string; move: string } {
  if (entry.format === 'rate') {
    // A yield is a level, so its move belongs in percentage points — reporting a
    // 4.66 -> 4.74 move as "+1.76%" would read as the market rising 1.76%.
    const pp = quote.price - quote.previousClose;
    return {
      price: `${quote.price.toFixed(2)}%`,
      move: `${pp >= 0 ? '+' : ''}${pp.toFixed(2)}pp`,
    };
  }
  const decimals = quote.price < 10 ? 4 : quote.price < 1000 ? 2 : 0;
  return {
    price: quote.price.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }),
    move: `${quote.changePct >= 0 ? '+' : ''}${(quote.changePct * 100).toFixed(2)}%`,
  };
}

/**
 * The live tape. Only the Markets desk mounts it — a scrolling quote strip over
 * annual filings or a dbt test list would be noise.
 *
 * The marquee is duplicated once and translated by exactly half its width, which
 * is what makes the loop seamless. Motion stops on hover so a figure can be
 * read, and is dropped entirely for readers who ask for reduced motion.
 */
export default function Ticker({ entries }: { entries: TapeEntry[] }) {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (entries.length === 0) return undefined;
    const symbols = entries.map((entry) => entry.symbol).join(',');
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(`/api/market/quotes?symbols=${encodeURIComponent(symbols)}`);
        const body = await response.json();
        if (cancelled) return;
        const next: Record<string, Quote> = {};
        for (const quote of body.quotes ?? []) next[quote.symbol] = quote;
        setQuotes(next);
        setFailed(Object.keys(next).length === 0);
      } catch {
        if (!cancelled) setFailed(true);
      }
    }

    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [entries]);

  const priced = entries.filter((entry) => quotes[entry.symbol]);
  if (failed && priced.length === 0) {
    return (
      <div className="tape tape--down">
        <span className="tape__note">Live quotes unavailable</span>
      </div>
    );
  }
  if (priced.length === 0) {
    return (
      <div className="tape">
        <span className="tape__note">Loading quotes…</span>
      </div>
    );
  }

  const run = priced.map((entry) => {
    const quote = quotes[entry.symbol];
    const { price, move } = format(entry, quote);
    const direction = quote.changePct > 0 ? 'up' : quote.changePct < 0 ? 'down' : '';
    return (
      <span className="tape__item" key={entry.symbol}>
        <span className="tape__label">{entry.label}</span>
        <span className="tape__price num">{price}</span>
        <span className={`tape__move num ${direction}`}>{move}</span>
      </span>
    );
  });

  return (
    <div className="tape" aria-label="Live market quotes">
      <div className="tape__track">
        <div className="tape__run">{run}</div>
        <div className="tape__run" aria-hidden="true">
          {run}
        </div>
      </div>
    </div>
  );
}
