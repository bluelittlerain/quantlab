import { Card, Collapse, Descriptions, List, Tag, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { Trade } from "../../api/types";
import { formatHKD, formatNumber, formatPercent } from "../../lib/format";

const columns: ColumnsType<Trade> = [
  { title: "ID", dataIndex: "trade_id", width: 72, fixed: "left" },
  {
    title: "状态",
    dataIndex: "status",
    width: 96,
    render: (status: Trade["status"]) =>
      status === "OPEN" ? <Tag color="processing">持仓中</Tag> : <Tag>已平仓</Tag>,
  },
  { title: "买入日期", dataIndex: "entry_date", width: 120 },
  {
    title: "买入价",
    dataIndex: "entry_execution_price",
    width: 126,
    align: "right",
    render: formatHKD,
  },
  { title: "卖出日期", dataIndex: "exit_date", width: 120, render: (value) => value ?? "—" },
  {
    title: "卖出价",
    dataIndex: "exit_execution_price",
    width: 126,
    align: "right",
    render: (value: number | null) => (value === null ? "—" : formatHKD(value)),
  },
  {
    title: "数量",
    dataIndex: "quantity",
    width: 110,
    align: "right",
    render: formatNumber,
  },
  {
    title: "持有交易日",
    dataIndex: "holding_days",
    width: 116,
    align: "right",
  },
  {
    title: "净损益",
    dataIndex: "net_pnl",
    width: 132,
    align: "right",
    sorter: (left, right) => left.net_pnl - right.net_pnl,
    render: (value: number) => (
      <span className={value >= 0 ? "value-positive" : "value-negative"}>{formatHKD(value)}</span>
    ),
  },
  {
    title: "净收益率",
    dataIndex: "net_return",
    width: 116,
    align: "right",
    render: formatPercent,
  },
  {
    title: "总成本",
    dataIndex: "total_cost",
    width: 120,
    align: "right",
    render: formatHKD,
  },
];

const desktopTableScroll = {
  x: 1120,
  y: "clamp(320px, 58vh, 640px)",
  scrollToFirstRowOnChange: true,
} as const;

interface TradeTableProps {
  trades: Trade[];
  mobile?: boolean;
}

function MobileTradeCard({ trade }: { trade: Trade }) {
  const exit = trade.exit_date ?? "持仓中";
  const allCosts = [trade.entry_costs, ...(trade.exit_costs ? [trade.exit_costs] : [])];
  const commission = allCosts.reduce((sum, item) => sum + item.broker_commission, 0);
  const stampDuty = allCosts.reduce((sum, item) => sum + item.stamp_duty, 0);
  const slippage = allCosts.reduce((sum, item) => sum + item.slippage_cost, 0);
  const statutory = allCosts.reduce(
    (sum, item) =>
      sum +
      item.trading_fee +
      item.transaction_levy +
      item.afrc_transaction_levy +
      item.settlement_fee,
    0,
  );
  return (
    <Card
      size="small"
      className="mobile-trade-card"
      title={`#${trade.trade_id} · ${trade.status === "OPEN" ? "持仓中" : "已平仓"}`}
      extra={
        <span className={trade.net_pnl >= 0 ? "value-positive" : "value-negative"}>
          {formatPercent(trade.net_return)}
        </span>
      }
    >
      <Typography.Text type="secondary">
        {trade.entry_date} → {exit}
      </Typography.Text>
      <div className="mobile-trade-summary">
        <div>
          <span>买入</span>
          <strong>{formatHKD(trade.entry_execution_price)}</strong>
        </div>
        <div>
          <span>卖出</span>
          <strong>
            {trade.exit_execution_price === null ? "持仓中" : formatHKD(trade.exit_execution_price)}
          </strong>
        </div>
        <div>
          <span>净损益</span>
          <strong className={trade.net_pnl >= 0 ? "value-positive" : "value-negative"}>
            {formatHKD(trade.net_pnl)}
          </strong>
        </div>
      </div>
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: "details",
            label: "查看成本与持有详情",
            children: (
              <Descriptions size="small" column={1}>
                <Descriptions.Item label="数量">{formatNumber(trade.quantity)}</Descriptions.Item>
                <Descriptions.Item label="持有交易日">{trade.holding_days}</Descriptions.Item>
                <Descriptions.Item label="佣金">{formatHKD(commission)}</Descriptions.Item>
                <Descriptions.Item label="印花税">{formatHKD(stampDuty)}</Descriptions.Item>
                <Descriptions.Item label="其他法定费用">{formatHKD(statutory)}</Descriptions.Item>
                <Descriptions.Item label="滑点">{formatHKD(slippage)}</Descriptions.Item>
                <Descriptions.Item label="总成本">{formatHKD(trade.total_cost)}</Descriptions.Item>
              </Descriptions>
            ),
          },
        ]}
      />
    </Card>
  );
}

export function TradeTable({ trades, mobile = false }: TradeTableProps) {
  return (
    <section className="trade-records-section" aria-labelledby="trades-title">
      <div className="section-heading compact">
        <div>
          <Typography.Title level={2} id="trades-title">
            交易记录
          </Typography.Title>
          <Typography.Text type="secondary">共 {trades.length} 笔开仓记录</Typography.Text>
        </div>
      </div>
      {mobile ? (
        <List
          className="mobile-trade-list"
          dataSource={trades}
          pagination={trades.length > 20 ? { pageSize: 20, size: "small" } : false}
          locale={{ emptyText: "当前区间没有交易" }}
          renderItem={(trade) => (
            <List.Item>
              <MobileTradeCard trade={trade} />
            </List.Item>
          )}
        />
      ) : (
        <div className="trade-table-shell" data-testid="trade-table-shell">
          <Table<Trade>
            className="trade-table"
            rowKey="trade_id"
            columns={columns}
            dataSource={trades}
            scroll={desktopTableScroll}
            pagination={{
              defaultPageSize: 20,
              pageSizeOptions: [20, 50, 100],
              showSizeChanger: true,
            }}
            locale={{ emptyText: "当前区间没有交易" }}
            expandable={{
              expandedRowRender: (trade) => (
                <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
                  <Descriptions.Item label="买入佣金">
                    {formatHKD(trade.entry_costs.broker_commission)}
                  </Descriptions.Item>
                  <Descriptions.Item label="买入印花税">
                    {formatHKD(trade.entry_costs.stamp_duty)}
                  </Descriptions.Item>
                  <Descriptions.Item label="买入法定费用">
                    {formatHKD(
                      trade.entry_costs.trading_fee +
                        trade.entry_costs.transaction_levy +
                        trade.entry_costs.afrc_transaction_levy +
                        trade.entry_costs.settlement_fee,
                    )}
                  </Descriptions.Item>
                  <Descriptions.Item label="买入滑点">
                    {formatHKD(trade.entry_costs.slippage_cost)}
                  </Descriptions.Item>
                  <Descriptions.Item label="卖出成本" span={2}>
                    {trade.exit_costs
                      ? formatHKD(trade.exit_costs.total_cost)
                      : "持仓中，不虚构退出成本"}
                  </Descriptions.Item>
                  <Descriptions.Item label="毛损益">{formatHKD(trade.gross_pnl)}</Descriptions.Item>
                  <Descriptions.Item label="总成本">
                    {formatHKD(trade.total_cost)}
                  </Descriptions.Item>
                </Descriptions>
              ),
            }}
          />
        </div>
      )}
    </section>
  );
}
