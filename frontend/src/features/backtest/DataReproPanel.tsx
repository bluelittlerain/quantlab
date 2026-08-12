import { ReloadOutlined } from "@ant-design/icons";
import { Button, Descriptions, Space, Tag, Typography } from "antd";

import type { BacktestResult } from "../../api/types";
import { symbolLabel } from "../../lib/symbol";

interface DataReproPanelProps {
  result: BacktestResult;
  refreshing: boolean;
  onRefresh: () => void;
}

export function DataReproPanel({ result, refreshing, onRefresh }: DataReproPanelProps) {
  const data = result.market_data;
  return (
    <section aria-labelledby="data-title" className="content-section">
      <div className="section-heading">
        <div>
          <Typography.Title level={2} id="data-title">
            数据与复现
          </Typography.Title>
          <Typography.Text type="secondary">
            工程元数据集中保留，不占用研究结论区域。
          </Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={refreshing} onClick={onRefresh}>
          重新获取行情并运行
        </Button>
      </div>
      <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
        <Descriptions.Item label="标的">{result.symbol.normalized_symbol}</Descriptions.Item>
        <Descriptions.Item label="比较基准">{symbolLabel(result.benchmark)}</Descriptions.Item>
        <Descriptions.Item label="数据来源">{data.source}</Descriptions.Item>
        <Descriptions.Item label="缓存状态">
          <Tag color={data.cache_status === "CACHE" ? "blue" : "green"}>
            {data.cache_status === "CACHE" ? "使用缓存" : "已刷新"}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="数据更新时间">{data.fetched_at_utc}</Descriptions.Item>
        <Descriptions.Item label="预热行数">{data.warmup_rows}</Descriptions.Item>
        <Descriptions.Item label="调整口径" span={2}>
          {data.adjustment_method}
        </Descriptions.Item>
        <Descriptions.Item label="运行标识" span={2}>
          <Typography.Text copyable code>
            {result.run_id}
          </Typography.Text>
        </Descriptions.Item>
        <Descriptions.Item label="数据 SHA256" span={2}>
          <Space orientation="vertical" size={4}>
            <Typography.Text code>{data.data_sha256.slice(0, 16)}…</Typography.Text>
            <Typography.Text copyable={{ text: data.data_sha256 }} type="secondary">
              复制完整数据指纹
            </Typography.Text>
          </Space>
        </Descriptions.Item>
      </Descriptions>
    </section>
  );
}
