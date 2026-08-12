"""Hong Kong market domain."""

from quant_lab.market.hk.models import (
    BoardLotConfig,
    BoardLotSource,
    CostBreakdown,
    ExecutionMode,
    HKBacktestConfig,
    HKBacktestResult,
    HKComparisonResult,
    HKPerformanceMetrics,
    HKSymbol,
    HKTradeRecord,
    HKTradingCostConfig,
    TradeSide,
)
from quant_lab.market.hk.symbols import normalize_hk_symbol

__all__ = [
    "BoardLotConfig",
    "BoardLotSource",
    "CostBreakdown",
    "ExecutionMode",
    "HKBacktestConfig",
    "HKBacktestResult",
    "HKComparisonResult",
    "HKPerformanceMetrics",
    "HKSymbol",
    "HKTradeRecord",
    "HKTradingCostConfig",
    "TradeSide",
    "normalize_hk_symbol",
]
