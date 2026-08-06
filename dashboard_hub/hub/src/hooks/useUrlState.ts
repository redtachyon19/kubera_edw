import { useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

interface Options<T extends string> {
  /**
   * Push a history entry rather than replacing the current one. Reserve it for a
   * change that reads as navigation — opening a sector is somewhere you went and
   * expect Back to leave; adding a chip is not, and a basket built one name at a
   * time would otherwise take six Backs to escape.
   */
  push?: boolean;
  /** The values a link is allowed to carry. Anything else falls back. */
  valid?: readonly T[];
}

/**
 * A piece of view state kept in the query string.
 *
 * A desk that holds what you are looking at in component state cannot be sent to
 * anybody: the address bar says `/s/markets` whether you are staring at the
 * default two names or at eleven miners over ten years on a log axis. Reading and
 * writing it here makes the URL the state — copy it, paste it, and the other
 * side opens on the same view.
 *
 * A value equal to the fallback is deleted rather than written, so an untouched
 * desk keeps a clean address and a link only carries what was actually changed.
 */
export function useUrlState<T extends string>(
  key: string,
  fallback: T,
  { push = false, valid }: Options<T> = {},
): [T, (value: T) => void] {
  const [params, setParams] = useSearchParams();

  // A hand-edited or stale link can carry anything; `valid` is what keeps a
  // typo out of the API rather than into it.
  const raw = params.get(key) as T | null;
  const value = raw !== null && (!valid || valid.includes(raw)) ? raw : fallback;

  const latest = useRef({ fallback, push });
  latest.current = { fallback, push };

  const set = useCallback(
    (next: T) => {
      const { fallback: base, push: pushes } = latest.current;
      setParams(
        (current) => {
          const out = new URLSearchParams(current);
          if (next === base) out.delete(key);
          else out.set(key, next);
          return out;
        },
        { replace: !pushes },
      );
    },
    [key, setParams],
  );

  return [value, set];
}

const same = (a: string[], b: string[]) => a.length === b.length && a.every((v, i) => v === b[i]);

/** The same, for a comma-separated list — a basket of symbols. */
export function useUrlList(
  key: string,
  fallback: string[],
  { push = false }: Pick<Options<string>, 'push'> = {},
): [string[], (value: string[]) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get(key);

  const latest = useRef({ fallback, push });
  latest.current = { fallback, push };

  // Parsed once per distinct string, and the identity is the point: the basket
  // is a dependency of the price fetch, so a fresh array every render would put
  // that request in a loop. `latest` is read rather than depended on for the
  // same reason — callers pass an array literal.
  const value = useMemo(
    () =>
      raw === null
        ? latest.current.fallback
        : raw
            .split(',')
            .map((symbol) => symbol.trim())
            .filter(Boolean),
    [raw],
  );

  const set = useCallback(
    (next: string[]) => {
      const { fallback: base, push: pushes } = latest.current;
      setParams(
        (current) => {
          const out = new URLSearchParams(current);
          // An emptied list is not an absent one. `?symbols=` has to survive the
          // trip or a link to a cleared desk would open on the default basket.
          if (same(next, base)) out.delete(key);
          else out.set(key, next.join(','));
          return out;
        },
        { replace: !pushes },
      );
    },
    [key, setParams],
  );

  return [value, set];
}
