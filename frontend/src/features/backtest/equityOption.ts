import type { EChartsCoreOption } from "echarts/core";

import type { BacktestResult } from "../../api/types";
import { chartPalette } from "../../charts/palette";

export function buildEquityOption(result: BacktestResult, dark = false): EChartsCoreOption {
  const palette = chartPalette(dark);
  const dates = result.equity_series.map((point) => point.date);
  return {
    animation: false,
    backgroundColor: "transparent",
    color: [palette.strategy, palette.benchmark, palette.excess],
    legend: {
      top: 2,
      right: 8,
      data: ["策略净值", "买入持有基准", "超额"],
      textStyle: { color: palette.text },
    },
    grid: { left: 18, right: 24, top: 48, bottom: 72, containLabel: true },
    tooltip: {
      trigger: "axis",
      confine: true,
      valueFormatter: (value: unknown) =>
        `HK$ ${Number(value).toLocaleString("zh-HK", { maximumFractionDigits: 2 })}`,
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: dates,
      axisLabel: { hideOverlap: true },
      axisLine: { lineStyle: { color: palette.grid } },
    },
    yAxis: [
      {
        type: "value",
        scale: true,
        splitLine: { lineStyle: { color: palette.grid, opacity: 0.7 } },
        axisLabel: {
          color: palette.muted,
          formatter: (value: number) => value.toLocaleString("zh-HK"),
        },
      },
      {
        type: "value",
        scale: true,
        splitLine: { show: false },
        axisLabel: { color: palette.muted },
      },
    ],
    dataZoom: [
      { type: "inside", filterMode: "none" },
      { type: "slider", height: 22, bottom: 16, filterMode: "none" },
    ],
    series: [
      {
        name: "策略净值",
        type: "line",
        showSymbol: false,
        smooth: false,
        data: result.equity_series.map((point) => point.strategy_equity),
      },
      {
        name: "买入持有基准",
        type: "line",
        showSymbol: false,
        smooth: false,
        data: result.equity_series.map((point) => point.benchmark_equity),
      },
      {
        name: "超额",
        type: "line",
        yAxisIndex: 1,
        showSymbol: false,
        lineStyle: { type: "dashed", width: 1.5 },
        data: result.equity_series.map((point) => point.excess),
      },
    ],
  };
}
