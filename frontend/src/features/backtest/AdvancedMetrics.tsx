import { Collapse, Descriptions } from "antd";

import type { PerformanceMetrics } from "../../api/types";
import { formatHKD, formatNumber, formatPercent } from "../../lib/format";

export function AdvancedMetrics({ metrics }: { metrics: PerformanceMetrics }) {
  return (
    <Collapse
      className="advanced-metrics"
      items={[
        {
          key: "advanced",
          label: "高级指标",
          children: (
            <Descriptions column={{ xs: 1, sm: 2, lg: 3 }} size="small" bordered>
              <Descriptions.Item label="年化收益（CAGR）">
                {formatPercent(metrics.cagr)}
              </Descriptions.Item>
              <Descriptions.Item label="年化波动率">
                {formatPercent(metrics.annualized_volatility)}
              </Descriptions.Item>
              <Descriptions.Item label="Sharpe Ratio">
                {metrics.sharpe_ratio === null ? "N/A" : formatNumber(metrics.sharpe_ratio)}
              </Descriptions.Item>
              <Descriptions.Item label="Calmar Ratio">
                {metrics.calmar_ratio === null ? "N/A" : formatNumber(metrics.calmar_ratio)}
              </Descriptions.Item>
              <Descriptions.Item label="市场暴露">
                {formatPercent(metrics.market_exposure)}
              </Descriptions.Item>
              <Descriptions.Item label="换手率">
                {formatPercent(metrics.turnover)}
              </Descriptions.Item>
              <Descriptions.Item label="胜率">{formatPercent(metrics.win_rate)}</Descriptions.Item>
              <Descriptions.Item label="Profit Factor">
                {metrics.profit_factor === null ? "N/A" : formatNumber(metrics.profit_factor)}
              </Descriptions.Item>
              <Descriptions.Item label="平均交易收益">
                {formatPercent(metrics.average_trade_return)}
              </Descriptions.Item>
              <Descriptions.Item label="平均持有交易日">
                {metrics.average_holding_period === null
                  ? "N/A"
                  : formatNumber(metrics.average_holding_period)}
              </Descriptions.Item>
              <Descriptions.Item label="累计滑点成本">
                {formatHKD(metrics.total_slippage_cost)}
              </Descriptions.Item>
              <Descriptions.Item label="成本 / 毛利润">
                {formatPercent(metrics.cost_to_gross_profit_ratio)}
              </Descriptions.Item>
            </Descriptions>
          ),
        },
      ]}
    />
  );
}
