from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from hk_fixtures import FixedHKProvider

from quant_lab.api.app import create_app
from quant_lab.api.security import SESSION_HEADER_NAME, LANPairingSession
from quant_lab.config import DeploymentMode, RuntimeConfig
from quant_lab.storage.sqlite import SQLiteRepository


class LANSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime = RuntimeConfig(
            mode=DeploymentMode.LAN,
            host="0.0.0.0",
            port=3000,
            data_directory=self.root,
            lan_url="http://192.168.1.25:3000/",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def app(self, session: LANPairingSession):
        return create_app(
            provider=FixedHKProvider(),
            repository=SQLiteRepository(self.root / "quantlab.db"),
            runtime_config=self.runtime,
            pairing_session=session,
        )

    def test_remote_client_must_pair_and_token_never_enters_response_body(self) -> None:
        session = LANPairingSession(
            code_factory=lambda: "123456",
            token_factory=lambda: "private-session-token",
        )
        with TestClient(self.app(session), client=("192.168.1.60", 50000)) as client:
            runtime = client.get("/api/runtime").json()
            self.assertFalse(runtime["authenticated"])
            self.assertTrue(runtime["pairing_required"])
            self.assertIsNone(runtime["pairing_code"])
            self.assertIsNone(runtime["lan_url"])

            rejected = client.get("/api/history")
            self.assertEqual(rejected.status_code, 401)
            self.assertEqual(rejected.json()["error"]["code"], "PAIRING_REQUIRED")
            self.assertEqual(rejected.json()["error"]["field"], "pairing_code")

            wrong = client.post("/api/session/pair", json={"code": "000000"})
            self.assertEqual(wrong.status_code, 401)
            paired = client.post("/api/session/pair", json={"code": "123456"})
            self.assertEqual(paired.status_code, 200)
            self.assertEqual(paired.json(), {"paired": True})
            self.assertNotIn("private-session-token", paired.text)
            self.assertIn("HttpOnly", paired.headers["set-cookie"])
            self.assertEqual(client.get("/api/history").status_code, 200)

    def test_localhost_is_trusted_and_can_display_pairing_material(self) -> None:
        session = LANPairingSession(code_factory=lambda: "654321")
        with TestClient(self.app(session), client=("127.0.0.1", 50000)) as client:
            runtime = client.get("/api/runtime").json()
            self.assertTrue(runtime["authenticated"])
            self.assertEqual(runtime["pairing_code"], "654321")
            self.assertEqual(runtime["lan_url"], "http://192.168.1.25:3000/")
            self.assertEqual(client.get("/api/history").status_code, 200)

    def test_header_token_is_supported_and_restart_invalidates_old_tokens(self) -> None:
        first = LANPairingSession(
            code_factory=lambda: "123456", token_factory=lambda: "first-token"
        )
        token = first.pair("123456")
        self.assertEqual(token, "first-token")
        with TestClient(self.app(first), client=("192.168.1.60", 50000)) as client:
            self.assertEqual(
                client.get("/api/history", headers={SESSION_HEADER_NAME: token}).status_code,
                200,
            )

        second = LANPairingSession(
            code_factory=lambda: "654321", token_factory=lambda: "second-token"
        )
        with TestClient(self.app(second), client=("192.168.1.60", 50000)) as client:
            self.assertEqual(
                client.get("/api/history", headers={SESSION_HEADER_NAME: token}).status_code,
                401,
            )

    def test_runtime_environment_is_explicit_and_rejects_invalid_values(self) -> None:
        config = RuntimeConfig.from_environment(
            {
                "QUANTLAB_MODE": "WEB",
                "QUANTLAB_HOST": "0.0.0.0",
                "QUANTLAB_PORT": "8080",
                "QUANTLAB_DATA_DIR": "/data",
                "QUANTLAB_CORS_ORIGINS": "https://quantlab.example, https://research.example",
            }
        )
        self.assertEqual(config.mode, DeploymentMode.WEB)
        self.assertEqual(config.port, 8080)
        self.assertEqual(
            config.cors_origins,
            ("https://quantlab.example", "https://research.example"),
        )
        with self.assertRaisesRegex(ValueError, "QUANTLAB_MODE"):
            RuntimeConfig.from_environment({"QUANTLAB_MODE": "PUBLIC"})


if __name__ == "__main__":
    unittest.main()
