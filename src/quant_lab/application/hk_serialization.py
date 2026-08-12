from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from quant_lab.application.hk_workflow import HKRunOutput
from quant_lab.market.hk.models import CostBreakdown, HKPerformanceMetrics, HKTradeRecord


def _optional_finite(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def _metrics(metrics: HKPerformanceMetrics) -> dict[str, Any]:
    values = asdict(metrics)
    return {
        key: _optional_finite(value) if isinstance(value, float) else value
        for key, value in values.items()
    }


def _costs(costs: CostBreakdown | None) -> dict[str, float] | None:
    return asdict(costs) if costs is not None else None


def _trade(trade: HKTradeRecord) -> dict[str, Any]:
    return {
        "trade_id": trade.trade_id,
        "status": trade.status,
        "entry_date": trade.entry_date.isoformat(),
        "entry_raw_price": trade.entry_raw_price,
        "entry_execution_price": trade.entry_execution_price,
        "quantity": trade.quantity,
        "entry_costs": _costs(trade.entry_costs),
        "exit_date": trade.exit_date.isoformat() if trade.exit_date else None,
        "exit_raw_price": trade.exit_raw_price,
        "exit_execution_price": trade.exit_execution_price,
        "exit_costs": _costs(trade.exit_costs),
        "mark_date": trade.mark_date.isoformat() if trade.mark_date else None,
        "mark_price": trade.mark_price,
        "holding_days": trade.holding_days,
        "gross_pnl": trade.gross_pnl,
        "net_pnl": trade.net_pnl,
        "net_return": trade.net_return,
        "total_cost": trade.total_cost,
    }


def _board_lot(value: Any) -> dict[str, Any]:
    return {
        "lot_size": value.lot_size,
        "source": value.source.value,
        "verified_at": value.verified_at.isoformat() if value.verified_at else None,
        "confirmed": value.confirmed,
    }


def serialize_hk_run(output: HKRunOutput) -> dict[str, Any]:
    request = output.request
    strategy_daily = output.comparison.strategy.daily.reset_index(drop=True)
    benchmark_daily = output.comparison.benchmark.daily.reset_index(drop=True)
    analysis_prices = output.market_data.prices.loc[
        (output.market_data.prices["date"] >= request.start_date)
        & (output.market_data.prices["date"] <= request.end_date)
    ].reset_index(drop=True)
    short_sma = output.market_data.prices["close"].rolling(request.short_window).mean()
    long_sma = output.market_data.prices["close"].rolling(request.long_window).mean()
    analysis_mask = (output.market_data.prices["date"] >= request.start_date) & (
        output.market_data.prices["date"] <= request.end_date
    )
    short_analysis = short_sma.loc[analysis_mask].reset_index(drop=True)
    long_analysis = long_sma.loc[analysis_mask].reset_index(drop=True)

    price_series = []
    for index, row in analysis_prices.iterrows():
        price_series.append(
            {
                "date": row["date"].isoformat(),
                "close": float(row["close"]),
                "short_sma": _optional_finite(float(short_analysis.iloc[index])),
                "long_sma": _optional_finite(float(long_analysis.iloc[index])),
                "action": str(strategy_daily.iloc[index]["action"]),
            }
        )

    equity_values = strategy_daily["equity"].astype(float)
    drawdown = equity_values / equity_values.cummax().clip(lower=request.initial_capital) - 1.0
    equity_series = [
        {
            "date": strategy_daily.iloc[index]["date"].isoformat(),
            "strategy_equity": float(strategy_daily.iloc[index]["equity"]),
            "benchmark_equity": float(benchmark_daily.iloc[index]["equity"]),
            "excess": float(strategy_daily.iloc[index]["equity"])
            - float(benchmark_daily.iloc[index]["equity"]),
            "drawdown": float(drawdown.iloc[index]),
        }
        for index in range(len(strategy_daily))
    ]

    cost_fields = (
        "broker_commission",
        "stamp_duty",
        "trading_fee",
        "transaction_levy",
        "afrc_transaction_levy",
        "settlement_fee",
        "slippage_cost",
    )
    cost_summary = {
        field: math.fsum(float(value) for value in strategy_daily[field]) for field in cost_fields
    }
    cost_summary["total_cost"] = math.fsum(cost_summary.values())

    return {
        "run_id": output.run_id,
        "created_at_utc": output.created_at_utc.isoformat(),
        "symbol": asdict(output.symbol),
        "benchmark": asdict(output.benchmark_symbol),
        "date_range": {
            "requested_start": request.start_date.isoformat(),
            "requested_end": request.end_date.isoformat(),
            "actual_start": strategy_daily.iloc[0]["date"].isoformat(),
            "actual_end": strategy_daily.iloc[-1]["date"].isoformat(),
        },
        "strategy": {
            "name": "SMA 双均线趋势",
            "short_window": request.short_window,
            "long_window": request.long_window,
        },
        "initial_capital": request.initial_capital,
        "board_lot": _board_lot(request.board_lot),
        "benchmark_board_lot": _board_lot(request.benchmark_board_lot),
        "cost_config": asdict(request.costs),
        "benchmark_cost_config": asdict(request.benchmark_costs),
        "strategy_metrics": _metrics(output.comparison.strategy.metrics),
        "benchmark_metrics": _metrics(output.comparison.benchmark.metrics),
        "benchmark_return": output.comparison.benchmark_return,
        "excess_return": output.comparison.excess_return,
        "price_series": price_series,
        "equity_series": equity_series,
        "trades": [_trade(trade) for trade in output.comparison.strategy.trades],
        "cost_summary": cost_summary,
        "market_data": {
            "source": output.market_data.metadata.source,
            "source_version": output.market_data.metadata.source_version,
            "fetched_at_utc": output.market_data.metadata.fetched_at_utc.isoformat(),
            "cache_status": output.market_data_cache_status,
            "data_sha256": output.market_data.metadata.data_sha256,
            "adjustment_method": output.market_data.metadata.adjustment_method,
            "warmup_rows": output.market_data.metadata.warmup_row_count,
            "missing_expected_sessions": [
                value.isoformat() for value in output.strategy_calendar.missing_expected_sessions
            ],
        },
        "warnings": list(output.comparison.strategy.warnings),
    }
