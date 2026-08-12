import { describe, expect, it } from "vitest";

import { fixedBacktestResult } from "../../test/fixture";
import { buildEquityOption } from "./equityOption";

describe("buildEquityOption", () => {
  it("uses backend dates and equity values without recomputing the series", () => {
    const option = buildEquityOption(fixedBacktestResult) as {
      xAxis: { data: string[] };
      series: Array<{ data: number[] }>;
    };
    expect(option.xAxis.data).toEqual(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]);
    expect(option.series[0]?.data).toEqual([100_000, 104_000, 108_000, 112_000]);
    expect(option.series[1]?.data).toEqual([100_000, 102_000, 106_000, 108_000]);
  });
});
