from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from quant_lab.market.hk.costs import calculate_hk_costs, combine_costs
from quant_lab.market.hk.metrics import calculate_hk_performance_metrics
from quant_lab.market.hk.models import (
    CostBreakdown,
    ExecutionMode,
    HKBacktestConfig,
    HKBacktestResult,
    HKComparisonResult,
    HKTradeRecord,
    TradeSide,
)

_CASH_EPSILON = 1e-8


@dataclass(frozen=True)
class _OpenHKTrade:
    trade_id: int
    entry_date: date
    entry_raw_price: float
    entry_execution_price: float
    quantity: int
    entry_costs: CostBreakdown
    entry_capital: float
    entry_user_index: int


def _validate_inputs(prices: pd.DataFrame, targets: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    required = {"date", "open", "close"}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"prices is missing required columns: {sorted(missing)}")
    if prices.empty:
        raise ValueError("prices must contain at least one row.")
    if not isinstance(targets, pd.Series) or not prices.index.equals(targets.index):
        raise ValueError("target positions must be a Series with the exact prices index.")
    frame = prices.copy()
    frame["date"] = [pd.Timestamp(value).date() for value in frame["date"]]
    if frame["date"].duplicated().any() or not frame["date"].is_monotonic_increasing:
        raise ValueError("prices dates must be unique and strictly ascending.")
    for column in ("open", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
        values = frame[column].to_numpy()
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError(f"{column} prices must be finite and greater than zero.")
    normalized_targets = pd.to_numeric(targets, errors="raise").astype(float)
    if not normalized_targets.isin((0.0, 1.0)).all():
        raise ValueError("target positions may contain only 0 or 1.")
    return frame, normalized_targets


def _largest_affordable_quantity(
    cash: float,
    raw_open: float,
    config: HKBacktestConfig,
) -> tuple[int, float, CostBreakdown] | None:
    lot_size = config.board_lot.lot_size
    approximate_lots = int(cash // (raw_open * (1.0 + config.costs.slippage_rate) * lot_size))
    for lots in range(approximate_lots, 0, -1):
        quantity = lots * lot_size
        execution_price, costs = calculate_hk_costs(
            raw_price=raw_open,
            quantity=quantity,
            side=TradeSide.BUY,
            config=config.costs,
        )
        required_cash = quantity * execution_price + costs.cash_fee
        if required_cash <= cash + _CASH_EPSILON:
            return quantity, execution_price, costs
    return None


def _empty_costs() -> CostBreakdown:
    return combine_costs()


def run_hk_strategy_backtest(
    prices: pd.DataFrame,
    target_positions: pd.Series,
    config: HKBacktestConfig,
    *,
    initial_pending_target: float | None = None,
) -> HKBacktestResult:
    """Run a T+1, long-only HK board-lot strategy through an explicit cash ledger."""
    if config.execution_mode is not ExecutionMode.BOARD_LOT:
        raise ValueError("HK engine supports BOARD_LOT; legacy fractional tests use backtest.py.")
    frame, targets = _validate_inputs(prices, target_positions)
    if initial_pending_target is not None and initial_pending_target not in (0, 1):
        raise ValueError("initial_pending_target may contain only 0 or 1.")
    mask = (frame["date"] >= config.start_date) & (frame["date"] <= config.end_date)
    user_positions = np.flatnonzero(mask.to_numpy())
    if not len(user_positions):
        raise ValueError("requested HK analysis interval contains no price data.")

    first_source = int(user_positions[0])
    if initial_pending_target is not None:
        first_pending = float(initial_pending_target)
    elif first_source > 0:
        first_pending = float(targets.iloc[first_source - 1])
    else:
        first_pending = 0.0

    cash = float(config.initial_capital)
    quantity = 0
    open_trade: _OpenHKTrade | None = None
    next_trade_id = 1
    daily_rows: list[dict[str, object]] = []
    closed_trades: list[HKTradeRecord] = []
    warnings: list[str] = []

    for user_index, source_value in enumerate(user_positions):
        source_position = int(source_value)
        row = frame.iloc[source_position]
        market_date = row["date"]
        raw_open = float(row["open"])
        close = float(row["close"])
        pending_target = (
            first_pending if user_index == 0 else float(targets.iloc[source_position - 1])
        )
        target_position = float(targets.iloc[source_position])
        action = "NONE"
        execution_price = math.nan
        traded_quantity = 0
        traded_notional = 0.0
        day_costs = _empty_costs()

        if pending_target == 1.0 and quantity == 0:
            affordable = _largest_affordable_quantity(cash, raw_open, config)
            if affordable is None:
                action = "INSUFFICIENT_CAPITAL"
                warning = "当前资金不足以买入一手。"
                if warning not in warnings:
                    warnings.append(warning)
            else:
                action = "BUY"
                traded_quantity, execution_price, day_costs = affordable
                traded_notional = traded_quantity * execution_price
                cash_before = cash
                cash -= traded_notional + day_costs.cash_fee
                if cash < -_CASH_EPSILON:
                    raise ArithmeticError("board-lot buy produced materially negative cash.")
                if abs(cash) <= _CASH_EPSILON:
                    cash = 0.0
                quantity = traded_quantity
                open_trade = _OpenHKTrade(
                    trade_id=next_trade_id,
                    entry_date=market_date,
                    entry_raw_price=raw_open,
                    entry_execution_price=execution_price,
                    quantity=quantity,
                    entry_costs=day_costs,
                    entry_capital=cash_before,
                    entry_user_index=user_index,
                )
                next_trade_id += 1

        elif pending_target == 0.0 and quantity > 0:
            if open_trade is None:
                raise ArithmeticError("open position is missing its HK trade record.")
            action = "SELL"
            traded_quantity = quantity
            execution_price, day_costs = calculate_hk_costs(
                raw_price=raw_open,
                quantity=quantity,
                side=TradeSide.SELL,
                config=config.costs,
            )
            traded_notional = quantity * execution_price
            cash += traded_notional - day_costs.cash_fee
            combined_costs = combine_costs(open_trade.entry_costs, day_costs)
            gross_pnl = quantity * (raw_open - open_trade.entry_raw_price)
            net_pnl = gross_pnl - combined_costs.total_cost
            closed_trades.append(
                HKTradeRecord(
                    trade_id=open_trade.trade_id,
                    status="CLOSED",
                    entry_date=open_trade.entry_date,
                    entry_raw_price=open_trade.entry_raw_price,
                    entry_execution_price=open_trade.entry_execution_price,
                    quantity=open_trade.quantity,
                    entry_costs=open_trade.entry_costs,
                    exit_date=market_date,
                    exit_raw_price=raw_open,
                    exit_execution_price=execution_price,
                    exit_costs=day_costs,
                    mark_date=None,
                    mark_price=None,
                    holding_days=user_index - open_trade.entry_user_index,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    net_return=net_pnl / open_trade.entry_capital,
                    total_cost=combined_costs.total_cost,
                )
            )
            quantity = 0
            open_trade = None

        equity = cash + quantity * close
        daily_rows.append(
            {
                "date": market_date,
                "target_position": target_position,
                "pending_target": pending_target,
                "action": action,
                "raw_open": raw_open,
                "execution_price": execution_price,
                "trade_quantity": traded_quantity,
                "traded_notional": traded_notional,
                "cash": cash,
                "quantity": quantity,
                "close": close,
                "broker_commission": day_costs.broker_commission,
                "stamp_duty": day_costs.stamp_duty,
                "trading_fee": day_costs.trading_fee,
                "transaction_levy": day_costs.transaction_levy,
                "afrc_transaction_levy": day_costs.afrc_transaction_levy,
                "settlement_fee": day_costs.settlement_fee,
                "slippage_cost": day_costs.slippage_cost,
                "total_cost": day_costs.total_cost,
                "equity": equity,
            }
        )

    trades = list(closed_trades)
    if open_trade is not None:
        last = daily_rows[-1]
        mark_price = float(last["close"])
        gross_pnl = quantity * (mark_price - open_trade.entry_raw_price)
        net_pnl = gross_pnl - open_trade.entry_costs.total_cost
        trades.append(
            HKTradeRecord(
                trade_id=open_trade.trade_id,
                status="OPEN",
                entry_date=open_trade.entry_date,
                entry_raw_price=open_trade.entry_raw_price,
                entry_execution_price=open_trade.entry_execution_price,
                quantity=open_trade.quantity,
                entry_costs=open_trade.entry_costs,
                exit_date=None,
                exit_raw_price=None,
                exit_execution_price=None,
                exit_costs=None,
                mark_date=last["date"],
                mark_price=mark_price,
                holding_days=len(user_positions) - 1 - open_trade.entry_user_index,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                net_return=net_pnl / open_trade.entry_capital,
                total_cost=open_trade.entry_costs.total_cost,
            )
        )

    daily = pd.DataFrame(daily_rows)
    trade_tuple = tuple(sorted(trades, key=lambda trade: trade.trade_id))
    metrics = calculate_hk_performance_metrics(config.initial_capital, daily, trade_tuple)
    return HKBacktestResult(
        daily=daily,
        trades=trade_tuple,
        metrics=metrics,
        warnings=tuple(warnings),
    )


def run_hk_buy_and_hold(
    prices: pd.DataFrame,
    config: HKBacktestConfig,
) -> HKBacktestResult:
    targets = pd.Series(1.0, index=prices.index, name="target_position")
    return run_hk_strategy_backtest(prices, targets, config, initial_pending_target=1.0)


def compare_hk_results(
    strategy: HKBacktestResult,
    benchmark: HKBacktestResult,
) -> HKComparisonResult:
    return HKComparisonResult(
        strategy=strategy,
        benchmark=benchmark,
        benchmark_return=benchmark.metrics.total_return,
        excess_return=strategy.metrics.total_return - benchmark.metrics.total_return,
    )
