from __future__ import annotations

from numbers import Integral

import numpy as np
import pandas as pd


def moving_average_signal(
    prices: pd.DataFrame,
    short_window: int = 20,
    long_window: int = 60,
) -> pd.Series:
    """Generate unshifted close-of-day target positions for the SMA strategy."""
    if (
        isinstance(short_window, bool)
        or isinstance(long_window, bool)
        or not isinstance(short_window, Integral)
        or not isinstance(long_window, Integral)
    ):
        raise TypeError("Windows must be integers.")
    if short_window <= 0 or long_window <= 0:
        raise ValueError("Windows must be positive integers.")
    if short_window >= long_window:
        raise ValueError("short_window must be smaller than long_window.")
    if "close" not in prices.columns:
        raise ValueError("prices must include a close column.")

    close = pd.to_numeric(prices["close"], errors="raise").astype(float)
    if not np.isfinite(close.to_numpy()).all():
        raise ValueError("close prices must be finite.")
    short_sma = close.rolling(short_window, min_periods=short_window).mean()
    long_sma = close.rolling(long_window, min_periods=long_window).mean()
    target = (short_sma > long_sma).astype(float)
    target.loc[long_sma.isna()] = 0.0
    return target.rename("target_position")
