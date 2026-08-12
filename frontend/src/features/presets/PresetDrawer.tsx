import { CloseOutlined, DeleteOutlined, EditOutlined, SaveOutlined } from "@ant-design/icons";
import { Button, Drawer, Empty, Input, List, Popconfirm, Space, Typography } from "antd";
import { useState } from "react";

import type { BacktestRequest, Preset } from "../../api/types";

interface PresetDrawerProps {
  open: boolean;
  items: Preset[];
  currentRequest: BacktestRequest | null;
  loading: boolean;
  onClose: () => void;
  onSave: (name: string, request: BacktestRequest) => void;
  onLoad: (request: BacktestRequest) => void;
  onRename: (presetId: number, name: string, request: BacktestRequest) => void;
  onDelete: (presetId: number) => void;
}

export function PresetDrawer({
  open,
  items,
  currentRequest,
  loading,
  onClose,
  onSave,
  onLoad,
  onRename,
  onDelete,
}: PresetDrawerProps) {
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  return (
    <Drawer
      title="研究预设"
      width="min(94vw, 460px)"
      open={open}
      onClose={onClose}
      loading={loading}
      closeIcon={<CloseOutlined aria-label="关闭" />}
    >
      <Space.Compact block className="preset-create">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="例如：腾讯 SMA 20/60"
          aria-label="预设名称"
        />
        <Button
          type="primary"
          icon={<SaveOutlined />}
          disabled={!currentRequest || !name.trim()}
          onClick={() => {
            if (!currentRequest || !name.trim()) return;
            onSave(name.trim(), currentRequest);
            setName("");
          }}
        >
          保存当前参数
        </Button>
      </Space.Compact>
      {!items.length && !loading ? (
        <Empty description="暂无预设" image={Empty.PRESENTED_IMAGE_SIMPLE}>
          <Typography.Text type="secondary">保存当前参数后，可以快速再次运行。</Typography.Text>
        </Empty>
      ) : (
        <List
          dataSource={items}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Button key="load" type="link" onClick={() => onLoad(item.payload)}>
                  应用
                </Button>,
                <Button
                  key="rename"
                  type="text"
                  icon={<EditOutlined />}
                  aria-label="重命名预设"
                  onClick={() => {
                    setEditing(item.id);
                    setEditingName(item.name);
                  }}
                />,
                <Popconfirm
                  key="delete"
                  title="删除这个预设？"
                  okText="删除"
                  cancelText="取消"
                  onConfirm={() => onDelete(item.id)}
                >
                  <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除预设" />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={
                  editing === item.id ? (
                    <Space.Compact block>
                      <Input
                        value={editingName}
                        onChange={(event) => setEditingName(event.target.value)}
                        aria-label="新的预设名称"
                      />
                      <Button
                        type="primary"
                        onClick={() => {
                          if (!editingName.trim()) return;
                          onRename(item.id, editingName.trim(), item.payload);
                          setEditing(null);
                        }}
                      >
                        保存
                      </Button>
                    </Space.Compact>
                  ) : (
                    <Typography.Text strong>{item.name}</Typography.Text>
                  )
                }
                description={`${item.payload.symbol} · SMA ${item.payload.short_window}/${item.payload.long_window} · ${item.updated_at.replace("T", " ").slice(0, 16)}`}
              />
            </List.Item>
          )}
        />
      )}
    </Drawer>
  );
}
