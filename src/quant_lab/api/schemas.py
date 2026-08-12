from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(APIModel):
    code: str
    message: str
    field: str | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(APIModel):
    error: ErrorBody


class BoardLotInput(APIModel):
    lot_size: int = Field(gt=0)
    confirmed: bool = True


class BoardLotView(APIModel):
    lot_size: int
    source: Literal["AUTO", "USER"]
    verified_at: datetime | None
    confirmed: bool


class HKCostInput(APIModel):
    broker_commission_rate: float = Field(default=0.00025, ge=0, lt=1)
    broker_minimum_commission: float = Field(default=100.0, ge=0)
    stamp_duty_rate: float = Field(default=0.001, ge=0, lt=1)
    trading_fee_rate: float = Field(default=0.0000565, ge=0, lt=1)
    transaction_levy_rate: float = Field(default=0.000027, ge=0, lt=1)
    afrc_transaction_levy_rate: float = Field(default=0.0000015, ge=0, lt=1)
    settlement_fee_rate: float = Field(default=0.000042, ge=0, lt=1)
    slippage_rate: float = Field(default=0.0005, ge=0, lt=1)
    buy_stamp_duty_rate: float | None = Field(default=None, ge=0, lt=1)
    sell_stamp_duty_rate: float | None = Field(default=None, ge=0, lt=1)


class BacktestRequestModel(APIModel):
    symbol: str = "0700.HK"
    benchmark_symbol: str = "2800.HK"
    start_date: date
    end_date: date
    short_window: int = Field(default=20, gt=0)
    long_window: int = Field(default=60, gt=1)
    initial_capital: float = Field(default=100_000.0, gt=0)
    board_lot: BoardLotInput
    benchmark_board_lot: BoardLotInput
    costs: HKCostInput = Field(default_factory=HKCostInput)
    benchmark_costs: HKCostInput = Field(default_factory=lambda: HKCostInput(stamp_duty_rate=0.0))

    @model_validator(mode="after")
    def validate_period_and_windows(self) -> BacktestRequestModel:
        if self.start_date > self.end_date:
            raise ValueError("结束日期必须晚于开始日期。")
        if self.short_window >= self.long_window:
            raise ValueError("短均线必须小于长均线。")
        if not self.board_lot.confirmed or not self.benchmark_board_lot.confirmed:
            raise ValueError("每手股数必须由用户确认。")
        return self


class SymbolView(APIModel):
    normalized_symbol: str
    exchange: str
    currency: str
    display_name: str | None
    local_alias: str | None


class SymbolResponse(APIModel):
    symbol: SymbolView
    board_lot: BoardLotView | None
    board_lot_requires_confirmation: bool
    provider: str


class DateRangeView(APIModel):
    requested_start: date
    requested_end: date
    actual_start: date
    actual_end: date


class StrategyView(APIModel):
    name: str
    short_window: int
    long_window: int


class MetricsView(APIModel):
    initial_equity: float
    final_equity: float
    total_return: float
    cagr: float | None
    annualized_volatility: float | None
    sharpe_ratio: float | None
    max_drawdown: float
    calmar_ratio: float | None
    market_exposure: float
    turnover: float
    closed_trade_count: int
    open_trade_count: int
    win_rate: float | None
    profit_factor: float | None
    average_trade_return: float | None
    average_holding_period: float | None
    total_trading_costs: float
    total_slippage_cost: float
    cost_to_gross_profit_ratio: float | None


class CostBreakdownView(APIModel):
    broker_commission: float
    stamp_duty: float
    trading_fee: float
    transaction_levy: float
    afrc_transaction_levy: float
    settlement_fee: float
    slippage_cost: float
    total_cost: float


class TradeView(APIModel):
    trade_id: int
    status: Literal["OPEN", "CLOSED"]
    entry_date: date
    entry_raw_price: float
    entry_execution_price: float
    quantity: int
    entry_costs: CostBreakdownView
    exit_date: date | None
    exit_raw_price: float | None
    exit_execution_price: float | None
    exit_costs: CostBreakdownView | None
    mark_date: date | None
    mark_price: float | None
    holding_days: int
    gross_pnl: float
    net_pnl: float
    net_return: float
    total_cost: float


class PricePoint(APIModel):
    date: date
    close: float
    short_sma: float | None
    long_sma: float | None
    action: str


class EquityPoint(APIModel):
    date: date
    strategy_equity: float
    benchmark_equity: float
    excess: float
    drawdown: float


class MarketDataView(APIModel):
    source: str
    source_version: str
    fetched_at_utc: datetime
    cache_status: Literal["LIVE", "CACHE"] = "LIVE"
    data_sha256: str
    adjustment_method: str
    warmup_rows: int
    missing_expected_sessions: list[date]


class BacktestResponseModel(APIModel):
    run_id: str
    created_at_utc: datetime
    symbol: SymbolView
    benchmark: SymbolView
    date_range: DateRangeView
    strategy: StrategyView
    initial_capital: float
    board_lot: BoardLotView
    benchmark_board_lot: BoardLotView
    cost_config: HKCostInput
    benchmark_cost_config: HKCostInput
    strategy_metrics: MetricsView
    benchmark_metrics: MetricsView
    benchmark_return: float
    excess_return: float
    price_series: list[PricePoint]
    equity_series: list[EquityPoint]
    trades: list[TradeView]
    cost_summary: CostBreakdownView
    market_data: MarketDataView
    warnings: list[str]


class PresetInput(APIModel):
    name: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any]


class PresetView(PresetInput):
    id: int
    updated_at: datetime


class SettingsInput(APIModel):
    theme: Literal["SYSTEM", "LIGHT", "DARK"] | None = None
    aliases: dict[str, str] | None = None
    lan_enabled: bool | None = None


class PairingInput(APIModel):
    code: str = Field(pattern=r"^\d{6}$")


class RuntimeView(APIModel):
    mode: Literal["DESKTOP", "LAN", "WEB"]
    authenticated: bool
    pairing_required: bool
    lan_url: str | None
    pairing_code: str | None


class ExportPreparationView(APIModel):
    run_id: str
    generated_at_utc: datetime
    files: dict[str, int]
