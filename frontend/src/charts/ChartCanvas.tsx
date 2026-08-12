import { useEffect, useRef } from "react";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  ToolboxComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import type { EChartsCoreOption, EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

import { useThemeMode } from "../theme/themeContext";

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  ToolboxComponent,
  TooltipComponent,
  CanvasRenderer,
]);

interface ChartCanvasProps {
  option: EChartsCoreOption;
  ariaLabel: string;
  className?: string;
  pointCount?: number;
}

export function ChartCanvas({ option, ariaLabel, className, pointCount }: ChartCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const { resolved } = useThemeMode();

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current, resolved === "DARK" ? "dark" : undefined, {
      renderer: "canvas",
    });
    chartRef.current = chart;
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(containerRef.current);
    return () => {
      resizeObserver.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, [resolved]);

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true, lazyUpdate: true });
  }, [option, resolved]);

  return (
    <div
      ref={containerRef}
      className={className ?? "research-chart"}
      role="img"
      aria-label={ariaLabel}
      data-point-count={pointCount}
    />
  );
}
