import { Card, Col, Row, Statistic, Tag, Typography } from "antd";

import type { BacktestResult } from "../../api/types";
import { formatHKD, formatPercent } from "../../lib/format";

interface OverviewProps {
  result: BacktestResult;
}

export function Overview({ result }: OverviewProps) {
  const metrics = result.strategy_metrics;
  return (
    <section aria-labelledby="overview-title">
      <div className="section-heading">
        <div>
          <Typography.Title level={2} id="overview-title">
            回测概览
          </Typography.Title>
          <Typography.Text type="secondary">
            {result.date_range.actual_start} 至 {result.date_range.actual_end}
          </Typography.Text>
        </div>
        <Tag color="success">运行完成</Tag>
      </div>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="最终权益" value={formatHKD(metrics.final_equity)} />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="年化收益（CAGR）" value={formatPercent(metrics.cagr)} />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="最大回撤" value={formatPercent(metrics.max_drawdown)} />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="基准 CAGR" value={formatPercent(result.benchmark_metrics.cagr)} />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="超额收益" value={formatPercent(result.excess_return)} />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="总交易成本" value={formatHKD(metrics.total_trading_costs)} />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="已平仓交易" value={metrics.closed_trade_count} suffix="笔" />
          </Card>
        </Col>
        <Col xs={12} md={8} xl={6}>
          <Card className="metric-card">
            <Statistic title="市场敞口" value={formatPercent(metrics.market_exposure)} />
          </Card>
        </Col>
      </Row>
    </section>
  );
}
