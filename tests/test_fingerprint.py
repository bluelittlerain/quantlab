from __future__ import annotations

import math
import unittest

import pandas as pd
from fixtures import G13_DATA_SHA256
from test_data import g13_raw_frame

from quant_lab.data import standardize_adjusted_ohlcv
from quant_lab.fingerprint import (
    calculate_market_data_sha256,
    canonical_market_data_bytes,
)

G13_CANONICAL_BYTES = (
    b"date,open,high,low,close,volume\n"
    b"2024-12-16,50.0000000000,52.0000000000,49.0000000000,51.0000000000,1000.0000000000\n"
    b"2024-12-17,51.0000000000,53.0000000000,50.0000000000,52.0000000000,2000.0000000000\n"
)


class FingerprintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prices = standardize_adjusted_ohlcv(g13_raw_frame())

    def test_g13_canonical_bytes_and_sha256_match_fixed_literals(self) -> None:
        self.assertEqual(canonical_market_data_bytes(self.prices), G13_CANONICAL_BYTES)
        self.assertEqual(calculate_market_data_sha256(self.prices), G13_DATA_SHA256)

    def test_column_order_and_dataframe_index_do_not_change_hash(self) -> None:
        reordered = self.prices[["volume", "close", "date", "low", "open", "high"]].copy()
        reordered.index = pd.Index(["second-label", "first-label"], name="arbitrary")
        self.assertEqual(
            calculate_market_data_sha256(reordered),
            G13_DATA_SHA256,
        )

    def test_input_row_order_does_not_change_hash(self) -> None:
        reversed_prices = self.prices.iloc[::-1].copy()
        self.assertEqual(
            calculate_market_data_sha256(reversed_prices),
            G13_DATA_SHA256,
        )

    def test_changing_one_standardized_price_changes_hash(self) -> None:
        changed = self.prices.copy()
        changed.loc[0, "open"] = 50.0000000001
        self.assertNotEqual(
            calculate_market_data_sha256(changed),
            G13_DATA_SHA256,
        )

    def test_metadata_and_dataframe_memory_layout_do_not_enter_hash(self) -> None:
        copied = self.prices.copy(deep=True)
        copied.attrs["fetched_at_utc"] = "2099-01-01T00:00:00Z"
        copied.attrs["source"] = "not-part-of-the-fingerprint"
        self.assertEqual(calculate_market_data_sha256(copied), G13_DATA_SHA256)

    def test_nan_in_core_ohlcv_is_rejected(self) -> None:
        invalid = self.prices.copy()
        invalid.loc[0, "close"] = math.nan
        with self.assertRaisesRegex(
            ValueError,
            "field='close'.*date=2024-12-16.*must be finite",
        ):
            calculate_market_data_sha256(invalid)

    def test_duplicate_date_is_rejected(self) -> None:
        duplicate = pd.concat([self.prices, self.prices.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(
            ValueError,
            "field='date'.*date=2024-12-16.*actual=2 rows",
        ):
            calculate_market_data_sha256(duplicate)


if __name__ == "__main__":
    unittest.main()
