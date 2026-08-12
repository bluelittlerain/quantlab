from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Callable, Literal

from quant_lab.__about__ import __version__
from quant_lab.backtest import run_strategy_and_benchmark
from quant_lab.data import SPY_SYMBOL, load_spy_adjusted_daily
from quant_lab.models import (
    BacktestConfig,
    BacktestReportView,
    ComparisonResult,
    MarketDataResult,
)
from quant_lab.presentation import build_report_view
from quant_lab.report import (
    render_html_report,
    render_run_manifest,
    render_trades_csv,
)
from quant_lab.strategies import moving_average_signal

PACKAGE_DISTRIBUTION_NAME = "quantlab-stock-etf-backtester"
SPY_SMA_STRATEGY_NAME = "SMA 双均线"
MarketDataLoader = Callable[..., MarketDataResult]
WorkflowStage = Literal[
    "market_data_fetch",
    "market_data_standardize",
    "sma_signal",
    "cash_ledger",
    "presentation",
    "html_report",
    "trades_csv",
    "manifest",
]
WorkflowStageCallback = Callable[[WorkflowStage], None]


@dataclass(frozen=True)
class SpySmaRunRequest:
    start_date: date
    end_date: date
    short_window: int
    long_window: int
    initial_capital: float
    fee_rate: float
    slippage_rate: float

    def __post_init__(self) -> None:
        for field_name, value in (
            ("start_date", self.start_date),
            ("end_date", self.end_date),
        ):
            if not isinstance(value, date) or isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a date.")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be later than end_date.")

        for field_name, value, minimum in (
            ("short_window", self.short_window, 1),
            ("long_window", self.long_window, 2),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(
                    f"{field_name} must be an integer greater than or equal to {minimum}."
                )
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window.")

        if (
            isinstance(self.initial_capital, bool)
            or not math.isfinite(float(self.initial_capital))
            or self.initial_capital <= 0
        ):
            raise ValueError("initial_capital must be finite and greater than zero.")
        for field_name, value in (
            ("fee_rate", self.fee_rate),
            ("slippage_rate", self.slippage_rate),
        ):
            if isinstance(value, bool) or not math.isfinite(float(value)) or not 0 <= value < 1:
                raise ValueError(f"{field_name} must be finite and satisfy 0 <= {field_name} < 1.")


@dataclass(frozen=True)
class SpySmaRunOutput:
    request: SpySmaRunRequest
    market_data: MarketDataResult
    comparison: ComparisonResult
    report_view: BacktestReportView
    html_report: str
    trades_csv: str
    manifest_json: str


def installed_software_version() -> str:
    """Read the package metadata instead of duplicating the project version."""
    try:
        return version(PACKAGE_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return __version__


def _emit_stage(
    stage_callback: WorkflowStageCallback | None,
    stage: WorkflowStage,
) -> None:
    if stage_callback is not None:
        stage_callback(stage)


def run_spy_sma_workflow(
    request: SpySmaRunRequest,
    *,
    software_version: str,
    generated_at_utc: datetime,
    market_data_loader: MarketDataLoader = load_spy_adjusted_daily,
    stage_callback: WorkflowStageCallback | None = None,
) -> SpySmaRunOutput:
    """Run the single Phase 1 SPY/SMA vertical path exactly once."""
    if not isinstance(request, SpySmaRunRequest):
        raise TypeError("request must be a SpySmaRunRequest.")
    if not software_version.strip():
        raise ValueError("software_version must be non-empty.")
    if not isinstance(generated_at_utc, datetime) or generated_at_utc.tzinfo is None:
        raise ValueError("generated_at_utc must be a timezone-aware UTC datetime.")
    if generated_at_utc.utcoffset() != timedelta(0):
        raise ValueError("generated_at_utc must have a zero UTC offset.")

    if market_data_loader is load_spy_adjusted_daily:
        market_data = load_spy_adjusted_daily(
            request.start_date,
            request.end_date,
            request.long_window,
            fetched_at_utc=generated_at_utc,
            stage_callback=stage_callback,
        )
    else:
        _emit_stage(stage_callback, "market_data_fetch")
        market_data = market_data_loader(
            request.start_date,
            request.end_date,
            request.long_window,
            fetched_at_utc=generated_at_utc,
        )
        _emit_stage(stage_callback, "market_data_standardize")
    if market_data.metadata.symbol != SPY_SYMBOL:
        raise ValueError(f"Phase 1 market_data_loader must return symbol {SPY_SYMBOL!r}.")

    _emit_stage(stage_callback, "sma_signal")
    target_positions = moving_average_signal(
        market_data.prices,
        short_window=request.short_window,
        long_window=request.long_window,
    )
    config = BacktestConfig(
        initial_capital=request.initial_capital,
        fee_rate=request.fee_rate,
        slippage_rate=request.slippage_rate,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    _emit_stage(stage_callback, "cash_ledger")
    comparison = run_strategy_and_benchmark(
        market_data.prices,
        target_positions,
        config,
    )
    _emit_stage(stage_callback, "presentation")
    report_view = build_report_view(
        market_data,
        comparison,
        config=config,
        strategy_name=SPY_SMA_STRATEGY_NAME,
        short_window=request.short_window,
        long_window=request.long_window,
        software_version=software_version,
        generated_at_utc=generated_at_utc,
    )
    _emit_stage(stage_callback, "html_report")
    html_report = render_html_report(report_view)
    _emit_stage(stage_callback, "trades_csv")
    trades_csv = render_trades_csv(report_view)
    _emit_stage(stage_callback, "manifest")
    manifest_json = render_run_manifest(report_view)
    return SpySmaRunOutput(
        request=request,
        market_data=market_data,
        comparison=comparison,
        report_view=report_view,
        html_report=html_report,
        trades_csv=trades_csv,
        manifest_json=manifest_json,
    )
