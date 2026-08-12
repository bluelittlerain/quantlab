from __future__ import annotations

import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from hk_fixtures import FixedHKProvider

from quant_lab.api.app import create_app
from quant_lab.storage.sqlite import SQLiteRepository


def request_payload() -> dict[str, object]:
    zero_costs = {
        "broker_commission_rate": 0.0,
        "broker_minimum_commission": 0.0,
        "stamp_duty_rate": 0.0,
        "trading_fee_rate": 0.0,
        "transaction_levy_rate": 0.0,
        "afrc_transaction_levy_rate": 0.0,
        "settlement_fee_rate": 0.0,
        "slippage_rate": 0.0,
    }
    return {
        "symbol": "700",
        "benchmark_symbol": "2800.HK",
        "start_date": "2024-01-02",
        "end_date": "2024-01-05",
        "short_window": 1,
        "long_window": 2,
        "initial_capital": 10_000.0,
        "board_lot": {"lot_size": 100, "confirmed": True},
        "benchmark_board_lot": {"lot_size": 100, "confirmed": True},
        "costs": zero_costs,
        "benchmark_costs": zero_costs,
    }


class HKAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        repository = SQLiteRepository(Path(self.temporary.name) / "quantlab.db")
        self.provider = FixedHKProvider()
        self.client = TestClient(create_app(provider=self.provider, repository=repository))

    def tearDown(self) -> None:
        self.client.close()
        self.temporary.cleanup()

    def test_health_and_openapi_are_typed(self) -> None:
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["market"], "HKEX")
        schema = self.client.get("/openapi.json").json()
        self.assertIn("BacktestResponseModel", schema["components"]["schemas"])
        self.assertIn("BacktestRequestModel", schema["components"]["schemas"])

    def test_react_assets_are_served_without_shadowing_the_api(self) -> None:
        frontend = Path(self.temporary.name) / "frontend"
        assets = frontend / "assets"
        assets.mkdir(parents=True)
        (frontend / "index.html").write_text(
            '<!doctype html><html lang="zh-CN"><body>QuantLab React</body></html>',
            encoding="utf-8",
        )
        (assets / "app.js").write_text("export const ready = true;", encoding="utf-8")
        repository = SQLiteRepository(Path(self.temporary.name) / "static.db")

        with TestClient(
            create_app(
                provider=self.provider,
                repository=repository,
                frontend_directory=frontend,
            )
        ) as client:
            self.assertIn("QuantLab React", client.get("/").text)
            self.assertIn("ready = true", client.get("/assets/app.js").text)
            self.assertEqual(client.get("/api/health").json()["market"], "HKEX")

    def test_incomplete_frontend_assets_are_rejected_at_startup(self) -> None:
        frontend = Path(self.temporary.name) / "incomplete-frontend"
        frontend.mkdir()
        with self.assertRaisesRegex(RuntimeError, "index.html"):
            create_app(
                provider=self.provider,
                repository=self.client.app.state.repository,
                frontend_directory=frontend,
            )

    def test_symbol_normalization_does_not_guess_board_lot(self) -> None:
        response = self.client.get("/api/symbols/700")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["symbol"]["normalized_symbol"], "0700.HK")
        self.assertIsNone(body["board_lot"])
        self.assertTrue(body["board_lot_requires_confirmation"])

    def test_successful_run_remembers_user_confirmed_board_lots(self) -> None:
        self.assertIsNone(self.client.get("/api/symbols/700").json()["board_lot"])
        response = self.client.post("/api/backtests", json=request_payload())
        self.assertEqual(response.status_code, 200, response.text)

        symbol = self.client.get("/api/symbols/700").json()
        benchmark = self.client.get("/api/symbols/2800").json()
        self.assertEqual(symbol["board_lot"]["lot_size"], 100)
        self.assertEqual(symbol["board_lot"]["source"], "USER")
        self.assertFalse(symbol["board_lot_requires_confirmation"])
        self.assertEqual(benchmark["board_lot"]["lot_size"], 100)

    def test_backtest_vertical_slice_persists_result(self) -> None:
        response = self.client.post("/api/backtests", json=request_payload())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["symbol"]["normalized_symbol"], "0700.HK")
        self.assertEqual(body["benchmark"]["normalized_symbol"], "2800.HK")
        self.assertEqual(body["date_range"]["actual_start"], "2024-01-02")
        self.assertEqual(body["date_range"]["actual_end"], "2024-01-05")
        self.assertEqual(body["strategy_metrics"]["final_equity"], 12_000.0)
        self.assertEqual(body["equity_series"][0]["strategy_equity"], 10_000.0)
        self.assertEqual(body["equity_series"][-1]["strategy_equity"], 12_000.0)
        self.assertEqual(body["trades"][0]["quantity"], 1_000)
        self.assertEqual(body["market_data"]["cache_status"], "LIVE")
        self.assertEqual(len(self.provider.calls), 2)

        stored = self.client.get(f"/api/backtests/{body['run_id']}")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json(), body)
        history = self.client.get("/api/history").json()
        self.assertEqual(history[0]["run_id"], body["run_id"])

    def test_force_refresh_and_exports_are_explicit(self) -> None:
        created = self.client.post("/api/backtests", json=request_payload()).json()
        self.assertEqual(len(self.provider.calls), 2)
        refreshed = self.client.post("/api/market-data/refresh", json=request_payload())
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(self.provider.calls[-2:], [("0700.HK", True), ("2800.HK", True)])

        run_id = created["run_id"]
        prepared = self.client.post(f"/api/exports/{run_id}/prepare")
        self.assertEqual(prepared.status_code, 200)
        self.assertEqual(prepared.json()["run_id"], run_id)
        self.assertGreater(prepared.json()["files"]["bundle.zip"], 0)
        report = self.client.get(f"/api/exports/{run_id}/report.html")
        trades = self.client.get(f"/api/exports/{run_id}/trades.csv")
        manifest = self.client.get(f"/api/exports/{run_id}/manifest.json")
        bundle = self.client.get(f"/api/exports/{run_id}/bundle.zip")
        self.assertIn(run_id, report.text)
        self.assertTrue(trades.content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(manifest.json()["run_id"], run_id)
        with zipfile.ZipFile(BytesIO(bundle.content)) as archive:
            self.assertEqual(archive.namelist(), ["report.html", "trades.csv", "manifest.json"])
            self.assertIn(run_id, archive.read("manifest.json").decode("utf-8"))

    def test_settings_and_preset_crud(self) -> None:
        settings = self.client.put("/api/settings", json={"theme": "DARK"})
        self.assertEqual(settings.json(), {"theme": "DARK"})
        created = self.client.post(
            "/api/presets",
            json={"name": "腾讯 SMA 20/60", "payload": {"symbol": "0700.HK"}},
        )
        self.assertEqual(created.status_code, 201)
        preset_id = created.json()["id"]
        self.assertEqual(len(self.client.get("/api/presets").json()), 1)
        updated = self.client.put(
            f"/api/presets/{preset_id}",
            json={"name": "腾讯趋势", "payload": {"symbol": "0700.HK"}},
        )
        self.assertTrue(updated.json()["updated"])
        self.assertTrue(self.client.delete(f"/api/presets/{preset_id}").json()["deleted"])

    def test_errors_are_structured_and_sanitized(self) -> None:
        invalid_symbol = self.client.get("/api/symbols/AAPL")
        self.assertEqual(invalid_symbol.status_code, 422)
        self.assertEqual(invalid_symbol.json()["error"]["code"], "INVALID_SYMBOL")
        missing = self.client.get("/api/backtests/not-found")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "RUN_NOT_FOUND")
        self.assertNotIn("Traceback", missing.text)
        self.assertNotIn("C:\\", missing.text)

    def test_validation_errors_identify_the_actionable_field(self) -> None:
        invalid_windows = request_payload()
        invalid_windows["short_window"] = 60
        invalid_windows["long_window"] = 20
        response = self.client.post("/api/backtests", json=invalid_windows)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "INVALID_SMA_WINDOWS")
        self.assertEqual(response.json()["error"]["field"], "long_window")
        self.assertIn("长均线", response.json()["error"]["message"])

        invalid_cost = request_payload()
        invalid_cost["costs"] = {**invalid_cost["costs"], "stamp_duty_rate": -0.01}
        response = self.client.post("/api/backtests", json=invalid_cost)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "INVALID_COST_RATE")
        self.assertEqual(response.json()["error"]["field"], "costs.stamp_duty_rate")
        self.assertNotIn("Traceback", response.text)

        insufficient = request_payload()
        insufficient["initial_capital"] = 1.0
        response = self.client.post("/api/backtests", json=insufficient)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "INSUFFICIENT_CAPITAL")
        self.assertEqual(response.json()["error"]["field"], "initial_capital")
        self.assertIn("一手", response.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
