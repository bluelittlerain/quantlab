import { CloseOutlined, DeleteOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { Button, Drawer, Empty, List, Popconfirm, Space, Tag, Typography } from "antd";

import type { RunHistoryItem } from "../../api/types";
import { formatPercent } from "../../lib/format";

interface HistoryDrawerProps {
  open: boolean;
  items: RunHistoryItem[];
  loading: boolean;
  onClose: () => void;
  onOpenRun: (runId: string) => void;
  onDelete: (runId: string) => void;
}

export function HistoryDrawer({
  open,
  items,
  loading,
  onClose,
  onOpenRun,
  onDelete,
}: HistoryDrawerProps) {
  return (
    <Drawer
      title="本地运行历史"
      width="min(94vw, 480px)"
      open={open}
      onClose={onClose}
      loading={loading}
      closeIcon={<CloseOutlined aria-label="关闭" />}
    >
      {!items.length && !loading ? (
        <Empty description="暂无历史运行" image={Empty.PRESENTED_IMAGE_SIMPLE}>
          <Typography.Text type="secondary">完成一次回测后，结果会自动保存在这里。</Typography.Text>
        </Empty>
      ) : (
        <List
          dataSource={items}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button
                  key="open"
                  type="link"
                  icon={<FolderOpenOutlined />}
                  onClick={() => onOpenRun(item.run_id)}
                >
                  打开
                </Button>,
                <Popconfirm
                  key="delete"
                  title="删除这条本地运行？"
                  okText="删除"
                  cancelText="取消"
                  onConfirm={() => onDelete(item.run_id)}
                >
                  <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除运行" />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  <Space>
                    <Typography.Text strong>{item.symbol}</Typography.Text>
                    <Tag>{formatPercent(item.strategy_metrics.total_return)}</Tag>
                  </Space>
                }
                description={
                  <Space orientation="vertical" size={2}>
                    <Typography.Text type="secondary">
                      {item.date_range.actual_start} 至 {item.date_range.actual_end}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      CAGR {formatPercent(item.strategy_metrics.cagr)} · 最大回撤
                      {` ${formatPercent(item.strategy_metrics.max_drawdown)}`}
                    </Typography.Text>
                    <Typography.Text type="secondary">
                      {item.created_at.replace("T", " ").slice(0, 19)}
                    </Typography.Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      )}
    </Drawer>
  );
}
