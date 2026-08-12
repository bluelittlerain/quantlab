from __future__ import annotations

import time
from datetime import date
from importlib import import_module

import numpy as np
import pandas as pd
import streamlit as st

from quant_lab import data


def fixed_spy_history(
    fetch_start_date: date,
    fetch_end_date: date,
) -> tuple[pd.DataFrame, str]:
    """Return deterministic raw provider rows while preserving the real data adapter."""
    time.sleep(3)
    dates = pd.bdate_range(
        start=fetch_start_date,
        end=fetch_end_date,
        tz="America/New_York",
        name="Date",
    )
    sequence = np.arange(len(dates), dtype=float)
    close = 100.0 + (sequence * 0.025) + (5.0 * np.sin(sequence / 23.0))
    open_ = close + (0.35 * np.sin(sequence / 11.0))
    high = np.maximum(open_, close) + 1.25
    low = np.minimum(open_, close) - 1.25
    return (
        pd.DataFrame(
            {
                "Open": open_,
                "High": high,
                "Low": low,
                "Close": close,
                "Adj Close": close,
                "Volume": np.full(len(dates), 1_000_000.0),
            },
            index=dates,
        ),
        "fixed-dark-theme-fixture",
    )


data.fetch_spy_raw_yfinance = fixed_spy_history

was_imported = bool(st.session_state.get("_dark_theme_fixture_imported", False))
streamlit_app = import_module("app.streamlit_app")
if was_imported:
    streamlit_app.render_app()
else:
    # The entry module renders once as an import side effect on the first script run.
    st.session_state["_dark_theme_fixture_imported"] = True
