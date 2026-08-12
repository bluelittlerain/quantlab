import { createContext, useContext } from "react";

import type { ThemeMode } from "../api/types";

export type ResolvedTheme = "LIGHT" | "DARK";

export interface ThemeContextValue {
  mode: ThemeMode;
  resolved: ResolvedTheme;
  setMode: (mode: ThemeMode) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useThemeMode(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useThemeMode must be used inside ThemeProvider");
  return context;
}
