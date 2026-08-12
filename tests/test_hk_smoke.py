from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from quant_lab.application.hk_smoke import run_offline_hk_smoke


class HKOfflineSmokeTests(unittest.TestCase):
    def test_bundled_smoke_runs_the_hk_vertical_slice_without_network(self) -> None:
        with patch.dict(os.environ, {"QUANTLAB_OFFLINE": "1"}):
            result = run_offline_hk_smoke()

        self.assertEqual(result["symbol"]["normalized_symbol"], "0700.HK")
        self.assertEqual(result["benchmark"]["normalized_symbol"], "2800.HK")
        self.assertEqual(result["strategy_metrics"]["final_equity"], 12_000.0)
        self.assertEqual(result["trades"][0]["quantity"], 1_000)
        self.assertEqual(result["date_range"]["actual_start"], "2024-01-02")
        self.assertEqual(result["date_range"]["actual_end"], "2024-01-05")


if __name__ == "__main__":
    unittest.main()
