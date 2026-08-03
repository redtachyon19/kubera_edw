import { useCallback, useEffect, useState } from 'react';

export type Mode = 'light' | 'dark';

const KEY = 'kubera-theme';

function initial(): Mode {
  const stored = localStorage.getItem(KEY);
  if (stored === 'light' || stored === 'dark') return stored;
  // The bone card is the house identity, so it is the default regardless of what
  // the operating system prefers. Dark is a choice the reader makes, not a guess.
  return 'light';
}

/**
 * Light/dark as a single stamped attribute on <html>, remembered across visits.
 *
 * The attribute is what every stylesheet keys off, and it is also what the
 * embedded dashboards are told to render as, so the whole page inverts together.
 */
export function useTheme(): [Mode, () => void] {
  const [mode, setMode] = useState<Mode>(initial);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', mode);
    localStorage.setItem(KEY, mode);
  }, [mode]);

  const toggle = useCallback(() => setMode((m) => (m === 'light' ? 'dark' : 'light')), []);
  return [mode, toggle];
}
