from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from quant_lab.application.hk_serialization import serialize_hk_run
from quant_lab.application.hk_workflow import HKRunRequest, run_hk_sma_workflow
from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.market.hk.models import (
    BoardLotConfig,
    BoardLotSource,
    HKSymbol,
    HKTradingCostConfig,
)
from quant_lab.models import MarketDataMetadata, MarketDataResult
from quant_lab.providers.base import ProviderMetadata, SymbolMetadata

_SMOKE_TIME = datetime(2024, 1, 6, tzinfo=timezone.utc)
_DATES = (
    date(2023, 12, 28),
    date(2023, 12, 29),
    date(2024, 1, 2),
    date(2024, 1, 3),
    date(2024, 1, 4),
    date(2024, 1, 5),
)


def _fixed_market_data(
    symbol: str,
    closes: tuple[float, ...],
    opens: tuple[float, ...],
) -> MarketDataResult:
    prices = pd.DataFrame(
        {
            "date": _DATES,
            "open": opens,
            "high": [max(open_, close) + 1 for open_, close in zip(opens, closes)],
            "low": [min(open_, close) - 1 for open_, close in zip(opens, closes)],
            "close": closes,
            "volume": [1_000_000.0] * len(_DATES),
        }
    )
    metadata = MarketDataMetadata(
        symbol=symbol,
        source="Bundled offline smoke fixture",
        source_version="1",
        fetched_at_utc=_SMOKE_TIME,
        requested_start_date=date(2024, 1, 2),
        requested_end_date=date(2024, 1, 5),
        actual_start_date=_DATES[0],
        actual_end_date=_DATES[-1],
        analysis_start_date=date(2024, 1, 2),
        analysis_end_date=date(2024, 1, 5),
        longest_lookback=2,
        warmup_row_count=2,
        analysis_row_count=4,
        total_row_count=6,
        adjustment_method="fixed adjusted OHLC",
        data_sha256=calculate_market_data_sha256(prices),
    )
    return MarketDataResult(prices=prices, metadata=metadata)


class _OfflineSmokeProvider:
    def __init__(self) -> None:
        self.results = {
            "0700.HK": _fixed_market_data(
                "0700.HK",
                (8.0, 9.0, 10.0, 12.0, 8.0, 13.0),
                (8.0, 9.0, 10.0, 11.0, 9.0, 12.0),
            ),
            "2800.HK": _fixed_market_data(
                "2800.HK",
                (5.0, 5.0, 5.0, 5.5, 5.8, 6.0),
                (5.0, 5.0, 5.0, 5.4, 5.7, 5.9),
            ),
        }

    def get_daily_prices(
        self,
        symbol: HKSymbol,
        start_date: date,
        end_date: date,
        longest_lookback: int,
        *,
        fetched_at_utc: datetime | None = None,
        force_refresh: bool = False,
    ) -> MarketDataResult:
        del start_date, end_date, longest_lookback, fetched_at_utc, force_refresh
        return self.results[symbol.normalized_symbol]

    def get_symbol_metadata(self, symbol: HKSymbol) -> SymbolMetadata:
        return SymbolMetadata(symbol=symbol, display_name=None)

    def get_board_lot(self, symbol: HKSymbol) -> BoardLotConfig | None:
        del symbol
        return None

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            name="Bundled offline smoke fixture",
            version="1",
            adjustment_policy="fixed adjusted OHLC",
        )


def run_offline_hk_smoke() -> dict[str, object]:
    """Execute a deterministic HK vertical slice without network or local persistence."""
    board_lot = BoardLotConfig(
        lot_size=100,
        source=BoardLotSource.USER,
        verified_at=_SMOKE_TIME,
        confirmed=True,
    )
    zero_costs = HKTradingCostConfig(
        broker_commission_rate=0.0,
        broker_minimum_commission=0.0,
        stamp_duty_rate=0.0,
        trading_fee_rate=0.0,
        transaction_levy_rate=0.0,
        afrc_transaction_levy_rate=0.0,
        settlement_fee_rate=0.0,
        slippage_rate=0.0,
    )
    request = HKRunRequest(
        symbol="0700.HK",
        benchmark_symbol="2800.HK",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 5),
        short_window=1,
        long_window=2,
        initial_capital=10_000.0,
        board_lot=board_lot,
        benchmark_board_lot=board_lot,
        costs=zero_costs,
        benchmark_costs=zero_costs,
    )
    result = serialize_hk_run(
        run_hk_sma_workflow(
            request,
            provider=_OfflineSmokeProvider(),
            created_at_utc=_SMOKE_TIME,
        )
    )
    if result["strategy_metrics"]["final_equity"] != 12_000.0:
        raise RuntimeError("The bundled HK smoke result did not match its fixed equity.")
    if result["symbol"]["normalized_symbol"] != "0700.HK":
        raise RuntimeError("The bundled HK smoke result used an unexpected symbol.")
    return result
