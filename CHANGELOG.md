# Changelog

All notable changes to QuantLab are documented in this file.

## 0.2.1 - 2026-08-10

### Fixed

- Fixed the real 0700.HK 2020-2024 workflow by preserving round-trip floating-point values in
  the deterministic market-data cache.
- Replaced generic validation failures with stable field-specific errors and protected symbol
  inputs from stale asynchronous metadata lookups.
- Removed duplicate history and preset empty states and made board-lot confirmation explicit.

### Improved

- Added a responsive desktop, tablet and mobile workflow with collapsible research controls,
  mobile drawers, one-chart-at-a-time navigation and mobile trade cards.
- Added product-focused cost controls, compact statutory-fee defaults and clearer run summaries.
- Added opt-in private-LAN access with per-process pairing, a six-digit code and in-memory session
  tokens while keeping loopback-only access as the default.
- Added deployment-neutral application and repository boundaries, explicit CORS configuration,
  liveness/readiness endpoints, SPA asset caching rules and self-hosting Docker documentation.
- Expanded deterministic desktop, mobile, theme, validation, LAN and deployment contract tests.

This release does not add a strategy or market and does not change the verified backtest,
execution, cost, adjusted-price, metric, run-id or fingerprint semantics. G01-G13 and HK01-HK15
remain unchanged. No GitHub Pages demo or public Web service is included.

## 0.2.0 - 2026-08-10

### Added

- Added a trusted HKEX stock and ETF daily-research vertical slice for normalized Hong Kong
  symbols, board-lot execution, side-aware trading costs and the 2800.HK tradable benchmark.
- Added HK01-HK15 deterministic golden tests, XHKG session validation and advanced risk,
  exposure, turnover, profit-factor and cost metrics calculated by the backend.
- Added a typed FastAPI boundary, local SQLite run history, reusable presets, recent symbols,
  deterministic market-data cache and explicit HTML/CSV/Manifest/ZIP exports.
- Added a React, TypeScript, Ant Design and Apache ECharts product interface with Chinese locale,
  system/light/dark themes, responsive research controls, four research charts and a practical
  trade ledger.
- Added a FastAPI desktop runtime that serves bundled React assets inside the existing isolated
  Edge/Chrome application window.

### Changed

- Made the Hong Kong product the default Windows entry while retaining the v0.1 Streamlit source
  for regression and migration reference.
- Moved engineering metadata into the data-and-reproducibility view so the overview prioritizes
  result, benchmark, risk and cost interpretation.

The existing SPY execution accounting, G01-G13 golden expectations, formal v0.1.0 example,
fingerprint rules and report consistency contracts remain unchanged.

## 0.1.1 - 2026-07-25

### Fixed

- Isolated the Streamlit application from browser extensions that could hide page controls.
- Kept the native sidebar restore control visible after the parameter sidebar is collapsed.
- Bounded the packaged smoke-test lifecycle so it exits and releases its service port.
- Shortened Windows build intermediates to avoid path-length failures.
- Deferred download resource registration so download managers such as IDM do not capture CSV
  resources immediately after a backtest completes.

### Improved

- Reduced equity-chart payload size and improved interactive chart performance.
- Added deterministic display-only chart sampling that retains endpoints and local extrema.
- Added light and dark page themes without changing exported artifacts.
- Improved responsive layouts for common Windows viewport sizes and display scaling.
- Made the complete `run_id` and data fingerprint available for direct viewing and copying.
- Added six-stage workflow feedback with elapsed time and market-data cache status.
- Separated session state for market data, current results, presentation data and prepared exports.
- Added explicit export preparation and a single ZIP containing HTML, CSV and Manifest outputs.
- Added a compact trade preview with explicit loading of the complete ledger.
- Refined dark-theme contrast for controls, charts, navigation, helper text and disabled states.
- Added visible keyboard focus treatment for native Streamlit controls.
- Sanitized user-facing workflow and export errors while retaining safe stage diagnostics.

This release does not change backtest execution, fills, fees, slippage, adjusted-price handling,
trade accounting or metric definitions. G01-G13 golden-test results remain unchanged.

## 0.1.0 - 2026-07-14

- Added a cash-ledger-driven, long-only SPY daily backtest.
- Executed close-of-day SMA targets at the next trading day's adjusted open.
- Applied transparent two-sided fees and slippage to actual fills.
- Standardized split- and distribution-adjusted SPY OHLC with deterministic SHA256 fingerprints.
- Added manually auditable G01-G13 golden cases and deterministic offline tests.
- Added a single presentation model shared by Streamlit, HTML, CSV and Manifest outputs.
- Added a focused Streamlit interface for the SPY SMA 20/60 workflow.
- Added a self-contained HTML report, structured trade CSV and run Manifest.
- Added an offline CI quality gate and reproducible Windows Release configuration.

Historical results are not a promise of future performance and are not investment advice.
