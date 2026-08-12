from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.models import MarketDataMetadata, MarketDataResult

G06_EXPECTED_FINAL_EQUITY = 1152.9457896285
G06_EXPECTED_TOTAL_RETURN = 0.152945789628
G06_EXPECTED_TOTAL_FEES = 21.5469071660
G06_EXPECTED_TOTAL_SLIPPAGE = 21.5665130870


def _analysis_dates(start_date: date, end_date: date) -> list[date]:
    dates = [value.date() for value in pd.bdate_range(start=start_date, end=end_date)]
    if len(dates) < 3:
        raise ValueError("offline workflow fixture requires at least three business days")
    return dates[:3]


def build_workflow_market_data(
    start_date: date,
    end_date: date,
    longest_lookback: int,
    *,
    fetched_at_utc: datetime,
    flat: bool = False,
    symbol: str = "SPY",
) -> MarketDataResult:
    """Create a deterministic provider result for workflow and Streamlit tests."""
    if longest_lookback != 60:
        raise ValueError("offline workflow fixture is fixed to a 60-day lookback")

    analysis_dates = _analysis_dates(start_date, end_date)
    warmup_dates = [
        value.date()
        for value in pd.bdate_range(
            end=pd.Timestamp(analysis_dates[0]) - pd.offsets.BDay(1),
            periods=longest_lookback,
        )
    ]
    warmup_closes = [100.0] * longest_lookback
    if not flat:
        # These fixed closes make the real SMA implementation emit 0 on the
        # final warmup day and 1, 0, 0 on the three analysis closes.
        warmup_closes[0] = 500.0
        warmup_closes[40] = 1.0
        warmup_closes[41] = 300.0

    rows: list[dict[str, object]] = []
    for market_date, close in zip(warmup_dates, warmup_closes):
        rows.append(
            {
                "date": market_date,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000.0,
            }
        )

    if flat:
        analysis_ohlc = (
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 100.0, 100.0, 100.0),
        )
    else:
        analysis_ohlc = (
            (100.0, 100.0, 100.0, 100.0),
            (100.0, 110.0, 100.0, 110.0),
            (120.0, 120.0, 120.0, 120.0),
        )
    for market_date, (open_, high, low, close) in zip(
        analysis_dates,
        analysis_ohlc,
    ):
        rows.append(
            {
                "date": market_date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0,
            }
        )

    prices = pd.DataFrame(rows)
    metadata = MarketDataMetadata(
        symbol=symbol,
        source="fixed-workflow-fixture",
        source_version="1",
        fetched_at_utc=fetched_at_utc,
        requested_start_date=start_date,
        requested_end_date=end_date,
        actual_start_date=warmup_dates[0],
        actual_end_date=analysis_dates[-1],
        analysis_start_date=analysis_dates[0],
        analysis_end_date=analysis_dates[-1],
        longest_lookback=longest_lookback,
        warmup_row_count=len(warmup_dates),
        analysis_row_count=len(analysis_dates),
        total_row_count=len(prices),
        adjustment_method="fixed adjusted OHLC fixture",
        data_sha256=calculate_market_data_sha256(prices),
    )
    return MarketDataResult(prices=prices, metadata=metadata)


class RecordingMarketDataLoader:
    def __init__(self, *, flat: bool = False, symbol: str = "SPY") -> None:
        self.flat = flat
        self.symbol = symbol
        self.calls: list[tuple[date, date, int, datetime]] = []

    def __call__(
        self,
        start_date: date,
        end_date: date,
        longest_lookback: int,
        *,
        fetched_at_utc: datetime,
    ) -> MarketDataResult:
        self.calls.append((start_date, end_date, longest_lookback, fetched_at_utc))
        return build_workflow_market_data(
            start_date,
            end_date,
            longest_lookback,
            fetched_at_utc=fetched_at_utc,
            flat=self.flat,
            symbol=self.symbol,
        )
