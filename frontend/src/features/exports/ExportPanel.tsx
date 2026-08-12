import { DownloadOutlined, FileZipOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Button, Card, List, Space, Tag, Typography } from "antd";
import { useEffect } from "react";

import { exportUrl, prepareExport } from "../../api/client";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export function ExportPanel({ runId }: { runId: string }) {
  const preparation = useMutation({ mutationFn: () => prepareExport(runId) });
  const resetPreparation = preparation.reset;

  useEffect(() => resetPreparation(), [resetPreparation, runId]);

  const files = [
    { key: "report.html", label: "HTML 研究报告" },
    { key: "trades.csv", label: "交易记录 CSV" },
    { key: "manifest.json", label: "复现清单 Manifest" },
    { key: "bundle.zip", label: "全部结果 ZIP", primary: true },
  ];

  return (
    <section aria-labelledby="export-title" className="content-section">
      <div className="section-heading">
        <div>
          <Typography.Title level={2} id="export-title">
            导出研究结果
          </Typography.Title>
          <Typography.Text type="secondary">
            文件只在明确准备后生成，不会触发行情下载或重新回测。
          </Typography.Text>
        </div>
      </div>
      {!preparation.data ? (
        <Card className="export-callout">
          <Space orientation="vertical" size={14}>
            <FileZipOutlined className="export-icon" />
            <Typography.Text>准备 HTML、CSV、Manifest 与统一 ZIP。</Typography.Text>
            <Button
              type="primary"
              icon={<FileZipOutlined />}
              loading={preparation.isPending}
              onClick={() => preparation.mutate()}
            >
              准备导出文件
            </Button>
          </Space>
        </Card>
      ) : (
        <Card>
          <Space wrap className="export-meta">
            <Tag color="success">已准备</Tag>
            <Typography.Text type="secondary">运行标识 {runId}</Typography.Text>
            <Typography.Text type="secondary">
              生成时间 {preparation.data.generated_at_utc}
            </Typography.Text>
          </Space>
          <List
            dataSource={files}
            renderItem={(file) => (
              <List.Item
                actions={[
                  <Button
                    key="download"
                    type={file.primary ? "primary" : "default"}
                    icon={<DownloadOutlined />}
                    href={exportUrl(runId, file.key)}
                  >
                    下载
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={file.label}
                  description={formatBytes(preparation.data.files[file.key] ?? 0)}
                />
              </List.Item>
            )}
          />
        </Card>
      )}
    </section>
  );
}
