from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

import pandas as pd


class ExecutionMode(StrEnum):
    FRACTIONAL = "FRACTIONAL"
    BOARD_LOT = "BOARD_LOT"


class BoardLotSource(StrEnum):
    AUTO = "AUTO"
    USER = "USER"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


HKTradeStatus = Literal["OPEN", "CLOSED"]


@dataclass(frozen=True)
class HKSymbol:
    normalized_symbol: str
    exchange: str = "HKEX"
    currency: str = "HKD"
    display_name: str | None = None
    local_alias: str | None = None

    def __post_init__(self) -> None:
        if not self.normalized_symbol.endswith(".HK"):
            raise ValueError("normalized_symbol must end with .HK.")
        if self.exchange != "HKEX":
            raise ValueError("HKSymbol exchange must be HKEX.")
        if self.currency != "HKD":
            raise ValueError("HKSymbol currency must be HKD.")


@dataclass(frozen=True)
class BoardLotConfig:
    lot_size: int
    source: BoardLotSource
    verified_at: datetime | None
    confirmed: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.lot_size, bool) or not isinstance(self.lot_size, int):
            raise TypeError("lot_size must be an integer.")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be greater than zero.")
        if not isinstance(self.source, BoardLotSource):
            raise TypeError("source must be a BoardLotSource.")
        if self.verified_at is not None and self.verified_at.tzinfo is None:
            raise ValueError("verified_at must be timezone-aware when supplied.")
        if not self.confirmed:
            raise ValueError("board lot must be explicitly confirmed before execution.")


def _validate_rate(field: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)) or not 0 <= value < 1:
        raise ValueError(f"{field} must be finite and satisfy 0 <= {field} < 1.")


@dataclass(frozen=True)
class HKTradingCostConfig:
    broker_commission_rate: float = 0.00025
    broker_minimum_commission: float = 100.0
    stamp_duty_rate: float = 0.001
    trading_fee_rate: float = 0.0000565
    transaction_levy_rate: float = 0.000027
    afrc_transaction_levy_rate: float = 0.0000015
    settlement_fee_rate: float = 0.000042
    slippage_rate: float = 0.0005
    buy_stamp_duty_rate: float | None = None
    sell_stamp_duty_rate: float | None = None

    def __post_init__(self) -> None:
        for field in (
            "broker_commission_rate",
            "stamp_duty_rate",
            "trading_fee_rate",
            "transaction_levy_rate",
            "afrc_transaction_levy_rate",
            "settlement_fee_rate",
            "slippage_rate",
        ):
            _validate_rate(field, float(getattr(self, field)))
        if (
            isinstance(self.broker_minimum_commission, bool)
            or not math.isfinite(float(self.broker_minimum_commission))
            or self.broker_minimum_commission < 0
        ):
            raise ValueError("broker_minimum_commission must be finite and non-negative.")
        for field in ("buy_stamp_duty_rate", "sell_stamp_duty_rate"):
            value = getattr(self, field)
            if value is not None:
                _validate_rate(field, float(value))

    def stamp_rate_for(self, side: TradeSide) -> float:
        override = self.buy_stamp_duty_rate if side is TradeSide.BUY else self.sell_stamp_duty_rate
        return self.stamp_duty_rate if override is None else override


@dataclass(frozen=True)
class CostBreakdown:
    broker_commission: float
    stamp_duty: float
    trading_fee: float
    transaction_levy: float
    afrc_transaction_levy: float
    settlement_fee: float
    slippage_cost: float
    total_cost: float

    @property
    def cash_fee(self) -> float:
        return self.total_cost - self.slippage_cost


@dataclass(frozen=True)
class HKBacktestConfig:
    initial_capital: float
    board_lot: BoardLotConfig
    costs: HKTradingCostConfig
    start_date: date
    end_date: date
    execution_mode: ExecutionMode = ExecutionMode.BOARD_LOT

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.initial_capital)) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be finite and greater than zero.")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be later than end_date.")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode.")


@dataclass(frozen=True)
class HKTradeRecord:
    trade_id: int
    status: HKTradeStatus
    entry_date: date
    entry_raw_price: float
    entry_execution_price: float
    quantity: int
    entry_costs: CostBreakdown
    exit_date: date | None
    exit_raw_price: float | None
    exit_execution_price: float | None
    exit_costs: CostBreakdown | None
    mark_date: date | None
    mark_price: float | None
    holding_days: int
    gross_pnl: float
    net_pnl: float
    net_return: float
    total_cost: float


@dataclass(frozen=True)
class HKPerformanceMetrics:
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


@dataclass(frozen=True)
class HKBacktestResult:
    daily: pd.DataFrame
    trades: tuple[HKTradeRecord, ...]
    metrics: HKPerformanceMetrics
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HKComparisonResult:
    strategy: HKBacktestResult
    benchmark: HKBacktestResult
    benchmark_return: float
    excess_return: float
