from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from quant_lab.models import (
    BacktestConfig,
    BacktestReportView,
    BacktestRunMetadata,
    ComparisonResult,
    EquityViewRow,
    MarketDataMetadata,
    MarketDataResult,
    MetricView,
    PerformanceMetrics,
    ScalarView,
    TradeRecord,
    TradeView,
)

RUN_ID_HEX_LENGTH = 16


def _require_finite(value: float | int, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")
    return number


def _fixed(value: float | int, places: int) -> str:
    number = _require_finite(value, "report value")
    quantum = Decimal(1).scaleb(-places)
    rounded = Decimal(str(number)).quantize(quantum, rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)
    return f"{rounded:.{places}f}"


def _currency(value: float | int) -> str:
    return f"${float(_fixed(value, 2)):,.2f}"


def _percent(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    return f"{_fixed(float(value) * 100.0, 4)}%"


def _price(value: float | int | None) -> str:
    return "N/A" if value is None else _fixed(value, 4)


def _quantity(value: float | int | None) -> str:
    return "N/A" if value is None else _fixed(value, 8)


def _money(value: float | int | None) -> str:
    return "N/A" if value is None else _currency(value)


def _date_text(value: date | None) -> str:
    return "N/A" if value is None else value.isoformat()


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("UTC timestamps must be timezone-aware datetimes.")
    if value.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamps must have a zero UTC offset.")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _daily_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("daily date must not be missing.")
    if timestamp.tzinfo is not None:
        raise ValueError("daily dates must be date-only values without a timezone.")
    return timestamp.date()


def _canonical_float(value: float) -> str:
    number = _require_finite(value, "run_id numeric field")
    return format(number, ".17g")


def calculate_run_id(
    market_data: MarketDataMetadata,
    config: BacktestConfig,
    *,
    strategy_name: str,
    short_window: int,
    long_window: int,
    software_version: str,
) -> str:
    """Hash a fixed ordered JSON sequence; generation time is intentionally absent."""
    fields = (
        ("software_version", software_version),
        ("symbol", market_data.symbol),
        ("requested_start_date", market_data.requested_start_date.isoformat()),
        ("requested_end_date", market_data.requested_end_date.isoformat()),
        ("actual_start_date", market_data.actual_start_date.isoformat()),
        ("actual_end_date", market_data.actual_end_date.isoformat()),
        ("analysis_start_date", market_data.analysis_start_date.isoformat()),
        ("analysis_end_date", market_data.analysis_end_date.isoformat()),
        ("data_sha256", market_data.data_sha256),
        ("initial_capital", _canonical_float(config.initial_capital)),
        ("fee_rate", _canonical_float(config.fee_rate)),
        ("slippage_rate", _canonical_float(config.slippage_rate)),
        ("strategy_name", strategy_name),
        ("short_window", str(short_window)),
        ("long_window", str(long_window)),
    )
    canonical = json.dumps(
        fields,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:RUN_ID_HEX_LENGTH]


def _metric_views(metrics: PerformanceMetrics) -> tuple[MetricView, ...]:
    return (
        MetricView(
            "initial_equity",
            "初始权益",
            metrics.initial_equity,
            _currency(metrics.initial_equity),
            "USD",
        ),
        MetricView(
            "final_equity",
            "最终权益",
            metrics.final_equity,
            _currency(metrics.final_equity),
            "USD",
        ),
        MetricView(
            "total_return",
            "总收益率",
            metrics.total_return,
            _percent(metrics.total_return),
            "%",
        ),
        MetricView(
            "max_drawdown",
            "最大回撤",
            metrics.max_drawdown,
            _percent(metrics.max_drawdown),
            "%",
        ),
        MetricView(
            "closed_trade_count",
            "已平仓交易",
            metrics.closed_trade_count,
            str(metrics.closed_trade_count),
            "count",
        ),
        MetricView(
            "open_trade_count",
            "未平仓交易",
            metrics.open_trade_count,
            str(metrics.open_trade_count),
            "count",
        ),
        MetricView(
            "win_rate",
            "胜率",
            metrics.win_rate,
            _percent(metrics.win_rate),
            "%",
        ),
        MetricView(
            "total_fees",
            "累计手续费",
            metrics.total_fees,
            _currency(metrics.total_fees),
            "USD",
        ),
        MetricView(
            "total_slippage_cost",
            "累计滑点成本",
            metrics.total_slippage_cost,
            _currency(metrics.total_slippage_cost),
            "USD",
        ),
    )


def _scalar_date(value: date | None) -> ScalarView:
    return ScalarView(value, _date_text(value))


def _scalar_price(value: float | None) -> ScalarView:
    return ScalarView(value, _price(value))


def _scalar_quantity(value: float | None) -> ScalarView:
    return ScalarView(value, _quantity(value))


def _scalar_money(value: float | None) -> ScalarView:
    return ScalarView(value, _money(value))


def _trade_view(trade: TradeRecord) -> TradeView:
    return TradeView(
        trade_id=trade.trade_id,
        status=trade.status,
        status_display="持仓中" if trade.status == "OPEN" else "已平仓",
        entry_date=_scalar_date(trade.entry_date),
        entry_raw_price=_scalar_price(trade.entry_raw_price),
        entry_execution_price=_scalar_price(trade.entry_execution_price),
        quantity=_scalar_quantity(trade.quantity),
        entry_fee=_scalar_money(trade.entry_fee),
        entry_slippage_cost=_scalar_money(trade.entry_slippage_cost),
        exit_date=_scalar_date(trade.exit_date),
        exit_raw_price=_scalar_price(trade.exit_raw_price),
        exit_execution_price=_scalar_price(trade.exit_execution_price),
        exit_fee=_scalar_money(trade.exit_fee),
        exit_slippage_cost=_scalar_money(trade.exit_slippage_cost),
        mark_date=_scalar_date(trade.mark_date),
        mark_price=_scalar_price(trade.mark_price),
        holding_days=ScalarView(trade.holding_days, str(trade.holding_days)),
        gross_pnl=_scalar_money(trade.gross_pnl),
        total_fees=_scalar_money(trade.total_fees),
        total_slippage_cost=_scalar_money(trade.total_slippage_cost),
        net_pnl=_scalar_money(trade.net_pnl),
        net_return=ScalarView(trade.net_return, _percent(trade.net_return)),
    )


def _validate_inputs(
    market_data: MarketDataResult,
    comparison: ComparisonResult,
    config: BacktestConfig,
    strategy_name: str,
    short_window: int,
    long_window: int,
    software_version: str,
    generated_at_utc: datetime,
) -> tuple[tuple[date, ...], tuple[date, ...]]:
    if not strategy_name.strip():
        raise ValueError("strategy_name must be non-empty.")
    if not software_version.strip():
        raise ValueError("software_version must be non-empty.")
    if not isinstance(short_window, int) or isinstance(short_window, bool) or short_window <= 0:
        raise ValueError("short_window must be a positive integer.")
    if not isinstance(long_window, int) or isinstance(long_window, bool) or long_window <= 0:
        raise ValueError("long_window must be a positive integer.")
    if short_window >= long_window:
        raise ValueError("short_window must be smaller than long_window.")
    _utc_text(generated_at_utc)

    metadata = market_data.metadata
    if config.start_date is None or config.end_date is None:
        raise ValueError("report config must define start_date and end_date.")
    if config.start_date != metadata.requested_start_date:
        raise ValueError("config.start_date must match requested_start_date.")
    if config.end_date != metadata.requested_end_date:
        raise ValueError("config.end_date must match requested_end_date.")

    strategy_daily = comparison.strategy.daily
    benchmark_daily = comparison.benchmark.daily
    for scope, result in (
        ("strategy", comparison.strategy),
        ("benchmark", comparison.benchmark),
    ):
        missing = {"date", "equity"} - set(result.daily.columns)
        if missing:
            raise ValueError(f"{scope} daily is missing columns: {sorted(missing)}.")
        if len(result.daily) != metadata.analysis_row_count:
            raise ValueError(f"{scope} daily row count must match metadata.analysis_row_count.")
        if not math.isclose(
            result.metrics.initial_equity,
            config.initial_capital,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError(f"{scope} initial equity must match config.initial_capital.")
        status_counts = {
            "OPEN": sum(trade.status == "OPEN" for trade in result.trades),
            "CLOSED": sum(trade.status == "CLOSED" for trade in result.trades),
        }
        if status_counts["OPEN"] != result.metrics.open_trade_count:
            raise ValueError(f"{scope} open trade count is inconsistent with its ledger.")
        if status_counts["CLOSED"] != result.metrics.closed_trade_count:
            raise ValueError(f"{scope} closed trade count is inconsistent with its ledger.")

    strategy_dates = tuple(_daily_date(value) for value in strategy_daily["date"])
    benchmark_dates = tuple(_daily_date(value) for value in benchmark_daily["date"])
    if strategy_dates != benchmark_dates:
        raise ValueError("strategy and benchmark daily dates must align exactly.")
    if not strategy_dates:
        raise ValueError("report requires at least one analysis trading day.")
    if len(set(strategy_dates)) != len(strategy_dates):
        raise ValueError("report daily dates must be unique.")
    if tuple(sorted(strategy_dates)) != strategy_dates:
        raise ValueError("report daily dates must be in ascending order.")
    if strategy_dates[0] != metadata.analysis_start_date:
        raise ValueError("daily start date must match metadata.analysis_start_date.")
    if strategy_dates[-1] != metadata.analysis_end_date:
        raise ValueError("daily end date must match metadata.analysis_end_date.")

    for scope, daily in (("strategy", strategy_daily), ("benchmark", benchmark_daily)):
        for row_date, value in zip(strategy_dates, daily["equity"]):
            number = _require_finite(value, f"{scope} equity at {row_date.isoformat()}")
            if number < 0:
                raise ValueError(f"{scope} equity at {row_date.isoformat()} must be non-negative.")
    return strategy_dates, benchmark_dates


def build_report_view(
    market_data: MarketDataResult,
    comparison: ComparisonResult,
    *,
    config: BacktestConfig,
    strategy_name: str,
    short_window: int,
    long_window: int,
    software_version: str,
    generated_at_utc: datetime,
) -> BacktestReportView:
    """Build the immutable presentation fact source without rerunning a backtest."""
    strategy_dates, _ = _validate_inputs(
        market_data,
        comparison,
        config,
        strategy_name,
        short_window,
        long_window,
        software_version,
        generated_at_utc,
    )
    metadata = market_data.metadata
    run_id = calculate_run_id(
        metadata,
        config,
        strategy_name=strategy_name,
        short_window=short_window,
        long_window=long_window,
        software_version=software_version,
    )
    symbol_slug = "-".join(
        part
        for part in "".join(
            character.lower() if character.isalnum() else "-" for character in metadata.symbol
        ).split("-")
        if part
    )
    if not symbol_slug:
        raise ValueError("market data symbol cannot form a report filename.")
    artifact_stem = f"quantlab-{symbol_slug}-{run_id}"

    equity_rows = tuple(
        EquityViewRow(
            date=row_date,
            date_display=row_date.isoformat(),
            strategy_equity=float(strategy_equity),
            strategy_equity_display=_currency(strategy_equity),
            benchmark_equity=float(benchmark_equity),
            benchmark_equity_display=_currency(benchmark_equity),
        )
        for row_date, strategy_equity, benchmark_equity in zip(
            strategy_dates,
            comparison.strategy.daily["equity"],
            comparison.benchmark.daily["equity"],
        )
    )
    strategy_metrics = _metric_views(comparison.strategy.metrics)
    benchmark_metrics = _metric_views(comparison.benchmark.metrics)
    excess_raw = (
        comparison.strategy.metrics.total_return - comparison.benchmark.metrics.total_return
    )

    return BacktestReportView(
        run_metadata=BacktestRunMetadata(
            run_id=run_id,
            software_version=software_version,
            generated_at_utc=generated_at_utc,
            generated_at_display=_utc_text(generated_at_utc),
            symbol=metadata.symbol,
            strategy_name=strategy_name,
            short_window=short_window,
            long_window=long_window,
        ),
        market_data=metadata,
        config=config,
        requested_date_range_display=(
            f"{metadata.requested_start_date.isoformat()} 至 "
            f"{metadata.requested_end_date.isoformat()}"
        ),
        actual_data_range_display=(
            f"{metadata.actual_start_date.isoformat()} 至 {metadata.actual_end_date.isoformat()}"
        ),
        analysis_date_range_display=(
            f"{metadata.analysis_start_date.isoformat()} 至 "
            f"{metadata.analysis_end_date.isoformat()}"
        ),
        market_fetched_at_display=_utc_text(metadata.fetched_at_utc),
        initial_capital_display=_currency(config.initial_capital),
        fee_rate_display=_percent(config.fee_rate),
        slippage_rate_display=_percent(config.slippage_rate),
        strategy_metrics=strategy_metrics,
        benchmark_metrics=benchmark_metrics,
        excess_return=MetricView(
            key="excess_return",
            label="策略超额收益",
            raw_value=excess_raw,
            display_value=_percent(excess_raw),
            unit="%",
        ),
        equity_rows=equity_rows,
        strategy_trades=tuple(_trade_view(trade) for trade in comparison.strategy.trades),
        strategy_trade_count=(
            comparison.strategy.metrics.closed_trade_count
            + comparison.strategy.metrics.open_trade_count
        ),
        strategy_open_trade_count=comparison.strategy.metrics.open_trade_count,
        html_filename=f"{artifact_stem}-report.html",
        csv_filename=f"{artifact_stem}-trades.csv",
        manifest_filename=f"{artifact_stem}-manifest.json",
        assumptions=(
            "仅使用调整后日线数据，只做多，持仓状态为全仓或空仓，并允许小数股。",
            "T 日收盘后形成目标仓位，最早在下一交易日开盘成交。",
            "买卖双边按实际成交金额计收手续费，并按开盘参考价施加滑点。",
            "期末未平仓持仓按最后一个分析交易日的调整后收盘价估值，不虚构卖出成本。",
            "买入持有基准使用相同初始资金、手续费、滑点和期末估值口径。",
        ),
        warnings=(
            "本报告使用调整后价格序列，不单独模拟现金分红入账。",
            "历史回测不代表未来表现；本工具仅用于研究和工程验证，不构成投资建议。",
        ),
    )
