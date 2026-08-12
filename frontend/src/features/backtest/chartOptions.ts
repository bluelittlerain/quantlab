import type { EChartsCoreOption } from "echarts/core";

import type { BacktestResult } from "../../api/types";
import { chartPalette } from "../../charts/palette";

function commonAxes(dark: boolean) {
  const palette = chartPalette(dark);
  return {
    axisLine: { lineStyle: { color: palette.grid } },
    axisLabel: { color: palette.muted, hideOverlap: true },
    splitLine: { lineStyle: { color: palette.grid, opacity: 0.7 } },
  };
}

export function buildPriceOption(result: BacktestResult, dark: boolean): EChartsCoreOption {
  const palette = chartPalette(dark);
  const buys = result.price_series
    .filter((point) => point.action === "BUY")
    .map((point) => [point.date, point.close]);
  const sells = result.price_series
    .filter((point) => point.action === "SELL")
    .map((point) => [point.date, point.close]);
  return {
    animation: false,
    backgroundColor: "transparent",
    color: [palette.text, palette.strategy, palette.benchmark, palette.positive, palette.negative],
    legend: { top: 2, textStyle: { color: palette.text } },
    tooltip: { trigger: "axis", confine: true },
    toolbox: { right: 8, feature: { restore: { title: "重置缩放" } } },
    grid: { left: 18, right: 24, top: 52, bottom: 72, containLabel: true },
    xAxis: {
      ...commonAxes(dark),
      type: "category",
      boundaryGap: false,
      data: result.price_series.map((point) => point.date),
    },
    yAxis: {
      ...commonAxes(dark),
      type: "value",
      scale: true,
      axisLabel: {
        color: palette.muted,
        formatter: (value: number) => `HK$${value.toLocaleString("zh-HK")}`,
      },
    },
    dataZoom: [
      { type: "inside", filterMode: "none" },
      { type: "slider", height: 22, bottom: 16, filterMode: "none" },
    ],
    series: [
      {
        name: "调整后收盘价",
        type: "line",
        showSymbol: false,
        data: result.price_series.map((point) => point.close),
      },
      {
        name: `SMA${result.strategy.short_window}`,
        type: "line",
        showSymbol: false,
        connectNulls: false,
        data: result.price_series.map((point) => point.short_sma),
      },
      {
        name: `SMA${result.strategy.long_window}`,
        type: "line",
        showSymbol: false,
        connectNulls: false,
        data: result.price_series.map((point) => point.long_sma),
      },
      { name: "买入", type: "scatter", symbolSize: 10, data: buys },
      { name: "卖出", type: "scatter", symbolSize: 10, data: sells },
    ],
  };
}

export function buildDrawdownOption(result: BacktestResult, dark: boolean): EChartsCoreOption {
  const palette = chartPalette(dark);
  return {
    animation: false,
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      confine: true,
      valueFormatter: (value: unknown) => `${(Number(value) * 100).toFixed(2)}%`,
    },
    grid: { left: 18, right: 24, top: 28, bottom: 66, containLabel: true },
    xAxis: {
      ...commonAxes(dark),
      type: "category",
      boundaryGap: false,
      data: result.equity_series.map((point) => point.date),
    },
    yAxis: {
      ...commonAxes(dark),
      type: "value",
      max: 0,
      axisLabel: {
        color: palette.muted,
        formatter: (value: number) => `${(value * 100).toFixed(0)}%`,
      },
    },
    dataZoom: [
      { type: "inside", filterMode: "none" },
      { type: "slider", height: 20, bottom: 14, filterMode: "none" },
    ],
    series: [
      {
        name: "回撤",
        type: "line",
        showSymbol: false,
        lineStyle: { color: palette.negative, width: 1.5 },
        areaStyle: { color: palette.negative, opacity: 0.18 },
        data: result.equity_series.map((point) => point.drawdown),
        markPoint: {
          symbolSize: 44,
          label: { formatter: "最大\n回撤", color: palette.text, fontSize: 10 },
          data: [{ type: "min", name: "最大回撤" }],
        },
      },
    ],
  };
}

export function buildCostOption(result: BacktestResult, dark: boolean): EChartsCoreOption {
  const palette = chartPalette(dark);
  const costs = result.cost_summary;
  return {
    animation: false,
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      confine: true,
      valueFormatter: (value: unknown) => `HK$ ${Number(value).toFixed(2)}`,
    },
    grid: { left: 18, right: 30, top: 14, bottom: 10, containLabel: true },
    xAxis: { ...commonAxes(dark), type: "value" },
    yAxis: {
      ...commonAxes(dark),
      type: "category",
      data: ["佣金", "印花税", "交易费", "证监会征费", "财汇局征费", "结算费", "滑点"],
    },
    series: [
      {
        name: "累计成本",
        type: "bar",
        itemStyle: { color: palette.excess, borderRadius: [0, 4, 4, 0] },
        data: [
          costs.broker_commission,
          costs.stamp_duty,
          costs.trading_fee,
          costs.transaction_levy,
          costs.afrc_transaction_levy,
          costs.settlement_fee,
          costs.slippage_cost,
        ],
      },
    ],
  };
}
