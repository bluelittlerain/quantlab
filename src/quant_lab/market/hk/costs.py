from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from quant_lab.market.hk.models import CostBreakdown, HKTradingCostConfig, TradeSide

_CENT = Decimal("0.01")
_DOLLAR = Decimal("1")


def _decimal(value: float) -> Decimal:
    return Decimal(str(float(value)))


def _round_cent(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def calculate_hk_costs(
    *,
    raw_price: float,
    quantity: int,
    side: TradeSide,
    config: HKTradingCostConfig,
) -> tuple[float, CostBreakdown]:
    """Return execution price and a deterministic side-aware HK cost breakdown."""
    if not math.isfinite(float(raw_price)) or raw_price <= 0:
        raise ValueError("raw_price must be finite and greater than zero.")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("quantity must be a positive integer.")
    if not isinstance(side, TradeSide):
        raise TypeError("side must be a TradeSide.")

    direction = 1.0 if side is TradeSide.BUY else -1.0
    execution_price = float(raw_price) * (1.0 + direction * config.slippage_rate)
    notional = _decimal(execution_price) * Decimal(quantity)
    commission = max(
        _round_cent(notional * _decimal(config.broker_commission_rate)),
        _round_cent(_decimal(config.broker_minimum_commission)),
    )
    stamp_raw = notional * _decimal(config.stamp_rate_for(side))
    stamp = stamp_raw.quantize(_DOLLAR, rounding=ROUND_CEILING) if stamp_raw else Decimal(0)
    trading_fee = _round_cent(notional * _decimal(config.trading_fee_rate))
    transaction_levy = _round_cent(notional * _decimal(config.transaction_levy_rate))
    afrc_levy = _round_cent(notional * _decimal(config.afrc_transaction_levy_rate))
    settlement_fee = _round_cent(notional * _decimal(config.settlement_fee_rate))
    slippage = _decimal(quantity) * abs(_decimal(execution_price) - _decimal(raw_price))
    total = (
        commission + stamp + trading_fee + transaction_levy + afrc_levy + settlement_fee + slippage
    )
    return execution_price, CostBreakdown(
        broker_commission=float(commission),
        stamp_duty=float(stamp),
        trading_fee=float(trading_fee),
        transaction_levy=float(transaction_levy),
        afrc_transaction_levy=float(afrc_levy),
        settlement_fee=float(settlement_fee),
        slippage_cost=float(slippage),
        total_cost=float(total),
    )


def combine_costs(*costs: CostBreakdown) -> CostBreakdown:
    if not costs:
        return CostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    fields = (
        "broker_commission",
        "stamp_duty",
        "trading_fee",
        "transaction_levy",
        "afrc_transaction_levy",
        "settlement_fee",
        "slippage_cost",
        "total_cost",
    )
    values = {field: math.fsum(getattr(cost, field) for cost in costs) for field in fields}
    return CostBreakdown(**values)
