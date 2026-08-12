import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportPanel } from "./ExportPanel";

describe("ExportPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("does not create download resources until the user explicitly prepares them", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "hk_fixture_001",
          generated_at_utc: "2026-08-10T00:00:00Z",
          files: {
            "report.html": 1200,
            "trades.csv": 600,
            "manifest.json": 800,
            "bundle.zip": 1800,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ExportPanel runId="hk_fixture_001" />
      </QueryClientProvider>,
    );

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryAllByRole("link", { name: "下载" })).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: /准备导出文件/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(screen.getAllByRole("link", { name: /下载/ })).toHaveLength(4);
    expect(screen.getByText("1.8 KB")).toBeInTheDocument();
  });
});
