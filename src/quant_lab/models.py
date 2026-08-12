from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd

TradeStatus = Literal["OPEN", "CLOSED"]


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 10_000.0
    fee_rate: float = 0.001
    slippage_rate: float = 0.0
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.initial_capital) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be finite and greater than zero.")
        if not math.isfinite(self.fee_rate) or not 0 <= self.fee_rate < 1:
            raise ValueError("fee_rate must be finite and satisfy 0 <= fee_rate < 1.")
        if not math.isfinite(self.slippage_rate) or not 0 <= self.slippage_rate < 1:
            raise ValueError("slippage_rate must be finite and satisfy 0 <= slippage_rate < 1.")
        if self.start_date is not None and not isinstance(self.start_date, date):
            raise TypeError("start_date must be a date or None.")
        if self.end_date is not None and not isinstance(self.end_date, date):
            raise TypeError("end_date must be a date or None.")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not be later than end_date.")


@dataclass(frozen=True)
class TradeRecord:
    trade_id: int
    status: TradeStatus
    entry_date: date
    entry_raw_price: float
    entry_execution_price: float
    quantity: float
    entry_fee: float
    entry_slippage_cost: float
    exit_date: date | None
    exit_raw_price: float | None
    exit_execution_price: float | None
    exit_fee: float | None
    exit_slippage_cost: float | None
    mark_date: date | None
    mark_price: float | None
    holding_days: int
    gross_pnl: float
    total_fees: float
    total_slippage_cost: float
    net_pnl: float
    net_return: float


@dataclass(frozen=True)
class PerformanceMetrics:
    initial_equity: float
    final_equity: float
    total_return: float
    max_drawdown: float
    closed_trade_count: int
    open_trade_count: int
    win_rate: float | None
    total_fees: float
    total_slippage_cost: float


@dataclass(frozen=True)
class BacktestResult:
    daily: pd.DataFrame
    trades: tuple[TradeRecord, ...]
    metrics: PerformanceMetrics


@dataclass(frozen=True)
class ComparisonResult:
    strategy: BacktestResult
    benchmark: BacktestResult


@dataclass(frozen=True)
class MarketDataMetadata:
    symbol: str
    source: str
    source_version: str
    fetched_at_utc: datetime
    requested_start_date: date
    requested_end_date: date
    actual_start_date: date
    actual_end_date: date
    analysis_start_date: date
    analysis_end_date: date
    longest_lookback: int
    warmup_row_count: int
    analysis_row_count: int
    total_row_count: int
    adjustment_method: str
    data_sha256: str

    def __post_init__(self) -> None:
        if not self.symbol or not self.source or not self.source_version:
            raise ValueError("symbol, source, and source_version must be non-empty.")
        if self.fetched_at_utc.tzinfo is None:
            raise ValueError("fetched_at_utc must be timezone-aware UTC.")
        if self.fetched_at_utc.utcoffset() != timedelta(0):
            raise ValueError("fetched_at_utc must have a zero UTC offset.")
        if self.requested_start_date > self.requested_end_date:
            raise ValueError("requested_start_date must not be after requested_end_date.")
        if self.actual_start_date > self.actual_end_date:
            raise ValueError("actual_start_date must not be after actual_end_date.")
        if self.analysis_start_date > self.analysis_end_date:
            raise ValueError("analysis_start_date must not be after analysis_end_date.")
        if not (
            self.actual_start_date
            <= self.analysis_start_date
            <= self.analysis_end_date
            <= self.actual_end_date
        ):
            raise ValueError("analysis dates must fall inside the actual data range.")
        if not (
            self.requested_start_date
            <= self.analysis_start_date
            <= self.analysis_end_date
            <= self.requested_end_date
        ):
            raise ValueError("analysis dates must fall inside the requested interval.")
        if self.longest_lookback <= 0:
            raise ValueError("longest_lookback must be greater than zero.")
        if self.warmup_row_count < self.longest_lookback:
            raise ValueError("warmup_row_count must cover longest_lookback.")
        if self.analysis_row_count <= 0:
            raise ValueError("analysis_row_count must be greater than zero.")
        if self.total_row_count != self.warmup_row_count + self.analysis_row_count:
            raise ValueError("total_row_count must equal warmup plus analysis rows.")
        if len(self.data_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.data_sha256
        ):
            raise ValueError("data_sha256 must be 64 lowercase hexadecimal characters.")


@dataclass(frozen=True)
class MarketDataResult:
    prices: pd.DataFrame
    metadata: MarketDataMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.prices, pd.DataFrame):
            raise TypeError("prices must be a pandas DataFrame.")
        if len(self.prices) != self.metadata.total_row_count:
            raise ValueError("prices row count must match metadata.total_row_count.")


ScalarRawValue = float | int | date | None


@dataclass(frozen=True)
class ScalarView:
    """A report field with its machine value kept separate from display text."""

    raw_value: ScalarRawValue
    display_value: str


@dataclass(frozen=True)
class BacktestRunMetadata:
    run_id: str
    software_version: str
    generated_at_utc: datetime
    generated_at_display: str
    symbol: str
    strategy_name: str
    short_window: int
    long_window: int


@dataclass(frozen=True)
class MetricView:
    key: str
    label: str
    raw_value: float | int | None
    display_value: str
    unit: str | None


@dataclass(frozen=True)
class EquityViewRow:
    date: date
    date_display: str
    strategy_equity: float
    strategy_equity_display: str
    benchmark_equity: float
    benchmark_equity_display: str


@dataclass(frozen=True)
class TradeView:
    trade_id: int
    status: TradeStatus
    status_display: str
    entry_date: ScalarView
    entry_raw_price: ScalarView
    entry_execution_price: ScalarView
    quantity: ScalarView
    entry_fee: ScalarView
    entry_slippage_cost: ScalarView
    exit_date: ScalarView
    exit_raw_price: ScalarView
    exit_execution_price: ScalarView
    exit_fee: ScalarView
    exit_slippage_cost: ScalarView
    mark_date: ScalarView
    mark_price: ScalarView
    holding_days: ScalarView
    gross_pnl: ScalarView
    total_fees: ScalarView
    total_slippage_cost: ScalarView
    net_pnl: ScalarView
    net_return: ScalarView


@dataclass(frozen=True)
class BacktestReportView:
    """The only presentation fact source consumed by every report renderer."""

    run_metadata: BacktestRunMetadata
    market_data: MarketDataMetadata
    config: BacktestConfig
    requested_date_range_display: str
    actual_data_range_display: str
    analysis_date_range_display: str
    market_fetched_at_display: str
    initial_capital_display: str
    fee_rate_display: str
    slippage_rate_display: str
    strategy_metrics: tuple[MetricView, ...]
    benchmark_metrics: tuple[MetricView, ...]
    excess_return: MetricView
    equity_rows: tuple[EquityViewRow, ...]
    strategy_trades: tuple[TradeView, ...]
    strategy_trade_count: int
    strategy_open_trade_count: int
    html_filename: str
    csv_filename: str
    manifest_filename: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ReportArtifacts:
    html_path: Path
    csv_path: Path
    manifest_path: Path
    html_filename: str
    csv_filename: str
    manifest_filename: str
    run_id: str
