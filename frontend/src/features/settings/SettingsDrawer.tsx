import { CopyOutlined, SettingOutlined } from "@ant-design/icons";
import { Alert, Button, Descriptions, Drawer, QRCode, Space, Switch, Typography } from "antd";

import type { RuntimeInfo, ThemeSettings } from "../../api/types";

interface SettingsDrawerProps {
  open: boolean;
  settings: ThemeSettings;
  runtime: RuntimeInfo | null;
  saving: boolean;
  onClose: () => void;
  onLANChange: (enabled: boolean) => void;
}

export function SettingsDrawer({
  open,
  settings,
  runtime,
  saving,
  onClose,
  onLANChange,
}: SettingsDrawerProps) {
  const lanActive = runtime?.mode === "LAN";
  return (
    <Drawer
      title={
        <Space>
          <SettingOutlined />
          设置
        </Space>
      }
      width="min(94vw, 480px)"
      open={open}
      onClose={onClose}
    >
      <section className="settings-section" aria-labelledby="lan-settings-title">
        <Typography.Title level={3} id="lan-settings-title">
          局域网访问
        </Typography.Title>
        <div className="settings-switch-row">
          <div>
            <Typography.Text strong>允许局域网设备访问</Typography.Text>
            <Typography.Paragraph type="secondary">
              默认关闭。仅应在可信的私人网络中使用。
            </Typography.Paragraph>
          </div>
          <Switch
            checked={Boolean(settings.lan_enabled)}
            loading={saving}
            onChange={onLANChange}
            aria-label="允许局域网设备访问"
          />
        </div>
        {Boolean(settings.lan_enabled) !== lanActive ? (
          <Alert
            type="info"
            showIcon
            title="该设置将在下次启动 QuantLab 时生效。"
            className="settings-alert"
          />
        ) : null}
        {lanActive && runtime?.lan_url && runtime.pairing_code ? (
          <div className="lan-pairing-panel">
            <QRCode value={runtime.lan_url} size={180} bordered={false} />
            <Descriptions column={1} size="small">
              <Descriptions.Item label="局域网地址">
                <Typography.Text copyable={{ icon: <CopyOutlined /> }}>
                  {runtime.lan_url}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="本次配对码">
                <Typography.Text copyable strong className="pairing-code">
                  {runtime.pairing_code}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
            <Alert
              type="warning"
              showIcon
              title="Windows 防火墙询问时，只允许专用网络，不建议允许公用网络。"
            />
          </div>
        ) : null}
        {!lanActive && settings.lan_enabled ? <Button onClick={onClose}>完成设置</Button> : null}
      </section>
    </Drawer>
  );
}
