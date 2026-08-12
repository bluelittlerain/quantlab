from __future__ import annotations

import math

import numpy as np
import pandas as pd

from quant_lab.market.hk.models import HKPerformanceMetrics, HKTradeRecord
from quant_lab.metrics import calculate_max_drawdown

_ANNUAL_TRADING_SESSIONS = 252.0
_CALENDAR_DAYS_PER_YEAR = 365.2425


def calculate_hk_performance_metrics(
    initial_capital: float,
    daily: pd.DataFrame,
    trades: tuple[HKTradeRecord, ...],
) -> HKPerformanceMetrics:
    required = {"date", "equity", "quantity", "traded_notional", "total_cost", "slippage_cost"}
    missing = required.difference(daily.columns)
    if missing:
        raise ValueError(f"daily is missing required columns: {sorted(missing)}")
    if daily.empty:
        raise ValueError("daily must contain at least one analysis row.")

    equity = daily["equity"].astype(float)
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / float(initial_capital) - 1.0
    max_drawdown = calculate_max_drawdown(initial_capital, equity)

    start = pd.Timestamp(daily["date"].iloc[0]).date()
    end = pd.Timestamp(daily["date"].iloc[-1]).date()
    elapsed_days = (end - start).days
    cagr = None
    if elapsed_days > 0 and final_equity > 0:
        cagr = (final_equity / float(initial_capital)) ** (
            _CALENDAR_DAYS_PER_YEAR / elapsed_days
        ) - 1.0

    equity_with_initial = np.concatenate(([float(initial_capital)], equity.to_numpy(copy=True)))
    daily_returns = equity_with_initial[1:] / equity_with_initial[:-1] - 1.0
    annualized_volatility = None
    sharpe_ratio = None
    if daily_returns.size >= 2:
        standard_deviation = float(np.std(daily_returns, ddof=1))
        annualized_volatility = standard_deviation * math.sqrt(_ANNUAL_TRADING_SESSIONS)
        if standard_deviation > 0:
            sharpe_ratio = (float(np.mean(daily_returns)) / standard_deviation) * math.sqrt(
                _ANNUAL_TRADING_SESSIONS
            )

    calmar_ratio = cagr / abs(max_drawdown) if cagr is not None and max_drawdown < 0 else None
    market_exposure = float((daily["quantity"].astype(float) > 0).mean())
    average_equity = float(equity.mean())
    turnover = (
        math.fsum(float(value) for value in daily["traded_notional"]) / average_equity
        if average_equity > 0
        else 0.0
    )

    closed = tuple(trade for trade in trades if trade.status == "CLOSED")
    open_trades = tuple(trade for trade in trades if trade.status == "OPEN")
    win_rate = math.fsum(trade.net_pnl > 0.0 for trade in closed) / len(closed) if closed else None
    net_profits = math.fsum(max(trade.net_pnl, 0.0) for trade in closed)
    net_losses = math.fsum(min(trade.net_pnl, 0.0) for trade in closed)
    profit_factor = net_profits / abs(net_losses) if net_losses < 0 else None
    average_trade_return = (
        math.fsum(trade.net_return for trade in closed) / len(closed) if closed else None
    )
    average_holding_period = (
        math.fsum(trade.holding_days for trade in closed) / len(closed) if closed else None
    )
    total_trading_costs = math.fsum(float(value) for value in daily["total_cost"])
    total_slippage_cost = math.fsum(float(value) for value in daily["slippage_cost"])
    gross_profits = math.fsum(max(trade.gross_pnl, 0.0) for trade in closed)
    cost_ratio = total_trading_costs / gross_profits if gross_profits > 0 else None

    return HKPerformanceMetrics(
        initial_equity=float(initial_capital),
        final_equity=final_equity,
        total_return=float(total_return),
        cagr=float(cagr) if cagr is not None else None,
        annualized_volatility=annualized_volatility,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        calmar_ratio=float(calmar_ratio) if calmar_ratio is not None else None,
        market_exposure=market_exposure,
        turnover=turnover,
        closed_trade_count=len(closed),
        open_trade_count=len(open_trades),
        win_rate=float(win_rate) if win_rate is not None else None,
        profit_factor=float(profit_factor) if profit_factor is not None else None,
        average_trade_return=(
            float(average_trade_return) if average_trade_return is not None else None
        ),
        average_holding_period=(
            float(average_holding_period) if average_holding_period is not None else None
        ),
        total_trading_costs=total_trading_costs,
        total_slippage_cost=total_slippage_cost,
        cost_to_gross_profit_ratio=float(cost_ratio) if cost_ratio is not None else None,
    )
