from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta, timezone
from numbers import Integral, Real
from typing import Callable, Literal
from zoneinfo import ZoneInfo

import pandas as pd

from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.models import MarketDataMetadata, MarketDataResult

SPY_SYMBOL = "SPY"
SPY_SOURCE = "Yahoo Finance via yfinance"
SPY_ADJUSTMENT_METHOD = (
    "adjusted_close/raw_close ratio applied to raw OHLC; volume retained unadjusted"
)
RAW_PRICE_COLUMNS = (
    "date",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
    "adjusted_close",
    "volume",
)
STANDARD_PRICE_COLUMNS = ("date", "open", "high", "low", "close", "volume")
_NEW_YORK = ZoneInfo("America/New_York")
MarketDataStage = Literal["market_data_fetch", "market_data_standardize"]
MarketDataStageCallback = Callable[[MarketDataStage], None]


def _require_date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime.date.")
    return value


def _require_lookback(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError("longest_lookback must be a positive integer.")
    return int(value)


def _to_market_date(value: object, row_label: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"field='date', date=row[{row_label!r}], actual={value!r}: cannot parse date."
        ) from exc
    if pd.isna(timestamp):
        raise ValueError(
            f"field='date', date=row[{row_label!r}], actual={value!r}: date must not be missing."
        )
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(_NEW_YORK)
    return timestamp.date()


def _missing_column_error(column: str) -> ValueError:
    return ValueError(f"field={column!r}, date=N/A, actual=<missing>: required column is absent.")


def _numeric_values(
    frame: pd.DataFrame,
    column: str,
    *,
    positive: bool,
) -> list[float]:
    values: list[float] = []
    for row_index, value in enumerate(frame[column]):
        market_date = frame["date"].iloc[row_index]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(
                f"field={column!r}, date={market_date.isoformat()}, actual={value!r}: "
                "value must have a numeric type."
            )
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(
                f"field={column!r}, date={market_date.isoformat()}, actual={value!r}: "
                "value must be finite."
            )
        if positive and number <= 0:
            raise ValueError(
                f"field={column!r}, date={market_date.isoformat()}, actual={value!r}: "
                "price must be greater than zero."
            )
        if not positive and number < 0:
            raise ValueError(
                f"field={column!r}, date={market_date.isoformat()}, actual={value!r}: "
                "volume must be non-negative."
            )
        values.append(number)
    return values


def validate_standardized_prices(
    prices: pd.DataFrame,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    longest_lookback: int | None = None,
) -> None:
    """Validate standardized adjusted OHLCV without mutating the input."""
    for column in STANDARD_PRICE_COLUMNS:
        if column not in prices.columns:
            raise _missing_column_error(column)
    if prices.empty:
        raise ValueError("field='prices', date=N/A, actual=0 rows: at least one row is required.")

    dates = [_to_market_date(value, row_label) for row_label, value in prices["date"].items()]
    seen: set[date] = set()
    for row_index, market_date in enumerate(dates):
        if market_date in seen:
            raise ValueError(
                f"field='date', date={market_date.isoformat()}, actual=duplicate: "
                "trading dates must be unique."
            )
        seen.add(market_date)
        if row_index and market_date <= dates[row_index - 1]:
            raise ValueError(
                f"field='date', date={market_date.isoformat()}, "
                f"actual={dates[row_index - 1].isoformat()} -> {market_date.isoformat()}: "
                "trading dates must be strictly ascending."
            )

    checked = prices.loc[:, STANDARD_PRICE_COLUMNS].copy()
    checked["date"] = dates
    for column in ("open", "high", "low", "close"):
        checked[column] = _numeric_values(checked, column, positive=True)
    checked["volume"] = _numeric_values(checked, "volume", positive=False)

    for row in checked.itertuples(index=False):
        if row.low > row.open:
            raise ValueError(
                f"field='low', date={row.date.isoformat()}, actual={row.low!r}: "
                f"low must be <= open ({row.open!r})."
            )
        if row.low > row.close:
            raise ValueError(
                f"field='low', date={row.date.isoformat()}, actual={row.low!r}: "
                f"low must be <= close ({row.close!r})."
            )
        if row.high < row.open:
            raise ValueError(
                f"field='high', date={row.date.isoformat()}, actual={row.high!r}: "
                f"high must be >= open ({row.open!r})."
            )
        if row.high < row.close:
            raise ValueError(
                f"field='high', date={row.date.isoformat()}, actual={row.high!r}: "
                f"high must be >= close ({row.close!r})."
            )
        if row.low > row.high:
            raise ValueError(
                f"field='low', date={row.date.isoformat()}, actual={row.low!r}: "
                f"low must be <= high ({row.high!r})."
            )

    supplied_interval = start_date is not None or end_date is not None
    if supplied_interval:
        if start_date is None or end_date is None:
            raise ValueError("start_date and end_date must be supplied together.")
        start = _require_date(start_date, "start_date")
        end = _require_date(end_date, "end_date")
        if start > end:
            raise ValueError("start_date must not be after end_date.")
        analysis_dates = [value for value in dates if start <= value <= end]
        if not analysis_dates:
            raise ValueError(
                f"field='analysis_date_range', date={start.isoformat()}..{end.isoformat()}, "
                "actual=0 rows: user interval contains no valid trading day."
            )
        if longest_lookback is not None:
            lookback = _require_lookback(longest_lookback)
            warmup_count = sum(value < start for value in dates)
            if warmup_count < lookback:
                raise ValueError(
                    f"field='warmup_row_count', date={analysis_dates[0].isoformat()}, "
                    f"actual={warmup_count}: requires at least {lookback} trading rows."
                )
    elif longest_lookback is not None:
        raise ValueError("start_date and end_date are required when longest_lookback is supplied.")


def standardize_adjusted_ohlcv(raw_prices: pd.DataFrame) -> pd.DataFrame:
    """Apply one adjusted-close ratio to every raw OHLC value for each day."""
    for column in RAW_PRICE_COLUMNS:
        if column not in raw_prices.columns:
            raise _missing_column_error(column)
    if raw_prices.empty:
        raise ValueError(
            "field='raw_prices', date=N/A, actual=0 rows: at least one row is required."
        )

    frame = raw_prices.loc[:, RAW_PRICE_COLUMNS].copy()
    frame["date"] = [
        _to_market_date(value, row_label) for row_label, value in frame["date"].items()
    ]
    frame = frame.sort_values("date", kind="mergesort").reset_index(drop=True)
    duplicate_mask = frame["date"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicate = frame.loc[duplicate_mask, "date"].iloc[0]
        count = int((frame["date"] == duplicate).sum())
        raise ValueError(
            f"field='date', date={duplicate.isoformat()}, actual={count} rows: "
            "duplicate trading date after timezone mapping."
        )

    for column in ("raw_open", "raw_high", "raw_low", "raw_close", "adjusted_close"):
        frame[column] = _numeric_values(frame, column, positive=True)
    frame["volume"] = _numeric_values(frame, "volume", positive=False)

    output_rows: list[dict[str, object]] = []
    for row in frame.itertuples(index=False):
        if row.raw_low > min(row.raw_open, row.raw_close):
            raise ValueError(
                f"field='raw_low', date={row.date.isoformat()}, actual={row.raw_low!r}: "
                "raw_low must be <= raw_open and raw_close."
            )
        if row.raw_high < max(row.raw_open, row.raw_close):
            raise ValueError(
                f"field='raw_high', date={row.date.isoformat()}, actual={row.raw_high!r}: "
                "raw_high must be >= raw_open and raw_close."
            )
        if row.raw_low > row.raw_high:
            raise ValueError(
                f"field='raw_low', date={row.date.isoformat()}, actual={row.raw_low!r}: "
                f"raw_low must be <= raw_high ({row.raw_high!r})."
            )

        factor = row.adjusted_close / row.raw_close
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError(
                f"field='adjustment_factor', date={row.date.isoformat()}, "
                f"actual={factor!r}: factor must be finite and greater than zero."
            )
        adjusted_values = {
            "open": row.raw_open * factor,
            "high": row.raw_high * factor,
            "low": row.raw_low * factor,
            "close": row.raw_close * factor,
        }
        for field, value in adjusted_values.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(
                    f"field={field!r}, date={row.date.isoformat()}, actual={value!r}: "
                    "adjusted price must be finite and greater than zero."
                )
        output_rows.append(
            {
                "date": row.date,
                **adjusted_values,
                "volume": row.volume,
            }
        )

    standardized = pd.DataFrame(output_rows, columns=STANDARD_PRICE_COLUMNS)
    validate_standardized_prices(standardized)
    return standardized


def adapt_yfinance_history(raw_history: pd.DataFrame) -> pd.DataFrame:
    """Map an unadjusted yfinance history table to the provider-neutral raw schema."""
    if not isinstance(raw_history, pd.DataFrame):
        raise TypeError("raw_history must be a pandas DataFrame.")
    if isinstance(raw_history.columns, pd.MultiIndex):
        raise ValueError(
            "field='columns', date=N/A, actual=MultiIndex: single-ticker SPY history required."
        )

    frame = raw_history.copy()
    normalized_names = {
        str(column).strip().lower().replace(" ", "_"): column for column in frame.columns
    }
    if "date" not in normalized_names:
        frame = frame.reset_index()
        normalized_names = {
            str(column).strip().lower().replace(" ", "_"): column for column in frame.columns
        }

    aliases = {
        "date": "date",
        "open": "raw_open",
        "high": "raw_high",
        "low": "raw_low",
        "close": "raw_close",
        "adj_close": "adjusted_close",
        "volume": "volume",
    }
    output: dict[str, pd.Series] = {}
    for provider_name, canonical_name in aliases.items():
        original_name = normalized_names.get(provider_name)
        if original_name is None:
            raise _missing_column_error(provider_name)
        output[canonical_name] = frame[original_name]
    return pd.DataFrame(output, index=frame.index).reset_index(drop=True)


def _normalize_fetched_at(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("fetched_at_utc must be a timezone-aware datetime.")
    return value.astimezone(timezone.utc)


def build_spy_market_data_result(
    raw_history: pd.DataFrame,
    start_date: date,
    end_date: date,
    longest_lookback: int,
    *,
    fetched_at_utc: datetime,
    source_version: str,
    source: str = SPY_SOURCE,
) -> MarketDataResult:
    """Pure offline construction of the Phase 1 SPY market-data result."""
    start = _require_date(start_date, "start_date")
    end = _require_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date.")
    lookback = _require_lookback(longest_lookback)
    fetched_at = _normalize_fetched_at(fetched_at_utc)
    canonical_raw = adapt_yfinance_history(raw_history)
    standardized = standardize_adjusted_ohlcv(canonical_raw)
    standardized = standardized.loc[standardized["date"] <= end].reset_index(drop=True)
    validate_standardized_prices(
        standardized,
        start_date=start,
        end_date=end,
        longest_lookback=lookback,
    )

    warmup = standardized.loc[standardized["date"] < start].tail(lookback)
    analysis = standardized.loc[(standardized["date"] >= start) & (standardized["date"] <= end)]
    prices = pd.concat([warmup, analysis], ignore_index=True)
    prices = prices.loc[:, STANDARD_PRICE_COLUMNS]
    validate_standardized_prices(
        prices,
        start_date=start,
        end_date=end,
        longest_lookback=lookback,
    )
    data_sha256 = calculate_market_data_sha256(prices)

    metadata = MarketDataMetadata(
        symbol=SPY_SYMBOL,
        source=source,
        source_version=source_version,
        fetched_at_utc=fetched_at,
        requested_start_date=start,
        requested_end_date=end,
        actual_start_date=prices["date"].iloc[0],
        actual_end_date=prices["date"].iloc[-1],
        analysis_start_date=analysis["date"].iloc[0],
        analysis_end_date=analysis["date"].iloc[-1],
        longest_lookback=lookback,
        warmup_row_count=len(warmup),
        analysis_row_count=len(analysis),
        total_row_count=len(prices),
        adjustment_method=SPY_ADJUSTMENT_METHOD,
        data_sha256=data_sha256,
    )
    return MarketDataResult(prices=prices, metadata=metadata)


def fetch_spy_raw_yfinance(
    fetch_start_date: date,
    fetch_end_date: date,
) -> tuple[pd.DataFrame, str]:
    """Network-only SPY provider call; end date is inclusive at this boundary."""
    if os.environ.get("QUANTLAB_OFFLINE") == "1":
        raise RuntimeError("SPY provider access is disabled by QUANTLAB_OFFLINE=1.")
    start = _require_date(fetch_start_date, "fetch_start_date")
    end = _require_date(fetch_end_date, "fetch_end_date")
    if start > end:
        raise ValueError("fetch_start_date must not be after fetch_end_date.")

    import yfinance as yf

    history = yf.Ticker(SPY_SYMBOL).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
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
        raise ValueError(
            f"field='provider_rows', date={start.isoformat()}..{end.isoformat()}, "
            "actual=0 rows: yfinance returned no SPY history."
        )
    return history, str(yf.__version__)


def load_spy_adjusted_daily(
    start_date: date,
    end_date: date,
    longest_lookback: int,
    *,
    fetched_at_utc: datetime | None = None,
    stage_callback: MarketDataStageCallback | None = None,
) -> MarketDataResult:
    """Fetch and validate the only Phase 1 production market-data path."""
    start = _require_date(start_date, "start_date")
    end = _require_date(end_date, "end_date")
    if start > end:
        raise ValueError("start_date must not be after end_date.")
    lookback = _require_lookback(longest_lookback)
    calendar_buffer_days = max(30, lookback * 2 + 14)
    fetch_start = start - timedelta(days=calendar_buffer_days)
    if stage_callback is not None:
        stage_callback("market_data_fetch")
    raw_history, provider_version = fetch_spy_raw_yfinance(fetch_start, end)
    if stage_callback is not None:
        stage_callback("market_data_standardize")
    fetch_timestamp = fetched_at_utc or datetime.now(timezone.utc)
    return build_spy_market_data_result(
        raw_history,
        start,
        end,
        lookback,
        fetched_at_utc=fetch_timestamp,
        source=SPY_SOURCE,
        source_version=provider_version,
    )
