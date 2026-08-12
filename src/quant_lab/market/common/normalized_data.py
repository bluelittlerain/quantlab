from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from quant_lab.data import (
    STANDARD_PRICE_COLUMNS,
    adapt_yfinance_history,
    standardize_adjusted_ohlcv,
    validate_standardized_prices,
)
from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.models import MarketDataMetadata, MarketDataResult

_HONG_KONG = ZoneInfo("Asia/Hong_Kong")


def _hk_market_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("HK provider date must not be missing.")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(_HONG_KONG)
    return timestamp.date()


def build_adjusted_market_data_result(
    *,
    symbol: str,
    raw_history: pd.DataFrame,
    start_date: date,
    end_date: date,
    longest_lookback: int,
    fetched_at_utc: datetime,
    source: str,
    source_version: str,
    adjustment_method: str,
) -> MarketDataResult:
    """Build provider-neutral adjusted OHLC while preserving HK trading dates."""
    if start_date > end_date:
        raise ValueError("start_date must not be later than end_date.")
    if longest_lookback <= 0:
        raise ValueError("longest_lookback must be greater than zero.")
    if fetched_at_utc.tzinfo is None:
        raise ValueError("fetched_at_utc must be timezone-aware.")
    fetched_at = fetched_at_utc.astimezone(timezone.utc)

    canonical_raw = adapt_yfinance_history(raw_history)
    canonical_raw["date"] = [_hk_market_date(value) for value in canonical_raw["date"]]
    standardized = standardize_adjusted_ohlcv(canonical_raw)
    standardized = standardized.loc[standardized["date"] <= end_date].reset_index(drop=True)
    validate_standardized_prices(
        standardized,
        start_date=start_date,
        end_date=end_date,
        longest_lookback=longest_lookback,
    )
    warmup = standardized.loc[standardized["date"] < start_date].tail(longest_lookback)
    analysis = standardized.loc[
        (standardized["date"] >= start_date) & (standardized["date"] <= end_date)
    ]
    prices = pd.concat([warmup, analysis], ignore_index=True).loc[:, STANDARD_PRICE_COLUMNS]
    validate_standardized_prices(
        prices,
        start_date=start_date,
        end_date=end_date,
        longest_lookback=longest_lookback,
    )
    metadata = MarketDataMetadata(
        symbol=symbol,
        source=source,
        source_version=source_version,
        fetched_at_utc=fetched_at,
        requested_start_date=start_date,
        requested_end_date=end_date,
        actual_start_date=prices["date"].iloc[0],
        actual_end_date=prices["date"].iloc[-1],
        analysis_start_date=analysis["date"].iloc[0],
        analysis_end_date=analysis["date"].iloc[-1],
        longest_lookback=longest_lookback,
        warmup_row_count=len(warmup),
        analysis_row_count=len(analysis),
        total_row_count=len(prices),
        adjustment_method=adjustment_method,
        data_sha256=calculate_market_data_sha256(prices),
    )
    return MarketDataResult(prices=prices, metadata=metadata)
