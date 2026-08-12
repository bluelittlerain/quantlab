import { useMemo } from "react";

import type { BacktestResult } from "../../api/types";
import { ChartCanvas } from "../../charts/ChartCanvas";
import { useThemeMode } from "../../theme/themeContext";
import { buildCostOption, buildDrawdownOption, buildPriceOption } from "./chartOptions";

export function PriceChart({ result }: { result: BacktestResult }) {
  const { resolved } = useThemeMode();
  const option = useMemo(() => buildPriceOption(result, resolved === "DARK"), [result, resolved]);
  return (
    <ChartCanvas
      option={option}
      ariaLabel="调整后价格、双均线与交易标记图"
      pointCount={result.price_series.length}
    />
  );
}

export function DrawdownChart({ result }: { result: BacktestResult }) {
  const { resolved } = useThemeMode();
  const option = useMemo(
    () => buildDrawdownOption(result, resolved === "DARK"),
    [result, resolved],
  );
  return (
    <ChartCanvas
      option={option}
      ariaLabel="策略回撤曲线"
      pointCount={result.equity_series.length}
    />
  );
}

export function CostChart({ result }: { result: BacktestResult }) {
  const { resolved } = useThemeMode();
  const option = useMemo(() => buildCostOption(result, resolved === "DARK"), [result, resolved]);
  return <ChartCanvas option={option} ariaLabel="港股交易成本分项图" />;
}
