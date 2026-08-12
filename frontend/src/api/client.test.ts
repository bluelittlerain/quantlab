import { afterEach, describe, expect, it, vi } from "vitest";

import { buildApiUrl, exportUrl, listHistory } from "./client";

describe("API deployment boundary", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses same-origin by default and composes an explicit web origin without double slashes", () => {
    expect(buildApiUrl("", "/api/health")).toBe("/api/health");
    expect(buildApiUrl("https://api.quantlab.example/", "/api/health")).toBe(
      "https://api.quantlab.example/api/health",
    );
    expect(exportUrl("run id", "trades.csv")).toBe("/api/exports/run%20id/trades.csv");
  });

  it("includes browser credentials without hardcoding localhost", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listHistory();

    expect(fetchMock).toHaveBeenCalledWith("/api/history", { credentials: "include" });
  });
});
