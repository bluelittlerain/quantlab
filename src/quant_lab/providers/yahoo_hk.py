from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from quant_lab.market.common.normalized_data import build_adjusted_market_data_result
from quant_lab.market.hk.models import BoardLotConfig, HKSymbol
from quant_lab.models import MarketDataResult
from quant_lab.providers.base import ProviderMetadata, SymbolMetadata

YAHOO_HK_SOURCE = "Yahoo Finance via yfinance"
YAHOO_HK_ADJUSTMENT = (
    "adjusted_close/raw_close ratio applied to raw OHLC; distributions are reflected "
    "in adjusted prices rather than booked as cash"
)


class YahooHKProvider:
    """Network adapter. Application and domain layers never import yfinance directly."""

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
        del force_refresh
        if os.environ.get("QUANTLAB_OFFLINE") == "1":
            raise RuntimeError("provider access is disabled by QUANTLAB_OFFLINE=1.")
        if start_date > end_date:
            raise ValueError("start_date must not be later than end_date.")
        fetch_start = start_date - timedelta(days=max(45, longest_lookback * 2 + 20))
        raw_history, provider_version = self._fetch_history(symbol, fetch_start, end_date)
        return build_adjusted_market_data_result(
            symbol=symbol.normalized_symbol,
            raw_history=raw_history,
            start_date=start_date,
            end_date=end_date,
            longest_lookback=longest_lookback,
            fetched_at_utc=fetched_at_utc or datetime.now(timezone.utc),
            source=YAHOO_HK_SOURCE,
            source_version=provider_version,
            adjustment_method=YAHOO_HK_ADJUSTMENT,
        )

    @staticmethod
    def _fetch_history(
        symbol: HKSymbol,
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame, str]:
        import yfinance as yf

        history = yf.Ticker(symbol.normalized_symbol).history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
            repair=False,
            keepna=True,
            rounding=False,
            timeout=20,
            raise_errors=True,
        )
        if history.empty:
            raise ValueError("DATA_NOT_FOUND: provider returned no daily rows.")
        return history, str(yf.__version__)

    def get_symbol_metadata(self, symbol: HKSymbol) -> SymbolMetadata:
        return SymbolMetadata(symbol=symbol, display_name=None)

    def get_board_lot(self, symbol: HKSymbol) -> BoardLotConfig | None:
        del symbol
        return None

    def get_provider_metadata(self) -> ProviderMetadata:
        import yfinance as yf

        return ProviderMetadata(
            name=YAHOO_HK_SOURCE,
            version=str(yf.__version__),
            adjustment_policy=YAHOO_HK_ADJUSTMENT,
        )
