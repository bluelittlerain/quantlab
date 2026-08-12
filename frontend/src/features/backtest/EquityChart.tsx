import { useMemo } from "react";

import type { BacktestResult } from "../../api/types";
import { ChartCanvas } from "../../charts/ChartCanvas";
import { useThemeMode } from "../../theme/themeContext";
import { buildEquityOption } from "./equityOption";

interface EquityChartProps {
  result: BacktestResult;
}

export function EquityChart({ result }: EquityChartProps) {
  const { resolved } = useThemeMode();
  const option = useMemo(() => buildEquityOption(result, resolved === "DARK"), [result, resolved]);
  return (
    <ChartCanvas
      option={option}
      className="equity-chart"
      ariaLabel="策略与买入持有基准净值对比图"
      pointCount={result.equity_series.length}
    />
  );
}
