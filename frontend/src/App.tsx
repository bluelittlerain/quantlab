import {
  DoubleLeftOutlined,
  DoubleRightOutlined,
  HistoryOutlined,
  LineChartOutlined,
  MenuOutlined,
  MoreOutlined,
  SaveOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App as AntApp,
  Button,
  Drawer,
  Dropdown,
  Layout,
  Segmented,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import {
  createPreset,
  deleteHistory,
  deletePreset,
  getSymbolMetadata,
  getBacktest,
  getRuntimeInfo,
  getSettings,
  listHistory,
  listPresets,
  listRecentSymbols,
  QuantLabApiError,
  pairLANSession,
  putSettings,
  runBacktest,
  updatePreset,
} from "./api/client";
import type { BacktestRequest, BacktestResult, ThemeSettings } from "./api/types";
import { AdvancedMetrics } from "./features/backtest/AdvancedMetrics";
import { BacktestForm } from "./features/backtest/BacktestForm";
import { DataReproPanel } from "./features/backtest/DataReproPanel";
import { EquityChart } from "./features/backtest/EquityChart";
import { Overview } from "./features/backtest/Overview";
import { CostChart, DrawdownChart, PriceChart } from "./features/backtest/ResearchCharts";
import { TradeTable } from "./features/backtest/TradeTable";
import { ExportPanel } from "./features/exports/ExportPanel";
import { HistoryDrawer } from "./features/history/HistoryDrawer";
import { PresetDrawer } from "./features/presets/PresetDrawer";
import { PairingGate } from "./features/settings/PairingGate";
import { SettingsDrawer } from "./features/settings/SettingsDrawer";
import { requestFromResult } from "./lib/backtest";
import { symbolLabel } from "./lib/symbol";
import { useViewportMode } from "./hooks/useViewport";
import "./styles/app.css";
import { ThemeControl } from "./theme/ThemeControl";
import { ThemeProvider } from "./theme/ThemeProvider";
import { useThemeMode } from "./theme/themeContext";

const { Content, Header, Sider } = Layout;

function errorMessage(error: Error | null): string | null {
  if (!error) return null;
  if (error instanceof QuantLabApiError) return error.message;
  return "本地服务连接失败，请稍后重试。";
}

interface RunInput {
  request: BacktestRequest;
  forceRefresh: boolean;
}

function ChartSection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="chart-section">
      <div className="section-heading compact">
        <div>
          <Typography.Title level={2}>{title}</Typography.Title>
          <Typography.Text type="secondary">{description}</Typography.Text>
        </div>
      </div>
      {children}
    </section>
  );
}

