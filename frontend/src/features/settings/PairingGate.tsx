import { LockOutlined } from "@ant-design/icons";
import { Alert, Button, Form, Input, Typography } from "antd";

interface PairingGateProps {
  loading: boolean;
  error: string | null;
  onPair: (code: string) => void;
}

export function PairingGate({ loading, error, onPair }: PairingGateProps) {
  return (
    <main className="pairing-gate">
      <section className="pairing-card" aria-labelledby="pairing-title">
        <LockOutlined className="pairing-icon" />
        <Typography.Title level={1} id="pairing-title">
          配对 QuantLab
        </Typography.Title>
        <Typography.Paragraph type="secondary">
          在桌面端“设置”中查看本次启动的 6 位配对码。
        </Typography.Paragraph>
        {error ? <Alert type="error" showIcon title={error} /> : null}
        <Form<{ code: string }>
          layout="vertical"
          onFinish={({ code }) => onPair(code)}
          requiredMark={false}
        >
          <Form.Item
            name="code"
            label="配对码"
            rules={[
              { required: true, message: "请输入 6 位配对码" },
              { pattern: /^\d{6}$/, message: "配对码必须是 6 位数字" },
            ]}
          >
            <Input inputMode="numeric" maxLength={6} autoComplete="one-time-code" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            连接
          </Button>
        </Form>
      </section>
    </main>
  );
}
