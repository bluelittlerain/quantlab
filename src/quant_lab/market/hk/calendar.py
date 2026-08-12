from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class HKCalendarValidation:
    expected_sessions: tuple[date, ...]
    observed_sessions: tuple[date, ...]
    missing_expected_sessions: tuple[date, ...]
    unexpected_sessions: tuple[date, ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_expected_sessions and not self.unexpected_sessions


@lru_cache(maxsize=1)
def _calendar():
    import exchange_calendars as exchange_calendars

    return exchange_calendars.get_calendar("XHKG")


def hkex_sessions(start_date: date, end_date: date) -> tuple[date, ...]:
    if start_date > end_date:
        raise ValueError("start_date must not be later than end_date.")
    sessions = _calendar().sessions_in_range(
        pd.Timestamp(start_date),
        pd.Timestamp(end_date),
    )
    return tuple(pd.Timestamp(value).date() for value in sessions)


def validate_hk_trading_sessions(
    observed_dates: Iterable[date],
    *,
    start_date: date,
    end_date: date,
) -> HKCalendarValidation:
    expected = hkex_sessions(start_date, end_date)
    observed = tuple(sorted(set(observed_dates)))
    expected_set = set(expected)
    observed_set = {value for value in observed if start_date <= value <= end_date}
    return HKCalendarValidation(
        expected_sessions=expected,
        observed_sessions=tuple(sorted(observed_set)),
        missing_expected_sessions=tuple(sorted(expected_set - observed_set)),
        unexpected_sessions=tuple(sorted(observed_set - expected_set)),
    )
