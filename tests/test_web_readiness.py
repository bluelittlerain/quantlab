from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from hk_fixtures import FixedHKProvider

from quant_lab.api.app import create_app
from quant_lab.application.service import BacktestApplicationService
from quant_lab.config import DeploymentMode, RuntimeConfig
from quant_lab.storage.repositories import QuantLabRepository
from quant_lab.storage.sqlite import SQLiteRepository

ROOT = Path(__file__).resolve().parents[1]


class WebReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = SQLiteRepository(self.root / "quantlab.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def runtime(self, *, cors_origins: tuple[str, ...] = ()) -> RuntimeConfig:
        return RuntimeConfig(
            mode=DeploymentMode.WEB,
            host="0.0.0.0",
            port=8000,
            data_directory=self.root,
            cors_origins=cors_origins,
        )

    def test_repository_boundary_is_structurally_satisfied_by_sqlite(self) -> None:
        self.assertIsInstance(self.repository, QuantLabRepository)
        self.assertTrue(self.repository.check_ready())

    def test_liveness_and_readiness_do_not_call_the_market_provider(self) -> None:
        provider = FixedHKProvider()
        app = create_app(
            provider=provider,
            repository=self.repository,
            runtime_config=self.runtime(),
        )
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/health/live").json()["status"], "live")
            self.assertEqual(client.get("/api/health/ready").json()["database"], "ok")
        self.assertEqual(provider.calls, [])

    def test_api_constructs_one_deployment_neutral_application_service(self) -> None:
        app = create_app(
            provider=FixedHKProvider(),
            repository=self.repository,
            runtime_config=self.runtime(),
        )
        self.assertIsNone(app.state.application_service)
        payload = {
            "symbol": "0700.HK",
            "benchmark_symbol": "2800.HK",
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
            "short_window": 1,
            "long_window": 2,
            "initial_capital": 100000,
            "board_lot": {"lot_size": 100, "confirmed": True},
            "benchmark_board_lot": {"lot_size": 100, "confirmed": True},
            "costs": {},
            "benchmark_costs": {},
        }
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/backtests", json=payload).status_code, 200)
        self.assertIsInstance(app.state.application_service, BacktestApplicationService)
        self.assertIs(app.state.application_service.repository, self.repository)

    def test_cors_is_an_explicit_allowlist_with_credentials(self) -> None:
        app = create_app(
            provider=FixedHKProvider(),
            repository=self.repository,
            runtime_config=self.runtime(cors_origins=("https://quantlab.example",)),
        )
        with TestClient(app) as client:
            allowed = client.options(
                "/api/health",
                headers={
                    "Origin": "https://quantlab.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
            rejected = client.options(
                "/api/health",
                headers={
                    "Origin": "https://untrusted.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
        self.assertEqual(allowed.headers["access-control-allow-origin"], "https://quantlab.example")
        self.assertEqual(allowed.headers["access-control-allow-credentials"], "true")
        self.assertNotIn("access-control-allow-origin", rejected.headers)

    def test_wildcard_and_malformed_cors_origins_are_rejected(self) -> None:
        for origin in ("*", "quantlab.example", "https://quantlab.example/path"):
            with self.subTest(origin=origin), self.assertRaisesRegex(ValueError, "CORS"):
                self.runtime(cors_origins=(origin,))

    def test_static_frontend_uses_spa_fallback_and_cache_boundaries(self) -> None:
        frontend = self.root / "frontend"
        assets = frontend / "assets"
        assets.mkdir(parents=True)
        (frontend / "index.html").write_text("<main>QuantLab shell</main>", encoding="utf-8")
        (assets / "index-a1b2c3.js").write_text("console.log('ok')", encoding="utf-8")
        app = create_app(
            provider=FixedHKProvider(),
            repository=self.repository,
            runtime_config=self.runtime(),
            frontend_directory=frontend,
        )

        with TestClient(app) as client:
            root = client.get("/")
            route = client.get("/history/run-123")
            asset = client.get("/assets/index-a1b2c3.js")
            missing_asset = client.get("/assets/missing.js")
            missing_api = client.get("/api/does-not-exist")

        self.assertEqual(root.headers["cache-control"], "no-cache")
        self.assertIn("QuantLab shell", route.text)
        self.assertEqual(route.headers["cache-control"], "no-cache")
        self.assertEqual(asset.headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertEqual(missing_asset.status_code, 404)
        self.assertEqual(missing_api.status_code, 404)

    def test_container_and_ci_are_build_only_and_contain_no_secret(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.example.yml").read_text(encoding="utf-8")
        environment = (ROOT / ".env.example").read_text(encoding="utf-8")
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertGreaterEqual(dockerfile.count("FROM "), 2)
        self.assertIn("USER quantlab", dockerfile)
        self.assertIn("quantlab-data:/data", compose)
        self.assertIn("PROVIDER_API_KEY=", environment)
        self.assertNotRegex(environment, r"PROVIDER_API_KEY=\S+")
        self.assertNotIn("docker build", ci)
        self.assertNotIn("docker push", ci)


if __name__ == "__main__":
    unittest.main()
