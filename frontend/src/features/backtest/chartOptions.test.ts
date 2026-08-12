import { describe, expect, it } from "vitest";

import { fixedBacktestResult } from "../../test/fixture";
import { buildCostOption, buildDrawdownOption, buildPriceOption } from "./chartOptions";

describe("research chart options", () => {
  it("preserves the exact backend price date range", () => {
    const option = buildPriceOption(fixedBacktestResult, false) as {
      xAxis: { data: string[] };
      series: Array<{ data: unknown[] }>;
    };
    expect(option.xAxis.data.at(0)).toBe("2024-01-02");
    expect(option.xAxis.data.at(-1)).toBe("2024-01-05");
    expect(option.series[0]?.data).toEqual([100, 104, 108, 112]);
  });

  it("uses backend drawdown and cost components without deriving new facts", () => {
    const drawdown = buildDrawdownOption(fixedBacktestResult, true) as {
      series: Array<{ data: number[] }>;
    };
    const costs = buildCostOption(fixedBacktestResult, true) as {
      series: Array<{ data: number[] }>;
    };
    expect(drawdown.series[0]?.data).toEqual([0, 0, 0, 0]);
    expect(costs.series[0]?.data.at(0)).toBe(200);
    expect(costs.series[0]?.data.at(-1)).toBe(0);
  });
});
