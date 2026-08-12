import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { fixedBacktestResult } from "./test/fixture";

const setOption = vi.fn();
const dispose = vi.fn();

vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: vi.fn(() => ({ setOption, resize: vi.fn(), dispose })),
}));

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe("QuantLab vertical slice", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        void input;
        if (!init?.method || init.method === "GET") {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify(fixedBacktestResult), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("does not call the backend before an explicit run", () => {
    renderApp();
    expect(screen.getByText("开始一次港股趋势研究")).toBeInTheDocument();
    expect(
      vi.mocked(fetch).mock.calls.some((call) => String(call[0]).includes("/api/backtests")),
    ).toBe(false);
  });

  it("renders overview, equity chart and trades from one API result", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("button", { name: /运行回测/ }));

    await waitFor(() => expect(screen.getByText("回测概览")).toBeInTheDocument());
    expect(
      vi.mocked(fetch).mock.calls.filter((call) => String(call[0]).includes("/api/backtests")),
    ).toHaveLength(1);
    expect(screen.getByText("HK$ 112,000.00")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "净值与回撤" }));
    expect(screen.getByRole("img", { name: "策略与买入持有基准净值对比图" })).toHaveAttribute(
      "data-point-count",
      "4",
    );
    expect(setOption).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("tab", { name: "交易记录" }));
    expect(screen.getByText("7.34%")).toBeInTheDocument();
    const tableShell = screen.getByTestId("trade-table-shell");
    expect(tableShell.querySelector(".ant-table-sticky-holder")).not.toBeInTheDocument();
    expect(tableShell.querySelector(".ant-table-body")).toBeInTheDocument();
  });

  it("collapses and restores desktop parameters without running a backtest", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("button", { name: "收起参数" }));
    expect(screen.getByRole("button", { name: "展开参数" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "展开参数" }));
    expect(screen.getByLabelText("港股代码")).toBeVisible();
    expect(
      vi.mocked(fetch).mock.calls.some((call) => String(call[0]).includes("/api/backtests")),
    ).toBe(false);
  });

  it("uses a parameter drawer and trade cards on a mobile viewport", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("max-width: 767px"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const user = userEvent.setup();
    renderApp();

    expect(screen.queryByLabelText("港股代码")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "参数" }));
    expect(await screen.findByRole("dialog", { name: "研究参数" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: /运行回测/ }));
    await waitFor(() => expect(screen.getByText("回测概览")).toBeVisible());
    await user.click(screen.getByRole("tab", { name: "交易记录" }));
    expect(screen.getByText("#1 · 已平仓")).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
