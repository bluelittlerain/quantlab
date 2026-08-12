from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from quant_lab.market.hk.models import BoardLotConfig, HKSymbol
from quant_lab.models import MarketDataResult


@dataclass(frozen=True)
class SymbolMetadata:
    symbol: HKSymbol
    display_name: str | None


@dataclass(frozen=True)
class ProviderMetadata:
    name: str
    version: str
    adjustment_policy: str


class MarketDataProvider(Protocol):
    def get_daily_prices(
        self,
        symbol: HKSymbol,
        start_date: date,
        end_date: date,
        longest_lookback: int,
        *,
        fetched_at_utc: datetime | None = None,
        force_refresh: bool = False,
    ) -> MarketDataResult: ...

    def get_symbol_metadata(self, symbol: HKSymbol) -> SymbolMetadata: ...

    def get_board_lot(self, symbol: HKSymbol) -> BoardLotConfig | None: ...

    def get_provider_metadata(self) -> ProviderMetadata: ...
