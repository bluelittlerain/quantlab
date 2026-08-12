from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from quant_lab.application.errors import QuantLabApplicationError
from quant_lab.application.hk_serialization import serialize_hk_run
from quant_lab.application.hk_workflow import HKRunRequest, run_hk_sma_workflow
from quant_lab.market.hk.symbols import normalize_hk_symbol
from quant_lab.providers.base import MarketDataProvider
from quant_lab.storage.repositories import QuantLabRepository


@dataclass
class BacktestApplicationService:
    """Deployment-neutral orchestration over the shared HK research core."""

    provider: MarketDataProvider
    repository: QuantLabRepository
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def execute(self, request: HKRunRequest, *, force_refresh: bool = False) -> dict[str, Any]:
        output = run_hk_sma_workflow(
            request,
            provider=self.provider,
            force_refresh=force_refresh,
        )
        strategy = output.comparison.strategy
        if not strategy.trades and "当前资金不足以买入一手。" in strategy.warnings:
            symbol = normalize_hk_symbol(request.symbol).normalized_symbol
            raise QuantLabApplicationError(
                "INSUFFICIENT_CAPITAL",
                f"初始资金不足以买入一手 {symbol}。",
                "initial_capital",
                {"board_lot": request.board_lot.lot_size},
            )

        result = serialize_hk_run(output)
        self.repository.save_run(result)
        self._remember_board_lots(request)
        return result

    def _remember_board_lots(self, request: HKRunRequest) -> None:
        settings = self.repository.get_settings()
        stored = dict(settings.get("board_lots", {}))
        verified_at = self.clock().astimezone(timezone.utc).isoformat()
        for symbol, board_lot in (
            (normalize_hk_symbol(request.symbol), request.board_lot),
            (normalize_hk_symbol(request.benchmark_symbol), request.benchmark_board_lot),
        ):
            stored[symbol.normalized_symbol] = {
                "lot_size": board_lot.lot_size,
                "verified_at": verified_at,
            }
        self.repository.put_settings({"board_lots": stored})