function ResultWorkspace({
  result,
  activeTab,
  onTabChange,
  refreshing,
  onRefresh,
  mobile,
}: {
  result: BacktestResult;
  activeTab: string;
  onTabChange: (key: string) => void;
  refreshing: boolean;
  onRefresh: () => void;
  mobile: boolean;
}) {
  type MobileChart = "price" | "equity" | "drawdown" | "costs";
  const [mobileChart, setMobileChart] = useState<MobileChart>("equity");
  const mobileChartContent = (
    {
      price: <PriceChart result={result} />,
      equity: <EquityChart result={result} />,
      drawdown: <DrawdownChart result={result} />,
      costs: <CostChart result={result} />,
    } satisfies Record<MobileChart, React.ReactNode>
  )[mobileChart];
  const desktopItems = [
    {
      key: "price",
      label: "行情与信号",
      children: (
        <ChartSection title="价格、均线与成交" description="调整后收盘价、双均线信号与实际成交标记">
          <PriceChart result={result} />
        </ChartSection>
      ),
    },
    {
      key: "equity",
      label: "净值与回撤",
      children: (
        <Space orientation="vertical" size={24} className="result-stack">
          <ChartSection title="净值对比" description="策略与可交易基准采用相同初始资金和执行原则">
            <EquityChart result={result} />
          </ChartSection>
          <ChartSection title="回撤曲线" description="最大回撤位置由后端权益序列直接呈现">
            <DrawdownChart result={result} />
          </ChartSection>
        </Space>
      ),
    },
  ];
  const mobileChartItem = {
    key: "charts",
    label: "图表",
    children: (
      <section className="chart-section mobile-chart-section">
        <Segmented<MobileChart>
          block
          value={mobileChart}
          onChange={setMobileChart}
          aria-label="图表选择"
          options={[
            { value: "price", label: "行情" },
            { value: "equity", label: "净值" },
            { value: "drawdown", label: "回撤" },
            { value: "costs", label: "成本" },
          ]}
        />
        <div className="mobile-chart-canvas">{mobileChartContent}</div>
      </section>
    ),
  };
  return (
    <div className="result-workspace">
      <div className="result-context">
        <div>
          <Space wrap>
            <Typography.Title level={1}>{result.symbol.normalized_symbol}</Typography.Title>
            <Tag>{result.strategy.name}</Tag>
            <Tag color={result.market_data.cache_status === "CACHE" ? "blue" : "green"}>
              {result.market_data.cache_status === "CACHE" ? "数据已缓存" : "数据已刷新"}
            </Tag>
          </Space>
          <Typography.Text type="secondary">
            {result.date_range.actual_start} 至 {result.date_range.actual_end} · 比较基准
            {` ${symbolLabel(result.benchmark)}`}
          </Typography.Text>
        </div>
      </div>
      {result.warnings.length ? (
        <Alert
          type="warning"
          showIcon
          title="本次运行有需要留意的事项"
          description={result.warnings.join("；")}
          className="workspace-alert"
        />
      ) : null}
      <Tabs
        activeKey={activeTab}
        onChange={onTabChange}
        destroyOnHidden
        className="result-tabs"
        items={[
          {
            key: "overview",
            label: "概览",
            children: <Overview result={result} />,
          },
          ...(mobile ? [mobileChartItem] : desktopItems),
          {
            key: "trades",
            label: "交易记录",
            children: <TradeTable trades={result.trades} mobile={mobile} />,
          },
          {
            key: "risk",
            label: "风险与成本",
            children: (
              <Space orientation="vertical" size={24} className="result-stack">
                <AdvancedMetrics metrics={result.strategy_metrics} />
                <ChartSection title="交易成本" description="实际成交产生的累计成本分项">
                  <CostChart result={result} />
                </ChartSection>
              </Space>
            ),
          },
          {
            key: "data",
            label: "数据与复现",
            children: (
              <DataReproPanel result={result} refreshing={refreshing} onRefresh={onRefresh} />
            ),
          },
          {
            key: "export",
            label: "导出",
            children: <ExportPanel key={result.run_id} runId={result.run_id} />,
          },
        ]}
      />
    </div>
  );
}

