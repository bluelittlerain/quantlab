import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QuantLabApiError } from "../../api/client";
import type { SymbolMetadataResponse } from "../../api/types";
import { BacktestForm } from "./BacktestForm";

describe("BacktestForm", () => {
  it("submits the explicit HK board lots only after the user clicks run", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    render(
      <ConfigProvider locale={zhCN}>
        <BacktestForm loading={false} onRun={onRun} />
      </ConfigProvider>,
    );

    expect(screen.getByLabelText("港股代码")).toHaveValue("0700.HK");
    expect(onRun).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /运行回测/ }));

    await waitFor(() => expect(onRun).toHaveBeenCalledTimes(1));
    const request = onRun.mock.calls[0]?.[0];
    expect(request.symbol).toBe("0700.HK");
    expect(request.benchmark_symbol).toBe("2800.HK");
    expect(request.board_lot).toEqual({ lot_size: 100, confirmed: true });
    expect(request.benchmark_board_lot).toEqual({ lot_size: 500, confirmed: true });
    expect(request.short_window).toBe(20);
    expect(request.long_window).toBe(60);
  });

  it("places a structured API error beside the matching field", async () => {
    render(
      <ConfigProvider locale={zhCN}>
        <BacktestForm
          loading={false}
          onRun={vi.fn()}
          apiError={
            new QuantLabApiError(
              "INVALID_SMA_WINDOWS",
              "长均线必须大于短均线。",
              "long_window",
              null,
            )
          }
        />
      </ConfigProvider>,
    );

    expect(await screen.findByText("长均线必须大于短均线。")).toBeVisible();
    expect(screen.getByLabelText("长均线")).toHaveAttribute("aria-invalid", "true");
  });

  it("does not let a stale symbol lookup overwrite newer user input", async () => {
    const user = userEvent.setup();
    let completeLookup!: (value: SymbolMetadataResponse) => void;
    const resolveSymbol = vi.fn(
      () =>
        new Promise<SymbolMetadataResponse>((resolve) => {
          completeLookup = resolve;
        }),
    );
    render(
      <ConfigProvider locale={zhCN}>
        <BacktestForm loading={false} onRun={vi.fn()} resolveSymbol={resolveSymbol} />
      </ConfigProvider>,
    );

    const symbol = screen.getByLabelText("港股代码");
    await user.click(symbol);
    await user.clear(symbol);
    await user.type(symbol, "INVALID");
    completeLookup({
      symbol: {
        normalized_symbol: "0700.HK",
        exchange: "HKEX",
        currency: "HKD",
        display_name: null,
        local_alias: null,
      },
      board_lot: {
        lot_size: 100,
        source: "AUTO",
        verified_at: "2024-01-01T00:00:00+00:00",
        confirmed: true,
      },
      board_lot_requires_confirmation: false,
      provider: "fixture",
    });

    await waitFor(() => expect(symbol).toHaveValue("INVALID"));
  });
});
