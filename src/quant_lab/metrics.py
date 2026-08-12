from __future__ import annotations

import math

import numpy as np
import pandas as pd

from quant_lab.models import PerformanceMetrics, TradeRecord


def calculate_max_drawdown(
    initial_equity: float,
    daily_equity: pd.Series,
) -> float:
    """Return peak-to-trough drawdown including the initial equity point."""
    values = np.concatenate(
        ([float(initial_equity)], daily_equity.astype(float).to_numpy(copy=True))
    )
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Equity values must be finite and non-negative.")
    peaks = np.maximum.accumulate(values)
    drawdowns = values / peaks - 1.0
    return float(drawdowns.min())


def calculate_performance_metrics(
    initial_capital: float,
    daily: pd.DataFrame,
    trades: tuple[TradeRecord, ...],
) -> PerformanceMetrics:
    required = {"equity", "fee", "slippage_cost"}
    missing = required.difference(daily.columns)
    if missing:
        raise ValueError(f"daily is missing required columns: {sorted(missing)}")
    if daily.empty:
        raise ValueError("daily must contain at least one user-period row.")

    final_equity = float(daily["equity"].iloc[-1])
    total_return = final_equity / float(initial_capital) - 1.0
    max_drawdown = calculate_max_drawdown(initial_capital, daily["equity"])
    closed = tuple(trade for trade in trades if trade.status == "CLOSED")
    open_trades = tuple(trade for trade in trades if trade.status == "OPEN")
    win_rate = math.fsum(trade.net_pnl > 0.0 for trade in closed) / len(closed) if closed else None

    return PerformanceMetrics(
        initial_equity=float(initial_capital),
        final_equity=final_equity,
        total_return=float(total_return),
        max_drawdown=max_drawdown,
        closed_trade_count=len(closed),
        open_trade_count=len(open_trades),
        win_rate=float(win_rate) if win_rate is not None else None,
        total_fees=math.fsum(float(value) for value in daily["fee"]),
        total_slippage_cost=math.fsum(float(value) for value in daily["slippage_cost"]),
    )
