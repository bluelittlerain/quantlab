import type {
  ApiErrorResponse,
  BacktestRequest,
  BacktestResult,
  ExportPreparation,
  Preset,
  PresetInput,
  RunHistoryItem,
  RuntimeInfo,
  SymbolMetadataResponse,
  ThemeSettings,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export function buildApiUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/+$/, "")}${path}`;
}

export function apiUrl(path: string): string {
  return buildApiUrl(API_BASE_URL, path);
}

export class QuantLabApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly field: string | null,
    readonly details: Record<string, unknown> | null,
  ) {
    super(message);
    this.name = "QuantLabApiError";
  }
}

async function readError(response: Response): Promise<QuantLabApiError> {
  try {
    const body = (await response.json()) as ApiErrorResponse;
    return new QuantLabApiError(
      body.error.code,
      body.error.message,
      body.error.field,
      body.error.details,
    );
  } catch {
    return new QuantLabApiError("NETWORK_ERROR", "本地服务暂时无法完成请求。", null, null);
  }
}

export async function runBacktest(
  request: BacktestRequest,
  options?: { forceRefresh?: boolean },
  signal?: AbortSignal,
): Promise<BacktestResult> {
  const response = await fetch(
    apiUrl(options?.forceRefresh ? "/api/market-data/refresh" : "/api/backtests"),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
      credentials: "include",
    },
  );
  if (!response.ok) {
    throw await readError(response);
  }
  return (await response.json()) as BacktestResult;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(url), { credentials: "include", ...init });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

export function getBacktest(runId: string): Promise<BacktestResult> {
  return requestJson(`/api/backtests/${encodeURIComponent(runId)}`);
}

export function listHistory(): Promise<RunHistoryItem[]> {
  return requestJson("/api/history");
}

export function deleteHistory(runId: string): Promise<{ deleted: boolean }> {
  return requestJson(`/api/history/${encodeURIComponent(runId)}`, { method: "DELETE" });
}

export function listPresets(): Promise<Preset[]> {
  return requestJson("/api/presets");
}

export function createPreset(input: PresetInput): Promise<Preset> {
  return requestJson("/api/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updatePreset(presetId: number, input: PresetInput): Promise<{ updated: boolean }> {
  return requestJson(`/api/presets/${presetId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deletePreset(presetId: number): Promise<{ deleted: boolean }> {
  return requestJson(`/api/presets/${presetId}`, { method: "DELETE" });
}

export function listRecentSymbols(): Promise<string[]> {
  return requestJson("/api/recent-symbols");
}

export function getSymbolMetadata(symbol: string): Promise<SymbolMetadataResponse> {
  return requestJson(`/api/symbols/${encodeURIComponent(symbol)}`);
}

export function getSettings(): Promise<ThemeSettings> {
  return requestJson("/api/settings");
}

export function getRuntimeInfo(): Promise<RuntimeInfo> {
  return requestJson("/api/runtime");
}

export function pairLANSession(code: string): Promise<{ paired: boolean }> {
  return requestJson("/api/session/pair", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
}

export function putSettings(settings: ThemeSettings): Promise<ThemeSettings> {
  return requestJson("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function prepareExport(runId: string): Promise<ExportPreparation> {
  return requestJson(`/api/exports/${encodeURIComponent(runId)}/prepare`, { method: "POST" });
}

export function exportUrl(runId: string, artifact: string): string {
  return apiUrl(`/api/exports/${encodeURIComponent(runId)}/${encodeURIComponent(artifact)}`);
}
