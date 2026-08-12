from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.market.hk.models import HKSymbol
from quant_lab.models import MarketDataMetadata, MarketDataResult
from quant_lab.providers.base import ProviderMetadata, SymbolMetadata


def fixed_market_data(
    symbol: str,
    *,
    closes: tuple[float, ...],
    opens: tuple[float, ...] | None = None,
) -> MarketDataResult:
    dates = (
        date(2023, 12, 28),
        date(2023, 12, 29),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    )
    if len(closes) != len(dates):
        raise ValueError("fixed closes must contain six values.")
    resolved_opens = opens or closes
    prices = pd.DataFrame(
        {
            "date": dates,
            "open": resolved_opens,
            "high": [
                max(open_value, close_value) + 1
                for open_value, close_value in zip(resolved_opens, closes)
            ],
            "low": [
                min(open_value, close_value) - 1
                for open_value, close_value in zip(resolved_opens, closes)
            ],
            "close": closes,
            "volume": [1_000_000.0] * len(dates),
        }
    )
    metadata = MarketDataMetadata(
        symbol=symbol,
        source="Fixed HK fixture",
        source_version="1",
        fetched_at_utc=datetime(2024, 1, 6, tzinfo=timezone.utc),
        requested_start_date=date(2024, 1, 2),
        requested_end_date=date(2024, 1, 5),
        actual_start_date=dates[0],
        actual_end_date=dates[-1],
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


class FixedHKProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.results = {
            "0700.HK": fixed_market_data(
                "0700.HK",
                closes=(8.0, 9.0, 10.0, 12.0, 8.0, 13.0),
                opens=(8.0, 9.0, 10.0, 11.0, 9.0, 12.0),
            ),
            "2800.HK": fixed_market_data(
                "2800.HK",
                closes=(5.0, 5.0, 5.0, 5.5, 5.8, 6.0),
                opens=(5.0, 5.0, 5.0, 5.4, 5.7, 5.9),
            ),
        }

    def get_daily_prices(
        self,
        symbol: HKSymbol,
        start_date,
        end_date,
        longest_lookback,
        *,
        fetched_at_utc=None,
        force_refresh=False,
    ) -> MarketDataResult:
        del start_date, end_date, longest_lookback, fetched_at_utc
        self.calls.append((symbol.normalized_symbol, force_refresh))
        return self.results[symbol.normalized_symbol]

    def get_symbol_metadata(self, symbol: HKSymbol) -> SymbolMetadata:
        return SymbolMetadata(symbol=symbol, display_name=None)

    def get_board_lot(self, symbol: HKSymbol):
        del symbol
        return None

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata("Fixed HK fixture", "1", "fixed adjusted OHLC")
