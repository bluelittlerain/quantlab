from __future__ import annotations

import hashlib
import math
from datetime import date, datetime
from numbers import Real
from zoneinfo import ZoneInfo

import pandas as pd

FINGERPRINT_COLUMNS = ("date", "open", "high", "low", "close", "volume")
_NEW_YORK = ZoneInfo("America/New_York")


def _market_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("field='date', date=N/A, actual=<missing>: invalid date.")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(_NEW_YORK)
    return timestamp.date()


def canonical_market_data_bytes(prices: pd.DataFrame) -> bytes:
    """Serialize standardized OHLCV with locale- and index-independent bytes."""
    missing = [column for column in FINGERPRINT_COLUMNS if column not in prices.columns]
    if missing:
        raise ValueError(
            f"field={missing[0]!r}, date=N/A, actual=<missing>: required fingerprint column."
        )

    frame = prices.loc[:, FINGERPRINT_COLUMNS].copy()
    converted_dates: list[date] = []
    for row_label, value in frame["date"].items():
        try:
            converted_dates.append(_market_date(value))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"field='date', date=row[{row_label!r}], actual={value!r}: "
                "cannot map to an America/New_York trading date."
            ) from exc
    frame["date"] = converted_dates
    frame = frame.sort_values("date", kind="mergesort").reset_index(drop=True)
    duplicate_mask = frame["date"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicate = frame.loc[duplicate_mask, "date"].iloc[0]
        count = int((frame["date"] == duplicate).sum())
        raise ValueError(
            f"field='date', date={duplicate.isoformat()}, actual={count} rows: "
            "duplicate trading date."
        )

    for column in FINGERPRINT_COLUMNS[1:]:
        converted: list[float] = []
        for row_index, value in enumerate(frame[column]):
            market_date = frame["date"].iloc[row_index]
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(
                    f"field={column!r}, date={market_date.isoformat()}, "
                    f"actual={value!r}: value must have a numeric type."
                )
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(
                    f"field={column!r}, date={market_date.isoformat()}, "
                    f"actual={value!r}: value must be finite."
                )
            if column == "volume":
                if number < 0:
                    raise ValueError(
                        f"field='volume', date={market_date.isoformat()}, "
                        f"actual={value!r}: volume must be non-negative."
                    )
            elif number <= 0:
                raise ValueError(
                    f"field={column!r}, date={market_date.isoformat()}, "
                    f"actual={value!r}: price must be greater than zero."
                )
            converted.append(0.0 if number == 0.0 else number)
        frame[column] = converted

    lines = [",".join(FINGERPRINT_COLUMNS)]
    for row in frame.itertuples(index=False):
        lines.append(
            ",".join(
                [
                    row.date.isoformat(),
                    f"{row.open:.10f}",
                    f"{row.high:.10f}",
                    f"{row.low:.10f}",
                    f"{row.close:.10f}",
                    f"{row.volume:.10f}",
                ]
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def calculate_market_data_sha256(prices: pd.DataFrame) -> str:
    return hashlib.sha256(canonical_market_data_bytes(prices)).hexdigest()
