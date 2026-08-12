from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from hk_fixtures import FixedHKProvider

from quant_lab.application.errors import QuantLabApplicationError
from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.market.hk.symbols import normalize_hk_symbol
from quant_lab.providers.cache import CachedMarketDataProvider


class HKMarketDataCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.provider = FixedHKProvider()
        self.cache = CachedMarketDataProvider(
            self.provider, Path(self.temporary.name) / "market-data"
        )
        self.symbol = normalize_hk_symbol("700")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(self, *, force_refresh: bool = False):
        return self.cache.get_daily_prices(
            self.symbol,
            date(2024, 1, 2),
            date(2024, 1, 5),
            2,
            force_refresh=force_refresh,
        )

    def test_second_request_reuses_valid_cache_without_provider_access(self) -> None:
        first = self.load()
        second = self.load()
        self.assertEqual(len(self.provider.calls), 1)
        self.assertTrue(self.cache.was_cache_hit(self.symbol))
        self.assertEqual(second.metadata.data_sha256, first.metadata.data_sha256)
        self.assertEqual(second.prices.to_dict("records"), first.prices.to_dict("records"))

    def test_force_refresh_bypasses_cache_and_replaces_it(self) -> None:
        self.load()
        self.load(force_refresh=True)
        self.assertEqual(self.provider.calls, [("0700.HK", False), ("0700.HK", True)])
        self.assertFalse(self.cache.was_cache_hit(self.symbol))

    def test_corrupt_cache_is_reported_instead_of_silently_deleted(self) -> None:
        self.load()
        metadata_path = next((Path(self.temporary.name) / "market-data").glob("*.json"))
        metadata_path.write_text("not-json", encoding="utf-8")
        with self.assertRaisesRegex(QuantLabApplicationError, "CACHE_ERROR"):
            self.load()

    def test_cache_float_parser_preserves_fingerprint_boundary_values(self) -> None:
        result = self.provider.results["0700.HK"]
        prices = result.prices.copy()
        prices.loc[0, "open"] = 287.46366903004366
        prices.loc[0, "high"] = 288.0
        prices.loc[0, "low"] = 280.0
        prices.loc[0, "close"] = 283.94512939453125
        self.provider.results["0700.HK"] = type(result)(
            prices=prices,
            metadata=type(result.metadata)(
                **{
                    **result.metadata.__dict__,
                    "data_sha256": calculate_market_data_sha256(prices),
                }
            ),
        )

        first = self.load()
        second = self.load()

        self.assertEqual(second.metadata.data_sha256, first.metadata.data_sha256)
        self.assertEqual(second.prices.loc[0, "open"], first.prices.loc[0, "open"])


if __name__ == "__main__":
    unittest.main()
