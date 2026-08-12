export type ISODate = string;
export type ISODateTime = string;

export interface BoardLotInput {
  lot_size: number;
  confirmed: boolean;
}

export interface BoardLotView extends BoardLotInput {
  source: "AUTO" | "USER";
  verified_at: ISODateTime | null;
}

export interface HKCostInput {
  broker_commission_rate: number;
  broker_minimum_commission: number;
  stamp_duty_rate: number;
  trading_fee_rate: number;
  transaction_levy_rate: number;
  afrc_transaction_levy_rate: number;
  settlement_fee_rate: number;
  slippage_rate: number;
  buy_stamp_duty_rate?: number | null;
  sell_stamp_duty_rate?: number | null;
}

export interface BacktestRequest {
  symbol: string;
  benchmark_symbol: string;
  start_date: ISODate;
  end_date: ISODate;
  short_window: number;
  long_window: number;
  initial_capital: number;
  board_lot: BoardLotInput;
  benchmark_board_lot: BoardLotInput;
  costs: HKCostInput;
  benchmark_costs: HKCostInput;
}

export interface SymbolView {
  normalized_symbol: string;
  exchange: string;
  currency: string;
  display_name: string | null;
  local_alias: string | null;
}

export interface DateRangeView {
  requested_start: ISODate;
  requested_end: ISODate;
  actual_start: ISODate;
  actual_end: ISODate;
}

export interface StrategyView {
  name: string;
  short_window: number;
  long_window: number;
}

export interface PerformanceMetrics {
  initial_equity: number;
  final_equity: number;
  total_return: number;
  cagr: number | null;
  annualized_volatility: number | null;
  sharpe_ratio: number | null;
  max_drawdown: number;
  calmar_ratio: number | null;
  market_exposure: number;
  turnover: number;
  closed_trade_count: number;
  open_trade_count: number;
  win_rate: number | null;
  profit_factor: number | null;
  average_trade_return: number | null;
  average_holding_period: number | null;
  total_trading_costs: number;
  total_slippage_cost: number;
  cost_to_gross_profit_ratio: number | null;
}

export interface CostBreakdown {
  broker_commission: number;
  stamp_duty: number;
  trading_fee: number;
  transaction_levy: number;
  afrc_transaction_levy: number;
  settlement_fee: number;
  slippage_cost: number;
  total_cost: number;
}

export interface Trade {
  trade_id: number;
  status: "OPEN" | "CLOSED";
  entry_date: ISODate;
  entry_raw_price: number;
  entry_execution_price: number;
  quantity: number;
  entry_costs: CostBreakdown;
  exit_date: ISODate | null;
  exit_raw_price: number | null;
  exit_execution_price: number | null;
  exit_costs: CostBreakdown | null;
  mark_date: ISODate | null;
  mark_price: number | null;
  holding_days: number;
  gross_pnl: number;
  net_pnl: number;
  net_return: number;
  total_cost: number;
}

export interface PricePoint {
  date: ISODate;
  close: number;
  short_sma: number | null;
  long_sma: number | null;
  action: string;
}

export interface EquityPoint {
  date: ISODate;
  strategy_equity: number;
  benchmark_equity: number;
  excess: number;
  drawdown: number;
}

export interface MarketDataMetadata {
  source: string;
  source_version: string;
  fetched_at_utc: ISODateTime;
  cache_status: "LIVE" | "CACHE";
  data_sha256: string;
  adjustment_method: string;
  warmup_rows: number;
  missing_expected_sessions: ISODate[];
}

export interface BacktestResult {
  run_id: string;
  created_at_utc: ISODateTime;
  symbol: SymbolView;
  benchmark: SymbolView;
  date_range: DateRangeView;
  strategy: StrategyView;
  initial_capital: number;
  board_lot: BoardLotView;
  benchmark_board_lot: BoardLotView;
  cost_config: HKCostInput;
  benchmark_cost_config: HKCostInput;
  strategy_metrics: PerformanceMetrics;
  benchmark_metrics: PerformanceMetrics;
  benchmark_return: number;
  excess_return: number;
  price_series: PricePoint[];
  equity_series: EquityPoint[];
  trades: Trade[];
  cost_summary: CostBreakdown;
  market_data: MarketDataMetadata;
  warnings: string[];
}

export interface ApiErrorBody {
  code: string;
  message: string;
  field: string | null;
  details: Record<string, unknown> | null;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}

export interface SymbolMetadataResponse {
  symbol: SymbolView;
  board_lot: BoardLotView | null;
  board_lot_requires_confirmation: boolean;
  provider: string;
}

export interface RunHistoryItem {
  run_id: string;
  symbol: string;
  benchmark: string;
  created_at: ISODateTime;
  date_range: DateRangeView;
  strategy_metrics: PerformanceMetrics;
  benchmark_metrics: PerformanceMetrics;
  trade_count: number;
}

export interface Preset {
  id: number;
  name: string;
  payload: BacktestRequest;
  updated_at: ISODateTime;
}

export interface PresetInput {
  name: string;
  payload: BacktestRequest;
}

export type ThemeMode = "SYSTEM" | "LIGHT" | "DARK";

export interface ThemeSettings {
  theme?: ThemeMode;
  aliases?: Record<string, string>;
  lan_enabled?: boolean;
}

export interface RuntimeInfo {
  mode: "DESKTOP" | "LAN" | "WEB";
  authenticated: boolean;
  pairing_required: boolean;
  lan_url: string | null;
  pairing_code: string | null;
}

export interface ExportPreparation {
  run_id: string;
  generated_at_utc: ISODateTime;
  files: Record<string, number>;
}
