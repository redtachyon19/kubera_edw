import { createContext, useContext } from 'react';

import type { Mode } from './useTheme';

export interface ThemeValue {
  mode: Mode;
  toggle: () => void;
}

export const ThemeContext = createContext<ThemeValue>({ mode: 'light', toggle: () => {} });

/** Current stock (light/dark) and the switch that inverts it. */
export function useThemeMode(): ThemeValue {
  return useContext(ThemeContext);
}