function QuantLabWorkspace() {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const viewport = useViewportMode();
  const mobile = viewport === "mobile";
  const { mode: themeMode, setMode: setThemeMode } = useThemeMode();
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [currentRequest, setCurrentRequest] = useState<BacktestRequest | null>(null);
  const [formSeed, setFormSeed] = useState<BacktestRequest | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [parametersCollapsed, setParametersCollapsed] = useState(
    () => localStorage.getItem("quantlab.parameters-collapsed") === "true",
  );
  const [draftChanged, setDraftChanged] = useState(false);
  const [parametersOpen, setParametersOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const runtimeQuery = useQuery({ queryKey: ["runtime"], queryFn: getRuntimeInfo });
  const runtimeAuthenticated = runtimeQuery.data?.authenticated === true;
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    enabled: runtimeAuthenticated,
  });
  const historyQuery = useQuery({
    queryKey: ["history"],
    queryFn: listHistory,
    enabled: runtimeAuthenticated,
  });
  const presetsQuery = useQuery({
    queryKey: ["presets"],
    queryFn: listPresets,
    enabled: runtimeAuthenticated,
  });
  const recentQuery = useQuery({
    queryKey: ["recent-symbols"],
    queryFn: listRecentSymbols,
    enabled: runtimeAuthenticated,
  });

  const runMutation = useMutation({
    mutationFn: ({ request, forceRefresh }: RunInput) => runBacktest(request, { forceRefresh }),
    onSuccess: (nextResult, input) => {
      setResult(nextResult);
      setCurrentRequest(input.request);
      setFormSeed(input.request);
      setDraftChanged(false);
      setParametersOpen(false);
      setActiveTab("overview");
      void queryClient.invalidateQueries({ queryKey: ["history"] });
      void queryClient.invalidateQueries({ queryKey: ["recent-symbols"] });
      void message.success(input.forceRefresh ? "行情已刷新并完成回测" : "回测已完成");
    },
  });

  const openRunMutation = useMutation({
    mutationFn: getBacktest,
    onSuccess: (storedResult) => {
      const request = requestFromResult(storedResult);
      setResult(storedResult);
      setCurrentRequest(request);
      setFormSeed(request);
      setDraftChanged(false);
      setHistoryOpen(false);
      setActiveTab("overview");
      void message.success("已打开本地运行，不需要重新下载行情");
    },
  });

  const deleteRunMutation = useMutation({
    mutationFn: deleteHistory,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["history"] }),
  });

  const savePresetMutation = useMutation({
    mutationFn: createPreset,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["presets"] });
      void message.success("预设已保存在本机");
    },
  });

  const deletePresetMutation = useMutation({
    mutationFn: deletePreset,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["presets"] }),
  });

  const updatePresetMutation = useMutation({
    mutationFn: ({ id, name, payload }: { id: number; name: string; payload: BacktestRequest }) =>
      updatePreset(id, { name, payload }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["presets"] });
      void message.success("预设名称已更新");
    },
  });

  const pairingMutation = useMutation({
    mutationFn: pairLANSession,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["runtime"] });
      await queryClient.invalidateQueries({ queryKey: ["history"] });
      await queryClient.invalidateQueries({ queryKey: ["presets"] });
      await queryClient.invalidateQueries({ queryKey: ["recent-symbols"] });
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const settingsMutation = useMutation({
    mutationFn: (settings: ThemeSettings) => putSettings(settings),
    onSuccess: (settings) => {
      queryClient.setQueryData(["settings"], settings);
      void message.success("局域网设置已保存");
    },
  });

  const visibleError = runMutation.error ?? openRunMutation.error;
  const changeParametersCollapsed = (collapsed: boolean) => {
    localStorage.setItem("quantlab.parameters-collapsed", String(collapsed));
    setParametersCollapsed(collapsed);
  };
  const parameterForm = (
    <BacktestForm
      loading={runMutation.isPending}
      initialRequest={formSeed}
      recentSymbols={recentQuery.data}
      apiError={runMutation.error instanceof QuantLabApiError ? runMutation.error : null}
      resolveSymbol={getSymbolMetadata}
      onDraftChange={() => {
        runMutation.reset();
        if (result) setDraftChanged(true);
      }}
      onRun={(request) => {
        runMutation.reset();
        runMutation.mutate({ request, forceRefresh: false });
      }}
    />
  );

  const mobileMoreItems = [
    { key: "presets", icon: <SaveOutlined />, label: "预设" },
    { key: "settings", icon: <SettingOutlined />, label: "设置" },
    { type: "divider" as const },
    { key: "SYSTEM", label: "外观：跟随系统" },
    { key: "LIGHT", label: "外观：浅色" },
    { key: "DARK", label: "外观：深色" },
  ];

  if (runtimeQuery.data?.authenticated === false) {
    return (
      <PairingGate
        loading={pairingMutation.isPending}
        error={errorMessage(pairingMutation.error)}
        onPair={(code) => pairingMutation.mutate(code)}
      />
    );
  }

  return (
    <Layout className="app-shell">
      <Header className="product-header">
        <Space size={12} align="center" className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            Q
          </div>
          <div className="brand-copy">
            <Typography.Title level={1}>QuantLab</Typography.Title>
            <Typography.Text>港股日线研究与回测工具</Typography.Text>
          </div>
        </Space>
        {mobile ? (
          <Space className="header-actions mobile-header-actions" size={4}>
            <Button
              type="text"
              icon={<MenuOutlined />}
              onClick={() => setParametersOpen(true)}
              aria-label="参数"
            >
              参数
            </Button>
            <Button
              type="text"
              icon={<HistoryOutlined />}
              onClick={() => setHistoryOpen(true)}
              aria-label="历史"
            >
              历史
            </Button>
            <Dropdown
              trigger={["click"]}
              placement="bottomRight"
              menu={{
                items: mobileMoreItems,
                selectable: true,
                selectedKeys: [themeMode],
                onClick: ({ key }) => {
                  if (key === "presets") setPresetsOpen(true);
                  if (key === "settings") setSettingsOpen(true);
                  if (key === "SYSTEM" || key === "LIGHT" || key === "DARK") setThemeMode(key);
                },
              }}
            >
              <Button type="text" icon={<MoreOutlined />} aria-label="更多">
                更多
              </Button>
            </Dropdown>
          </Space>
        ) : (
          <Space className="header-actions" wrap>
            <Button icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
              历史
            </Button>
            <Button icon={<SaveOutlined />} onClick={() => setPresetsOpen(true)}>
              预设
            </Button>
            <Button icon={<SettingOutlined />} onClick={() => setSettingsOpen(true)}>
              设置
            </Button>
            <ThemeControl />
          </Space>
        )}
      </Header>
      <Layout>
        {!mobile ? (
          <Sider
            width={viewport === "tablet" ? 320 : 368}
            collapsedWidth={0}
            collapsed={parametersCollapsed}
            trigger={null}
            className="parameter-sider"
            theme="light"
          >
            <div className="parameter-heading">
              <div>
                <Typography.Title level={2}>研究参数</Typography.Title>
                <Typography.Text type="secondary">
                  修改参数后，点击运行才会开始计算。
                </Typography.Text>
              </div>
              <Button
                type="text"
                icon={<DoubleLeftOutlined />}
                onClick={() => changeParametersCollapsed(true)}
                aria-label="收起参数"
              >
                收起
              </Button>
            </div>
            {parameterForm}
          </Sider>
        ) : null}
        <Content className="workspace-content">
          {parametersCollapsed && !mobile ? (
            <Button
              className="parameter-restore"
              icon={<DoubleRightOutlined />}
              onClick={() => changeParametersCollapsed(false)}
              aria-label="展开参数"
            >
              展开参数
            </Button>
          ) : null}
          {errorMessage(visibleError) ? (
            <Alert
              type="error"
              showIcon
              closable
              title="操作未完成"
              description={errorMessage(visibleError)}
              className="workspace-alert"
            />
          ) : null}
          {result && draftChanged && !runMutation.isPending ? (
            <Alert
              type="info"
              showIcon
              title="参数已修改，当前结果来自上一次运行。"
              description="点击左侧“运行回测”后，结果才会使用新参数。"
              className="workspace-alert"
            />
          ) : null}
          {!result && !runMutation.isPending ? (
            <div className="empty-workspace">
              <div>
                <LineChartOutlined className="empty-icon" />
                <Typography.Title level={2}>开始一次港股趋势研究</Typography.Title>
                <Typography.Text type="secondary">
                  确认左侧标的、整手股数和成本参数后运行。
                </Typography.Text>
              </div>
            </div>
          ) : null}
          {runMutation.isPending ? (
            <div className="loading-workspace" role="status" aria-live="polite">
              <div>
                <div className="loading-pulse" aria-hidden="true" />
                <Typography.Title level={2}>正在执行港股回测</Typography.Title>
                <Typography.Text type="secondary">正在获取行情并核算整手交易成本…</Typography.Text>
              </div>
            </div>
          ) : null}
          {result && !runMutation.isPending ? (
            <ResultWorkspace
              result={result}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              refreshing={runMutation.isPending}
              onRefresh={() => {
                if (currentRequest) {
                  runMutation.mutate({ request: currentRequest, forceRefresh: true });
                }
              }}
              mobile={mobile}
            />
          ) : null}
        </Content>
      </Layout>
      {mobile ? (
        <Drawer
          title="研究参数"
          placement="left"
          width="min(94vw, 420px)"
          open={parametersOpen}
          onClose={() => setParametersOpen(false)}
          className="mobile-parameter-drawer"
        >
          {parameterForm}
        </Drawer>
      ) : null}
      <HistoryDrawer
        open={historyOpen}
        items={historyQuery.data ?? []}
        loading={historyQuery.isPending || openRunMutation.isPending}
        onClose={() => setHistoryOpen(false)}
        onOpenRun={(runId) => openRunMutation.mutate(runId)}
        onDelete={(runId) => deleteRunMutation.mutate(runId)}
      />
      <PresetDrawer
        open={presetsOpen}
        items={presetsQuery.data ?? []}
        currentRequest={currentRequest}
        loading={presetsQuery.isPending}
        onClose={() => setPresetsOpen(false)}
        onSave={(name, request) => savePresetMutation.mutate({ name, payload: request })}
        onLoad={(request) => {
          setFormSeed({ ...request });
          setDraftChanged(Boolean(result));
          setPresetsOpen(false);
          void message.success("预设已载入，点击运行回测后才会执行");
        }}
        onRename={(id, name, payload) => updatePresetMutation.mutate({ id, name, payload })}
        onDelete={(presetId) => deletePresetMutation.mutate(presetId)}
      />
      <SettingsDrawer
        open={settingsOpen}
        settings={settingsQuery.data ?? {}}
        runtime={runtimeQuery.data ?? null}
        saving={settingsMutation.isPending}
        onClose={() => setSettingsOpen(false)}
        onLANChange={(enabled) => settingsMutation.mutate({ lan_enabled: enabled })}
      />
    </Layout>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AntApp>
        <QuantLabWorkspace />
      </AntApp>
    </ThemeProvider>
  );
}
