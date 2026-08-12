from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

from quant_lab.metrics import calculate_performance_metrics
from quant_lab.models import (
    BacktestConfig,
    BacktestResult,
    ComparisonResult,
    TradeRecord,
)

_CASH_ABSOLUTE_EPSILON = 1e-9


@dataclass(frozen=True)
class _OpenTrade:
    trade_id: int
    entry_date: date
    entry_raw_price: float
    entry_execution_price: float
    quantity: float
    entry_fee: float
    entry_slippage_cost: float
    entry_capital: float
    entry_user_index: int


def _as_market_date(value: object) -> date:
    parsed = pd.Timestamp(value)
    if pd.isna(parsed):
        raise ValueError("dates must not contain missing values.")
    return parsed.date()


def _validate_inputs(
    prices: pd.DataFrame,
    target_positions: pd.Series,
) -> tuple[pd.DataFrame, pd.Series]:
    required = {"date", "open", "close"}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"prices is missing required columns: {sorted(missing)}")
    if prices.empty:
        raise ValueError("prices must contain at least one row.")
    if not isinstance(target_positions, pd.Series):
        raise TypeError("target_positions must be a pandas Series.")
    if not prices.index.equals(target_positions.index):
        raise ValueError("target_positions index must exactly match prices index.")

    frame = prices.copy()
    try:
        frame["date"] = [_as_market_date(value) for value in frame["date"]]
    except (TypeError, ValueError) as exc:
        raise ValueError("prices contains an invalid date.") from exc
    if frame["date"].duplicated().any():
        raise ValueError("prices dates must be unique.")
    dates = frame["date"].tolist()
    if any(current <= previous for previous, current in zip(dates, dates[1:])):
        raise ValueError("prices dates must be strictly ascending.")

    for column in ("open", "close"):
        try:
            frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{column} prices must be numeric.") from exc
        values = frame[column].to_numpy()
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError(f"{column} prices must be finite and greater than zero.")

    try:
        targets = pd.to_numeric(target_positions, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("target_positions must contain numeric values.") from exc
    if not np.isfinite(targets.to_numpy()).all():
        raise ValueError("target_positions must be finite.")
    if not targets.isin((0.0, 1.0)).all():
        raise ValueError("target_positions may contain only 0 or 1.")
    return frame, targets


def _config_date(value: date | None, fallback: date) -> date:
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    return value


def _execute_cash_ledger(
    prices: pd.DataFrame,
    target_positions: pd.Series,
    config: BacktestConfig,
    *,
    initial_pending_target: float | None = None,
) -> BacktestResult:
    frame, targets = _validate_inputs(prices, target_positions)
    if initial_pending_target is not None and initial_pending_target not in (0, 1):
        raise ValueError("initial_pending_target may be only 0 or 1.")

    start_date = _config_date(config.start_date, frame["date"].iloc[0])
    end_date = _config_date(config.end_date, frame["date"].iloc[-1])
    user_mask = (frame["date"] >= start_date) & (frame["date"] <= end_date)
    user_positions = np.flatnonzero(user_mask.to_numpy())
    if user_positions.size == 0:
        raise ValueError("The requested user backtest interval contains no price data.")

    first_position = int(user_positions[0])
    if initial_pending_target is not None:
        first_pending = float(initial_pending_target)
    elif first_position > 0:
        first_pending = float(targets.iloc[first_position - 1])
    else:
        first_pending = 0.0

    cash = float(config.initial_capital)
    quantity = 0.0
    open_trade: _OpenTrade | None = None
    next_trade_id = 1
    daily_rows: list[dict[str, object]] = []
    closed_trades: list[TradeRecord] = []

    for user_index, source_position_value in enumerate(user_positions):
        source_position = int(source_position_value)
        row = frame.iloc[source_position]
        market_date = row["date"]
        raw_open = float(row["open"])
        close = float(row["close"])
        pending_target = (
            first_pending if user_index == 0 else float(targets.iloc[source_position - 1])
        )
        target_position = float(targets.iloc[source_position])
        actual_position = 1.0 if quantity > 0.0 else 0.0

        action = "NONE"
        execution_price = math.nan
        trade_quantity = 0.0
        fee = 0.0
        slippage_cost = 0.0

        if pending_target == 1.0 and actual_position == 0.0:
            action = "BUY"
            execution_price = raw_open * (1.0 + config.slippage_rate)
            cash_before = cash
            trade_quantity = cash_before / (execution_price * (1.0 + config.fee_rate))
            trade_notional = trade_quantity * execution_price
            fee = trade_notional * config.fee_rate
            slippage_cost = trade_quantity * (execution_price - raw_open)
            cash = cash_before - trade_notional - fee
            if cash < -_CASH_ABSOLUTE_EPSILON:
                raise ArithmeticError("Buy accounting produced materially negative cash.")
            if abs(cash) <= _CASH_ABSOLUTE_EPSILON:
                cash = 0.0
            quantity = trade_quantity
            open_trade = _OpenTrade(
                trade_id=next_trade_id,
                entry_date=market_date,
                entry_raw_price=raw_open,
                entry_execution_price=execution_price,
                quantity=trade_quantity,
                entry_fee=fee,
                entry_slippage_cost=slippage_cost,
                entry_capital=cash_before,
                entry_user_index=user_index,
            )
            next_trade_id += 1

        elif pending_target == 0.0 and actual_position == 1.0:
            if open_trade is None:
                raise ArithmeticError("Open position is missing its trade ledger entry.")
            action = "SELL"
            execution_price = raw_open * (1.0 - config.slippage_rate)
            trade_quantity = quantity
            trade_notional = trade_quantity * execution_price
            fee = trade_notional * config.fee_rate
            slippage_cost = trade_quantity * (raw_open - execution_price)
            cash += trade_notional - fee

            gross_pnl = trade_quantity * (raw_open - open_trade.entry_raw_price)
            total_fees = open_trade.entry_fee + fee
            total_slippage = open_trade.entry_slippage_cost + slippage_cost
            net_pnl = gross_pnl - total_fees - total_slippage
            closed_trades.append(
                TradeRecord(
                    trade_id=open_trade.trade_id,
                    status="CLOSED",
                    entry_date=open_trade.entry_date,
                    entry_raw_price=open_trade.entry_raw_price,
                    entry_execution_price=open_trade.entry_execution_price,
                    quantity=open_trade.quantity,
                    entry_fee=open_trade.entry_fee,
                    entry_slippage_cost=open_trade.entry_slippage_cost,
                    exit_date=market_date,
                    exit_raw_price=raw_open,
                    exit_execution_price=execution_price,
                    exit_fee=fee,
                    exit_slippage_cost=slippage_cost,
                    mark_date=None,
                    mark_price=None,
                    holding_days=user_index - open_trade.entry_user_index,
                    gross_pnl=gross_pnl,
                    total_fees=total_fees,
                    total_slippage_cost=total_slippage,
                    net_pnl=net_pnl,
                    net_return=net_pnl / open_trade.entry_capital,
                )
            )
            quantity = 0.0
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
                "trade_quantity": trade_quantity,
                "cash": cash,
                "quantity": quantity,
                "fee": fee,
                "slippage_cost": slippage_cost,
                "close": close,
                "equity": equity,
            }
        )

    trades = list(closed_trades)
    if open_trade is not None:
        last_row = daily_rows[-1]
        mark_date = last_row["date"]
        mark_price = float(last_row["close"])
        gross_pnl = open_trade.quantity * (mark_price - open_trade.entry_raw_price)
        net_pnl = gross_pnl - open_trade.entry_fee - open_trade.entry_slippage_cost
        trades.append(
            TradeRecord(
                trade_id=open_trade.trade_id,
                status="OPEN",
                entry_date=open_trade.entry_date,
                entry_raw_price=open_trade.entry_raw_price,
                entry_execution_price=open_trade.entry_execution_price,
                quantity=open_trade.quantity,
                entry_fee=open_trade.entry_fee,
                entry_slippage_cost=open_trade.entry_slippage_cost,
                exit_date=None,
                exit_raw_price=None,
                exit_execution_price=None,
                exit_fee=None,
                exit_slippage_cost=None,
                mark_date=mark_date,
                mark_price=mark_price,
                holding_days=len(user_positions) - 1 - open_trade.entry_user_index,
                gross_pnl=gross_pnl,
                total_fees=open_trade.entry_fee,
                total_slippage_cost=open_trade.entry_slippage_cost,
                net_pnl=net_pnl,
                net_return=net_pnl / open_trade.entry_capital,
            )
        )

    daily = pd.DataFrame(daily_rows)
    trade_tuple = tuple(sorted(trades, key=lambda trade: trade.trade_id))
    metrics = calculate_performance_metrics(
        config.initial_capital,
        daily,
        trade_tuple,
    )
    return BacktestResult(daily=daily, trades=trade_tuple, metrics=metrics)


def run_strategy_backtest(
    prices: pd.DataFrame,
    target_positions: pd.Series,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a delayed target-position strategy through the cash ledger."""
    return _execute_cash_ledger(
        prices,
        target_positions,
        config or BacktestConfig(),
    )


def run_buy_and_hold_benchmark(
    prices: pd.DataFrame,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Buy at the first user bar open using the shared execution ledger."""
    targets = pd.Series(1.0, index=prices.index, name="target_position")
    return _execute_cash_ledger(
        prices,
        targets,
        config or BacktestConfig(),
        initial_pending_target=1.0,
    )


def run_strategy_and_benchmark(
    prices: pd.DataFrame,
    target_positions: pd.Series,
    config: BacktestConfig | None = None,
) -> ComparisonResult:
    resolved_config = config or BacktestConfig()
    return ComparisonResult(
        strategy=run_strategy_backtest(prices, target_positions, resolved_config),
        benchmark=run_buy_and_hold_benchmark(prices, resolved_config),
    )
