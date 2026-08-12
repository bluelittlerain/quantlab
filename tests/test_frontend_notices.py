from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "packaging" / "windows" / "generate_frontend_notices.py"
SPEC = importlib.util.spec_from_file_location("quantlab_frontend_notices", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load the frontend notices generator.")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_package(root: Path, name: str, version: str, dependencies=None) -> None:
    root.mkdir(parents=True)
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "license": "MIT",
                "dependencies": dependencies or {},
            }
        ),
        encoding="utf-8",
    )
    (root / "LICENSE").write_text(f"License for {name}", encoding="utf-8")


class FrontendNoticesTests(unittest.TestCase):
    def test_only_reachable_production_dependencies_are_rendered_without_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            frontend = Path(temporary) / "frontend"
            node_modules = frontend / "node_modules"
            frontend.mkdir()
            (frontend / "package.json").write_text(
                json.dumps(
                    {
                        "dependencies": {"alpha": "1.0.0"},
                        "devDependencies": {"dev-only": "1.0.0"},
                    }
                ),
                encoding="utf-8",
            )
            write_package(node_modules / "alpha", "alpha", "1.0.0", {"beta": "2.0.0"})
            write_package(node_modules / "beta", "beta", "2.0.0")
            write_package(node_modules / "dev-only", "dev-only", "1.0.0")

            rendered = MODULE.render_frontend_notices(frontend)

        self.assertIn("## alpha 1.0.0", rendered)
        self.assertIn("## beta 2.0.0", rendered)
        self.assertNotIn("dev-only", rendered)
        self.assertNotIn(temporary, rendered)
        self.assertLess(rendered.index("## alpha"), rendered.index("## beta"))


if __name__ == "__main__":
    unittest.main()
