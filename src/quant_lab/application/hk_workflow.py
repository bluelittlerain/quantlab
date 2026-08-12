from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd

from quant_lab.application.errors import QuantLabApplicationError
from quant_lab.market.hk.calendar import HKCalendarValidation, validate_hk_trading_sessions
from quant_lab.market.hk.engine import (
    compare_hk_results,
    run_hk_buy_and_hold,
    run_hk_strategy_backtest,
)
from quant_lab.market.hk.models import (
    BoardLotConfig,
    HKBacktestConfig,
    HKComparisonResult,
    HKSymbol,
    HKTradingCostConfig,
)
from quant_lab.market.hk.symbols import normalize_hk_symbol
from quant_lab.models import MarketDataResult
from quant_lab.providers.base import MarketDataProvider
from quant_lab.strategies import moving_average_signal


@dataclass(frozen=True)
class HKRunRequest:
    symbol: str
    benchmark_symbol: str
    start_date: date
    end_date: date
    short_window: int
    long_window: int
    initial_capital: float
    board_lot: BoardLotConfig
    benchmark_board_lot: BoardLotConfig
    costs: HKTradingCostConfig
    benchmark_costs: HKTradingCostConfig

    def __post_init__(self) -> None:
        normalize_hk_symbol(self.symbol)
        normalize_hk_symbol(self.benchmark_symbol)
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be later than end_date.")
        if self.short_window <= 0 or self.long_window <= 1:
            raise ValueError("SMA windows must be positive.")
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window.")
        if not math.isfinite(float(self.initial_capital)) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be finite and greater than zero.")


@dataclass(frozen=True)
class HKRunOutput:
    run_id: str
    created_at_utc: datetime
    symbol: HKSymbol
    benchmark_symbol: HKSymbol
    request: HKRunRequest
    market_data: MarketDataResult
    benchmark_market_data: MarketDataResult
    strategy_calendar: HKCalendarValidation
    benchmark_calendar: HKCalendarValidation
    comparison: HKComparisonResult
    target_positions: pd.Series
    market_data_cache_status: str
    benchmark_data_cache_status: str


def _analysis_dates(market_data: MarketDataResult) -> tuple[date, ...]:
    metadata = market_data.metadata
    frame = market_data.prices
    mask = (frame["date"] >= metadata.analysis_start_date) & (
        frame["date"] <= metadata.analysis_end_date
    )
    return tuple(frame.loc[mask, "date"])


def _run_id(
    request: HKRunRequest,
    market_data: MarketDataResult,
    benchmark_market_data: MarketDataResult,
) -> str:
    payload = {
        "benchmark": normalize_hk_symbol(request.benchmark_symbol).normalized_symbol,
        "benchmark_board_lot": request.benchmark_board_lot.lot_size,
        "benchmark_costs": request.benchmark_costs.__dict__,
        "benchmark_data_sha256": benchmark_market_data.metadata.data_sha256,
        "board_lot": request.board_lot.lot_size,
        "costs": request.costs.__dict__,
        "data_sha256": market_data.metadata.data_sha256,
        "end_date": request.end_date.isoformat(),
        "initial_capital": format(request.initial_capital, ".12f"),
        "long_window": request.long_window,
        "short_window": request.short_window,
        "start_date": request.start_date.isoformat(),
        "strategy": "SMA_CROSSOVER",
        "symbol": normalize_hk_symbol(request.symbol).normalized_symbol,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def run_hk_sma_workflow(
    request: HKRunRequest,
    *,
    provider: MarketDataProvider,
    created_at_utc: datetime | None = None,
    force_refresh: bool = False,
) -> HKRunOutput:
    """Run the first HK vertical slice with one provider and no UI-side calculations."""
    created_at = (created_at_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    symbol = normalize_hk_symbol(request.symbol)
    benchmark_symbol = normalize_hk_symbol(request.benchmark_symbol)

    def load_prices(current_symbol: HKSymbol, *, field: str, benchmark: bool) -> MarketDataResult:
        try:
            return provider.get_daily_prices(
                current_symbol,
                request.start_date,
                request.end_date,
                request.long_window,
                fetched_at_utc=created_at,
                force_refresh=force_refresh,
            )
        except QuantLabApplicationError as exc:
            if exc.field is not None:
                raise
            raise QuantLabApplicationError(exc.code, exc.message, field, exc.details) from exc
        except (OSError, RuntimeError) as exc:
            target = "比较基准" if benchmark else "标的"
            raise QuantLabApplicationError(
                "PROVIDER_ERROR",
                f"无法获取{target} {current_symbol.normalized_symbol} 的行情，请稍后重试。",
                field,
            ) from exc
        except ValueError as exc:
            code = "BENCHMARK_DATA_NOT_FOUND" if benchmark else "DATA_NOT_FOUND"
            target = "比较基准" if benchmark else "标的"
            raise QuantLabApplicationError(
                code,
                f"找不到{target} {current_symbol.normalized_symbol} 在所选区间的有效行情。",
                field,
            ) from exc

    market_data = load_prices(symbol, field="symbol", benchmark=False)
    benchmark_data = load_prices(
        benchmark_symbol,
        field="benchmark_symbol",
        benchmark=True,
    )

    strategy_dates = _analysis_dates(market_data)
    benchmark_dates = _analysis_dates(benchmark_data)
    if strategy_dates != benchmark_dates:
        raise QuantLabApplicationError(
            "BENCHMARK_DATE_MISMATCH",
            "标的与比较基准的有效交易日期不一致。",
            "benchmark_symbol",
            {"strategy_rows": len(strategy_dates), "benchmark_rows": len(benchmark_dates)},
        )
    strategy_calendar = validate_hk_trading_sessions(
        strategy_dates,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    benchmark_calendar = validate_hk_trading_sessions(
        benchmark_dates,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    targets = moving_average_signal(
        market_data.prices,
        short_window=request.short_window,
        long_window=request.long_window,
    )
    strategy_config = HKBacktestConfig(
        initial_capital=request.initial_capital,
        board_lot=request.board_lot,
        costs=request.costs,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    benchmark_config = HKBacktestConfig(
        initial_capital=request.initial_capital,
        board_lot=request.benchmark_board_lot,
        costs=request.benchmark_costs,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    strategy_result = run_hk_strategy_backtest(market_data.prices, targets, strategy_config)
    benchmark_result = run_hk_buy_and_hold(benchmark_data.prices, benchmark_config)
    comparison = compare_hk_results(strategy_result, benchmark_result)
    cache_checker = getattr(provider, "was_cache_hit", None)
    market_cache_status = "CACHE" if cache_checker and cache_checker(symbol) else "LIVE"
    benchmark_cache_status = (
        "CACHE" if cache_checker and cache_checker(benchmark_symbol) else "LIVE"
    )
    return HKRunOutput(
        run_id=_run_id(request, market_data, benchmark_data),
        created_at_utc=created_at,
        symbol=symbol,
        benchmark_symbol=benchmark_symbol,
        request=request,
        market_data=market_data,
        benchmark_market_data=benchmark_data,
        strategy_calendar=strategy_calendar,
        benchmark_calendar=benchmark_calendar,
        comparison=comparison,
        target_positions=targets,
        market_data_cache_status=market_cache_status,
        benchmark_data_cache_status=benchmark_cache_status,
    )
