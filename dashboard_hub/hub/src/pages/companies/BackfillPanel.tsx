import { useCallback, useEffect, useRef, useState } from 'react';

export interface BackfillRecord {
  ticker: string;
  /** `held` is already in the book; `absent` has never been asked for. */
  status: 'held' | 'absent' | 'queued' | 'running' | 'done' | 'failed' | 'unavailable';
  requestedAt?: string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  error?: string | null;
  note?: string;
}

const POLL_MS = 4000;

async function read(symbol: string, signal?: AbortSignal): Promise<BackfillRecord> {
  const response = await fetch(`/api/market/backfill?symbol=${encodeURIComponent(symbol)}`, {
    signal,
  });
  const body = await response.json();
  if (!response.ok || body.error) throw new Error(body.error ?? `API returned ${response.status}`);
  return body as BackfillRecord;
}

/**
 * Ask for a company to be built into the warehouse.
 *
 * This is the answer to the question every unheld company raises: the page in
 * front of you is drawn live from SEC, so why is this name not in the book?
 * Because the book is a curated file. This queues the work that changes that —
 * resolve the filer, add it to the universe, pull its filings, rebuild — and
 * what comes back is not more history for this page but the company's presence
 * in every cross-sectional view: allocation, FX impact, the macro joins.
 *
 * The build runs elsewhere. This only asks, then watches.
 */
export default function BackfillPanel({ symbol, name }: { symbol: string; name: string }) {
  const [record, setRecord] = useState<BackfillRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(
    (signal?: AbortSignal) =>
      read(symbol, signal)
        .then(setRecord)
        .catch((err: Error) => {
          if (err.name !== 'AbortError') setError(err.message);
        }),
    [symbol],
  );

  useEffect(() => {
    const controller = new AbortController();
    setRecord(null);
    setError(null);
    refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  // Watch only while something is actually in flight.
  useEffect(() => {
    const live = record?.status === 'queued' || record?.status === 'running';
    if (!live) return;
    timer.current = window.setInterval(() => refresh(), POLL_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [record?.status, refresh]);

  async function ask() {
    setAsking(true);
    setError(null);
    try {
      const response = await fetch('/api/market/backfill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      });
      const body = await response.json();
      if (!response.ok || body.error) throw new Error(body.error ?? `API returned ${response.status}`);
      setRecord(body as BackfillRecord);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAsking(false);
    }
  }

  // Held names get the filed panel instead; nothing to offer here.
  if (record?.status === 'held' || record?.status === 'unavailable') return null;

  const status = record?.status ?? 'absent';
  const working = status === 'queued' || status === 'running';

  return (
    <section className="co__backfill" aria-label="Warehouse backfill">
      <div className="sectors__bar">
        <p className="eyebrow">Not in the book</p>
      </div>

      <p className="co__filed-lead">
        Everything above is read live from SEC and Yahoo. {name} is not one of the holdings the
        warehouse carries, so there are no as-filed figures beneath it, and it appears in none of
        the portfolio, FX or macro views. Building it in adds its filings to{' '}
        <code>marts.fact_financials</code>, converted at each period-end rate and covered by the
        same dbt tests as the rest of the book.
      </p>

      {status === 'absent' && (
        <button type="button" className="sectors__cta" onClick={ask} disabled={asking}>
          {asking ? 'Queueing…' : 'Get historical data →'}
        </button>
      )}

      {working && (
        <p className="stock__warn">
          <span className="co__spin" aria-hidden="true" />
          {status === 'queued'
            ? `Queued — starting within a few seconds.`
            : `Building ${symbol}: resolving the filer, pulling its filings and rebuilding the
               marts. A few minutes. This page keeps working while it runs.`}
        </p>
      )}

      {status === 'done' && (
        <p className="stock__warn">
          {symbol} is in the book. Reload to read its filed figures.{' '}
          <button type="button" className="co__inline" onClick={() => window.location.reload()}>
            Reload
          </button>
        </p>
      )}

      {status === 'failed' && (
        <>
          <p className="stock__error">Backfill failed — {record?.error}</p>
          <button type="button" className="sectors__cta" onClick={ask} disabled={asking}>
            Try again
          </button>
        </>
      )}

      {error && <p className="stock__error">{error}</p>}
    </section>
  );
}
