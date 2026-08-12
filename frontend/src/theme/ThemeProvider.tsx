import { ConfigProvider, theme as antTheme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useEffect, useMemo, useState } from "react";

import type { ThemeMode } from "../api/types";
import { ThemeContext } from "./themeContext";
import type { ResolvedTheme, ThemeContextValue } from "./themeContext";

const STORAGE_KEY = "quantlab.theme-mode";

function storedMode(): ThemeMode {
  const value = localStorage.getItem(STORAGE_KEY);
  return value === "LIGHT" || value === "DARK" || value === "SYSTEM" ? value : "SYSTEM";
}

function systemTheme(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "DARK" : "LIGHT";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(storedMode);
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme);
  const resolved = mode === "SYSTEM" ? system : mode;

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystem(media.matches ? "DARK" : "LIGHT");
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = resolved.toLowerCase();
    document.documentElement.style.colorScheme = resolved === "DARK" ? "dark" : "light";
  }, [resolved]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      resolved,
      setMode: (nextMode) => {
        localStorage.setItem(STORAGE_KEY, nextMode);
        setModeState(nextMode);
      },
    }),
    [mode, resolved],
  );

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: resolved === "DARK" ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
          token: {
            colorPrimary: resolved === "DARK" ? "#62a0ff" : "#1267e5",
            colorSuccess: resolved === "DARK" ? "#4bd4a2" : "#13855c",
            colorError: resolved === "DARK" ? "#ff7b8c" : "#ca3c4f",
            colorBgLayout: resolved === "DARK" ? "#0d131d" : "#f4f7fb",
            colorBgContainer: resolved === "DARK" ? "#131c29" : "#ffffff",
            colorBorder: resolved === "DARK" ? "#2d3a4d" : "#dce5f0",
            borderRadius: 8,
            fontFamily:
              'Inter, "SF Pro Text", "Segoe UI", "Microsoft YaHei", system-ui, sans-serif',
          },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}
