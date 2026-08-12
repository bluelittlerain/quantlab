import { PlayCircleOutlined, QuestionCircleOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Collapse,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import { useCallback, useEffect, useState } from "react";

import type { QuantLabApiError } from "../../api/client";
import type { BacktestRequest, SymbolMetadataResponse } from "../../api/types";
import { DEFAULT_BENCHMARK_COSTS, DEFAULT_HK_COSTS } from "./defaults";

interface FormValues {
  symbol: string;
  benchmarkSymbol: string;
  dateRange: [Dayjs, Dayjs];
  shortWindow: number;
  longWindow: number;
  initialCapital: number;
  boardLot: number;
  benchmarkBoardLot: number;
  commissionPercent: number;
  minimumCommission: number;
  stampDutyPercent: number;
  tradingFeePercent: number;
  transactionLevyPercent: number;
  afrcLevyPercent: number;
  settlementFeePercent: number;
  slippagePercent: number;
  useDefaultStatutoryCosts: boolean;
}

type LotSource = "AUTO" | "USER" | "UNKNOWN";

interface BacktestFormProps {
  loading: boolean;
  onRun: (request: BacktestRequest) => void;
  onDraftChange?: () => void;
  initialRequest?: BacktestRequest | null;
  recentSymbols?: string[];
  apiError?: QuantLabApiError | null;
  resolveSymbol?: (symbol: string) => Promise<SymbolMetadataResponse>;
}

const API_TO_FORM_FIELD: Record<string, keyof FormValues> = {
  symbol: "symbol",
  benchmark_symbol: "benchmarkSymbol",
  start_date: "dateRange",
  end_date: "dateRange",
  short_window: "shortWindow",
  long_window: "longWindow",
  initial_capital: "initialCapital",
  board_lot: "boardLot",
  benchmark_board_lot: "benchmarkBoardLot",
  "costs.broker_commission_rate": "commissionPercent",
  "costs.broker_minimum_commission": "minimumCommission",
  "costs.stamp_duty_rate": "stampDutyPercent",
  "costs.trading_fee_rate": "tradingFeePercent",
  "costs.transaction_levy_rate": "transactionLevyPercent",
  "costs.afrc_transaction_levy_rate": "afrcLevyPercent",
  "costs.settlement_fee_rate": "settlementFeePercent",
  "costs.slippage_rate": "slippagePercent",
};

const sectionTitle = (title: string) => (
  <Typography.Text className="form-section-title">{title}</Typography.Text>
);

const helpLabel = (label: string, help: string) => (
  <Space size={5}>
    <span>{label}</span>
    <Tooltip title={help} placement="topLeft">
      <QuestionCircleOutlined aria-label={`${label}说明`} />
    </Tooltip>
  </Space>
);

function formValuesFromRequest(request: BacktestRequest): Partial<FormValues> {
  return {
    symbol: request.symbol,
    benchmarkSymbol: request.benchmark_symbol,
    dateRange: [dayjs(request.start_date), dayjs(request.end_date)],
    shortWindow: request.short_window,
    longWindow: request.long_window,
    initialCapital: request.initial_capital,
    boardLot: request.board_lot.lot_size,
    benchmarkBoardLot: request.benchmark_board_lot.lot_size,
    commissionPercent: request.costs.broker_commission_rate * 100,
    minimumCommission: request.costs.broker_minimum_commission,
    stampDutyPercent: request.costs.stamp_duty_rate * 100,
    tradingFeePercent: request.costs.trading_fee_rate * 100,
    transactionLevyPercent: request.costs.transaction_levy_rate * 100,
    afrcLevyPercent: request.costs.afrc_transaction_levy_rate * 100,
    settlementFeePercent: request.costs.settlement_fee_rate * 100,
    slippagePercent: request.costs.slippage_rate * 100,
    useDefaultStatutoryCosts:
      request.costs.stamp_duty_rate === DEFAULT_HK_COSTS.stamp_duty_rate &&
      request.costs.trading_fee_rate === DEFAULT_HK_COSTS.trading_fee_rate &&
      request.costs.transaction_levy_rate === DEFAULT_HK_COSTS.transaction_levy_rate &&
      request.costs.afrc_transaction_levy_rate === DEFAULT_HK_COSTS.afrc_transaction_levy_rate &&
      request.costs.settlement_fee_rate === DEFAULT_HK_COSTS.settlement_fee_rate,
  };
}

function lotSourceTag(source: LotSource) {
  if (source === "AUTO") return <Tag color="blue">自动获取</Tag>;
  if (source === "USER") return <Tag color="green">用户确认</Tag>;
  return <Tag>待确认</Tag>;
}

export function BacktestForm({
  loading,
  onRun,
  onDraftChange,
  initialRequest,
  recentSymbols = [],
  apiError,
  resolveSymbol,
}: BacktestFormProps) {
  const [form] = Form.useForm<FormValues>();
  const [lotSources, setLotSources] = useState<Record<"symbol" | "benchmark", LotSource>>({
    symbol: "UNKNOWN",
    benchmark: "UNKNOWN",
  });

  useEffect(() => {
    if (initialRequest) form.setFieldsValue(formValuesFromRequest(initialRequest));
  }, [form, initialRequest]);

  useEffect(() => {
    if (!apiError?.field) return;
    const field = API_TO_FORM_FIELD[apiError.field];
    if (!field) return;
    form.setFields([{ name: field, errors: [apiError.message] }]);
    window.setTimeout(() => {
      form.scrollToField(field, { focus: true, block: "center" });
    }, 0);
  }, [apiError, form]);

  const inspectSymbol = useCallback(
    async (kind: "symbol" | "benchmark") => {
      if (!resolveSymbol) return;
      const symbolField = kind === "symbol" ? "symbol" : "benchmarkSymbol";
      const lotField = kind === "symbol" ? "boardLot" : "benchmarkBoardLot";
      const raw = form.getFieldValue(symbolField)?.trim();
      if (!raw) return;
      const inputStillMatches = () =>
        form.getFieldValue(symbolField)?.trim().toUpperCase() === raw.toUpperCase();
      try {
        const metadata = await resolveSymbol(raw);
        if (!inputStillMatches()) return;
        form.setFieldValue(symbolField, metadata.symbol.normalized_symbol);
        if (metadata.board_lot) {
          form.setFieldValue(lotField, metadata.board_lot.lot_size);
          setLotSources((current) => ({
            ...current,
            [kind]: metadata.board_lot?.source ?? "UNKNOWN",
          }));
        } else {
          setLotSources((current) => ({ ...current, [kind]: "UNKNOWN" }));
        }
      } catch {
        if (!inputStillMatches()) return;
        setLotSources((current) => ({ ...current, [kind]: "UNKNOWN" }));
      }
    },
    [form, resolveSymbol],
  );

  function submit(values: FormValues) {
    const statutory = values.useDefaultStatutoryCosts
      ? DEFAULT_HK_COSTS
      : {
          stamp_duty_rate: values.stampDutyPercent / 100,
          trading_fee_rate: values.tradingFeePercent / 100,
          transaction_levy_rate: values.transactionLevyPercent / 100,
          afrc_transaction_levy_rate: values.afrcLevyPercent / 100,
          settlement_fee_rate: values.settlementFeePercent / 100,
        };
    onRun({
      symbol: values.symbol,
      benchmark_symbol: values.benchmarkSymbol,
      start_date: values.dateRange[0].format("YYYY-MM-DD"),
      end_date: values.dateRange[1].format("YYYY-MM-DD"),
      short_window: values.shortWindow,
      long_window: values.longWindow,
      initial_capital: values.initialCapital,
      board_lot: { lot_size: values.boardLot, confirmed: true },
      benchmark_board_lot: { lot_size: values.benchmarkBoardLot, confirmed: true },
      costs: {
        broker_commission_rate: values.commissionPercent / 100,
        broker_minimum_commission: values.minimumCommission,
        stamp_duty_rate: statutory.stamp_duty_rate,
        trading_fee_rate: statutory.trading_fee_rate,
        transaction_levy_rate: statutory.transaction_levy_rate,
        afrc_transaction_levy_rate: statutory.afrc_transaction_levy_rate,
        settlement_fee_rate: statutory.settlement_fee_rate,
        slippage_rate: values.slippagePercent / 100,
      },
      benchmark_costs: {
        ...DEFAULT_BENCHMARK_COSTS,
        broker_commission_rate: values.commissionPercent / 100,
        broker_minimum_commission: values.minimumCommission,
        trading_fee_rate: statutory.trading_fee_rate,
        transaction_levy_rate: statutory.transaction_levy_rate,
        afrc_transaction_levy_rate: statutory.afrc_transaction_levy_rate,
        settlement_fee_rate: statutory.settlement_fee_rate,
        slippage_rate: values.slippagePercent / 100,
      },
    });
  }

  return (
    <Form<FormValues>
      form={form}
      layout="vertical"
      requiredMark={false}
      initialValues={{
        symbol: "0700.HK",
        benchmarkSymbol: "2800.HK",
        dateRange: [dayjs("2020-01-01"), dayjs("2024-12-31")],
        shortWindow: 20,
        longWindow: 60,
        initialCapital: 100_000,
        boardLot: 100,
        benchmarkBoardLot: 500,
        commissionPercent: DEFAULT_HK_COSTS.broker_commission_rate * 100,
        minimumCommission: DEFAULT_HK_COSTS.broker_minimum_commission,
        stampDutyPercent: DEFAULT_HK_COSTS.stamp_duty_rate * 100,
        tradingFeePercent: DEFAULT_HK_COSTS.trading_fee_rate * 100,
        transactionLevyPercent: DEFAULT_HK_COSTS.transaction_levy_rate * 100,
        afrcLevyPercent: DEFAULT_HK_COSTS.afrc_transaction_levy_rate * 100,
        settlementFeePercent: DEFAULT_HK_COSTS.settlement_fee_rate * 100,
        slippagePercent: DEFAULT_HK_COSTS.slippage_rate * 100,
        useDefaultStatutoryCosts: true,
      }}
      onFinish={submit}
      onValuesChange={onDraftChange}
      onFinishFailed={({ errorFields }) => {
        const first = errorFields[0]?.name;
        if (first) form.scrollToField(first, { focus: true, block: "center" });
      }}
      aria-label="港股回测参数"
    >
      {sectionTitle("标的")}
      <Form.Item
        name="symbol"
        label="港股代码"
        normalize={(value: string) => value.trim().toUpperCase()}
        rules={[{ required: true, message: "请输入港股代码" }]}
      >
        <Input
          placeholder="例如 0700.HK"
          autoComplete="off"
          onFocus={() => void inspectSymbol("symbol")}
          onBlur={() => void inspectSymbol("symbol")}
        />
      </Form.Item>
      {recentSymbols.length ? (
        <div className="recent-symbols" aria-label="最近标的">
          <Typography.Text type="secondary">最近：</Typography.Text>
          {recentSymbols.map((symbol) => (
            <Button
              key={symbol}
              type="link"
              size="small"
              onClick={() => {
                form.setFieldValue("symbol", symbol);
                void inspectSymbol("symbol");
              }}
            >
              {symbol}
            </Button>
          ))}
        </div>
      ) : null}
      <Form.Item
        name="benchmarkSymbol"
        label="比较基准"
        normalize={(value: string) => value.trim().toUpperCase()}
        rules={[{ required: true, message: "请输入比较基准" }]}
        extra="默认使用可交易的 2800.HK 盈富基金，不等同于恒生指数。"
      >
        <Input
          autoComplete="off"
          onFocus={() => void inspectSymbol("benchmark")}
          onBlur={() => void inspectSymbol("benchmark")}
        />
      </Form.Item>

      <Divider />
      {sectionTitle("时间")}
      <Form.Item
        name="dateRange"
        label="分析日期"
        rules={[{ required: true, message: "请选择分析日期" }]}
      >
        <DatePicker.RangePicker allowClear={false} format="YYYY-MM-DD" style={{ width: "100%" }} />
      </Form.Item>

      <Divider />
      {sectionTitle("策略")}
      <div className="form-grid two-columns">
        <Form.Item name="shortWindow" label="短均线" rules={[{ required: true }]}>
          <InputNumber min={1} precision={0} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item
          name="longWindow"
          label="长均线"
          dependencies={["shortWindow"]}
          rules={[
            { required: true },
            ({ getFieldValue }) => ({
              validator(_, value: number) {
                return value > getFieldValue("shortWindow")
                  ? Promise.resolve()
                  : Promise.reject(new Error("长均线必须大于短均线"));
              },
            }),
          ]}
        >
          <InputNumber min={2} precision={0} style={{ width: "100%" }} />
        </Form.Item>
      </div>

      <Divider />
      {sectionTitle("资金与整手")}
      <Form.Item name="initialCapital" label="初始资金" rules={[{ required: true }]}>
        <InputNumber
          addonBefore="HK$"
          min={1}
          precision={0}
          step={10_000}
          style={{ width: "100%" }}
        />
      </Form.Item>
      <div className="form-grid two-columns">
        <Form.Item
          name="boardLot"
          label={<Space size={6}>每手股数 {lotSourceTag(lotSources.symbol)}</Space>}
          rules={[{ required: true, message: "请确认标的每手股数" }]}
        >
          <InputNumber
            min={1}
            precision={0}
            style={{ width: "100%" }}
            onChange={() => setLotSources((current) => ({ ...current, symbol: "USER" }))}
          />
        </Form.Item>
        <Form.Item
          name="benchmarkBoardLot"
          label={<Space size={6}>基准每手 {lotSourceTag(lotSources.benchmark)}</Space>}
          rules={[{ required: true, message: "请确认基准每手股数" }]}
        >
          <InputNumber
            min={1}
            precision={0}
            style={{ width: "100%" }}
            onChange={() => setLotSources((current) => ({ ...current, benchmark: "USER" }))}
          />
        </Form.Item>
      </div>
      {lotSources.symbol === "UNKNOWN" || lotSources.benchmark === "UNKNOWN" ? (
        <Alert
          type="info"
          showIcon
          title="无法自动确认每手股数，请核对后运行。"
          className="lot-alert"
        />
      ) : null}

      <Divider />
      {sectionTitle("券商费用")}
      <div className="form-grid two-columns cost-grid">
        <Form.Item name="commissionPercent" label="佣金率">
          <InputNumber addonAfter="%" min={0} precision={5} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="minimumCommission" label="最低佣金">
          <InputNumber addonBefore="HK$" min={0} precision={2} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="slippagePercent" label="滑点">
          <InputNumber addonAfter="%" min={0} precision={5} style={{ width: "100%" }} />
        </Form.Item>
      </div>

      <Collapse
        className="cost-collapse"
        items={[
          {
            key: "statutory",
            label: "港股法定费用",
            extra: (
              <Form.Item name="useDefaultStatutoryCosts" valuePropName="checked" noStyle>
                <Switch
                  checkedChildren="默认"
                  unCheckedChildren="自定义"
                  onClick={(_, event) => event.stopPropagation()}
                  aria-label="使用默认港股法定费用"
                />
              </Form.Item>
            ),
            children: (
              <Form.Item noStyle shouldUpdate>
                {({ getFieldValue }) =>
                  getFieldValue("useDefaultStatutoryCosts") ? (
                    <Alert
                      type="success"
                      showIcon
                      title="使用当前港股默认法定费用"
                      description="规则日期：2023-11-17 起的印花税率；其他费率按当前研究规则。"
                    />
                  ) : (
                    <div className="form-grid two-columns cost-grid statutory-grid">
                      <Form.Item
                        name="stampDutyPercent"
                        label={helpLabel("印花税", "按成交金额计提，按港股规则取整。")}
                      >
                        <InputNumber addonAfter="%" min={0} precision={5} />
                      </Form.Item>
                      <Form.Item
                        name="tradingFeePercent"
                        label={helpLabel("交易费", "香港交易所交易费。")}
                      >
                        <InputNumber addonAfter="%" min={0} precision={6} />
                      </Form.Item>
                      <Form.Item
                        name="transactionLevyPercent"
                        label={helpLabel("证监会征费", "香港证监会交易征费。")}
                      >
                        <InputNumber addonAfter="%" min={0} precision={6} />
                      </Form.Item>
                      <Form.Item
                        name="afrcLevyPercent"
                        label={helpLabel("财汇局征费", "会计及财务汇报局交易征费。")}
                      >
                        <InputNumber addonAfter="%" min={0} precision={6} />
                      </Form.Item>
                      <Form.Item
                        name="settlementFeePercent"
                        label={helpLabel("结算费", "按成交金额计提的结算费用。")}
                      >
                        <InputNumber addonAfter="%" min={0} precision={6} />
                      </Form.Item>
                    </div>
                  )
                }
              </Form.Item>
            ),
          },
        ]}
      />

      <Button
        type="primary"
        htmlType="submit"
        size="large"
        icon={<PlayCircleOutlined />}
        loading={loading}
        block
        className="run-button"
      >
        运行回测
      </Button>
    </Form>
  );
}
