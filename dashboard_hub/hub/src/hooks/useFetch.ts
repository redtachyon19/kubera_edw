import { useEffect, useRef, useState } from 'react';

export interface Fetched<T> {
  data: T | null;
  loading: boolean;
  /** The failure message, or null. Aborts never appear here. */
  error: string | null;
}

interface Options {
  /** Skip the request entirely — for a view that is not on screen. */
  skip?: boolean;
  /**
   * Keep the last result visible while the next one loads. Off by default,
   * because showing a company's figures under a different company's name is
   * worse than showing nothing.
   */
  keepPrevious?: boolean;
}

/**
 * Fetch on a dependency change, abort on the way out.
 *
 * Every page here was writing the same fifteen lines: make an `AbortController`,
 * raise a loading flag, call, set the data, catch, re-check `err.name` against
 * `'AbortError'`, lower the flag, and return the abort. It appeared fifteen
 * times across eight files, and the `AbortError` guard eleven times — which is
 * eleven chances to forget it and set state on an unmounted component.
 *
 * The guard is the reason this is a hook rather than a convention. Aborting a
 * request rejects its promise, so a view that is navigated away from mid-flight
 * lands in the `catch` like any other failure. Without the check it renders an
 * error for a request nobody was waiting for; with it, an abort is silence.
 *
 * `run` receives the signal and may do anything with it — a single call, or a
 * `Promise.all` of several, which is how a view that needs two endpoints at once
 * still gets one loading flag and one error.
 *
 * The callback is deliberately **not** a dependency. Callers pass an inline
 * arrow, which is a new function on every render, so keying the effect on it
 * would refetch forever. It is held in a ref and read at call time; `deps` is
 * what decides when to run, exactly as it would in the hand-written effect.
 */
export function useFetch<T>(
  run: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  { skip = false, keepPrevious = false }: Options = {},
): Fetched<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!skip);
  const [error, setError] = useState<string | null>(null);

  const latest = useRef(run);
  latest.current = run;

  useEffect(() => {
    if (skip) {
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);
    if (!keepPrevious) setData(null);

    latest
      .current(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((err: Error) => {
        // An abort is not a failure — it is this view being left.
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
    // `run` is intentionally absent; see the note above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, skip, keepPrevious]);

  return { data, loading, error };
}
