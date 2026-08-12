from __future__ import annotations

import csv
import json
import re
import runpy
import tomllib
import unittest
from importlib.metadata import distributions, version
from pathlib import Path

from quant_lab import __version__

ROOT = Path(__file__).resolve().parents[1]
SPY_EXAMPLE = ROOT / "examples" / "spy-sma-20-60"
HK_EXAMPLE = ROOT / "examples" / "hk-sma-fixed"
NOTICE_GENERATOR = ROOT / "packaging" / "windows" / "generate_third_party_notices.py"
MAIN_SCREENSHOT = ROOT / "docs" / "images" / "quantlab-main.png"
RELEASE_NOTES = ROOT / "RELEASE-NOTES-v0.2.1.md"
PROJECT_STATUS = ROOT / "docs" / "PROJECT_STATUS.md"

EXPECTED_SPY_RUN_ID = "f74140da8472ee71"
EXPECTED_SPY_SHA256 = "ed981728b13a8092c5729b2cef165cb7e43c51b9dc3b108deed4082bd37c9811"
EXPECTED_SPY_VERSION = "0.1.0"
EXPECTED_HK_RUN_ID = "ed34a165606e87cf"
EXPECTED_HK_SHA256 = "6e6c98c856e19db59e4bfc4087278f232f6be3acb5d6c998153d0b07e7ea7276"


class RepositoryReleaseTests(unittest.TestCase):
    def test_version_has_one_python_source_and_matches_release_metadata(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(__version__, "0.2.1")
        self.assertEqual(
            pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"],
            "quant_lab.__about__.__version__",
        )
        self.assertNotIn("authors", pyproject["project"])
        self.assertEqual(version("quantlab-stock-etf-backtester"), __version__)

        windows_template = (ROOT / "packaging" / "windows" / "README-WINDOWS.txt").read_text(
            encoding="utf-8"
        )
        build_script = (ROOT / "packaging" / "windows" / "build_release.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("v{{VERSION}}", windows_template)
        self.assertIn('.Replace("{{VERSION}}", $Version)', build_script)
        self.assertIn('Join-Path $ProjectRoot "RELEASE-NOTES-v$Version.md"', build_script)

    def test_removed_legacy_entry_files_do_not_exist(self) -> None:
        removed_paths = (
            "src/quant_lab/daily_signal.py",
            "src/quant_lab/demo.py",
            "src/quant_lab/risk.py",
            "desktop_launcher.py",
            "QuantLab.spec",
            "START_QUANTLAB.bat",
            "run_app.bat",
            "build_exe.bat",
            "PRACTICAL_PLAYBOOK.md",
        )
        self.assertEqual([path for path in removed_paths if (ROOT / path).exists()], [])
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for value in ("/exports/", "/reports/", "/data/"):
            self.assertIn(value, ignore)
        self.assertTrue((ROOT / "frontend/src/features/exports/ExportPanel.tsx").is_file())
        self.assertTrue((ROOT / "frontend/src/features/exports/ExportPanel.test.tsx").is_file())

    def test_readme_relative_links_resolve(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        targets = re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", readme)
        missing: list[str] = []
        for target in targets:
            path_text = target.split("#", 1)[0]
            if not path_text or "://" in path_text or path_text.startswith("#"):
                continue
            if not (ROOT / path_text).exists():
                missing.append(target)
        self.assertEqual(missing, [])

    def test_readme_is_a_concise_public_project_homepage(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        for value in (
            "可信、可复现的港股日线回测与研究工具",
            "## Why QuantLab?",
            "## Key Features",
            "## Backtest Assumptions",
            "## Testing",
            "## Example",
            "## Limitations",
            "## Disclaimer",
            "docs/images/quantlab-main.png",
        ):
            self.assertIn(value, readme)
        self.assertNotIn("Streamlit 历史界面", readme)
        self.assertNotIn("coming soon", readme.lower())
        self.assertNotIn("production trading system", readme.lower())

    def test_readme_screenshot_is_current_1600_by_1000_png(self) -> None:
        image = MAIN_SCREENSHOT.read_bytes()

        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(image), 50_000)
        self.assertEqual(int.from_bytes(image[16:20], "big"), 1600)
        self.assertEqual(int.from_bytes(image[20:24], "big"), 1000)

    def test_legacy_spy_example_keeps_its_fixed_identity(self) -> None:
        manifest = json.loads((SPY_EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
        html = (SPY_EXAMPLE / "report.html").read_text(encoding="utf-8")
        with (SPY_EXAMPLE / "trades.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(manifest["run_id"], EXPECTED_SPY_RUN_ID)
        self.assertEqual(manifest["data_sha256"], EXPECTED_SPY_SHA256)
        self.assertEqual(manifest["software_version"], EXPECTED_SPY_VERSION)
        self.assertEqual(manifest["strategy_trade_count"], len(rows))
        self.assertIn(EXPECTED_SPY_RUN_ID, html)
        self.assertIn(EXPECTED_SPY_SHA256, html)
        self.assertEqual({row["run_id"] for row in rows}, {EXPECTED_SPY_RUN_ID})

    def test_fixed_hk_example_outputs_share_one_identity(self) -> None:
        manifest = json.loads((HK_EXAMPLE / "manifest.json").read_text(encoding="utf-8"))
        html = (HK_EXAMPLE / "report.html").read_text(encoding="utf-8")
        with (HK_EXAMPLE / "trades.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(manifest["run_id"], EXPECTED_HK_RUN_ID)
        self.assertEqual(manifest["market_data"]["data_sha256"], EXPECTED_HK_SHA256)
        self.assertEqual(manifest["strategy"]["name"], "SMA 双均线趋势")
        self.assertEqual(manifest["trade_count"], len(rows))
        self.assertEqual({row["run_id"] for row in rows}, {EXPECTED_HK_RUN_ID})
        self.assertIn(EXPECTED_HK_RUN_ID, html)
        self.assertIn(EXPECTED_HK_SHA256, html)
        self.assertIn("0700.HK 港股日线回测", html)

    def test_examples_are_self_contained_and_path_clean(self) -> None:
        for example in (SPY_EXAMPLE, HK_EXAMPLE):
            html = (example / "report.html").read_text(encoding="utf-8")
            combined = "\n".join(
                path.read_text(encoding="utf-8-sig")
                for path in (
                    example / "report.html",
                    example / "trades.csv",
                    example / "manifest.json",
                    example / "README.md",
                )
            )
            self.assertNotIn("http://", html.lower())
            self.assertNotIn("https://", html.lower())
            self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", combined))
            self.assertNotIn("file://", combined.lower())

    def test_readme_distinguishes_current_release_from_legacy_example(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("QuantLab-v0.2.1-windows-x64.zip", readme)
        self.assertIn("fixed at QuantLab v0.1.0", readme)
        self.assertIn("fixed Hong Kong example", readme)

    def test_changelog_records_golden_scope_without_core_changes(self) -> None:
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        self.assertIn("## 0.2.1", changelog)
        self.assertIn("G01-G13 and HK01-HK15", changelog)
        self.assertIn("## 0.1.1", changelog)
        self.assertIn("G01-G13 golden-test results remain unchanged", changelog)
        self.assertIn("does not change backtest execution", changelog)

    def test_third_party_notice_generator_covers_direct_dependencies_without_paths(self) -> None:
        render_notices = runpy.run_path(str(NOTICE_GENERATOR))["render_third_party_notices"]
        notices = render_notices(
            distributions(),
            excluded_names=frozenset({"quantlab-stock-etf-backtester"}),
        )

        for package_name in ("altair", "numpy", "pandas", "streamlit", "yfinance"):
            self.assertIn(f"## {package_name} ", notices.lower())
        self.assertNotIn("quantlab-stock-etf-backtester", notices.lower())
        self.assertIsNone(re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", notices))

    def test_ci_is_offline_locked_and_covers_supported_runtimes(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn('python-version: ["3.11", "3.12"]', workflow)
        self.assertIn('QUANTLAB_OFFLINE: "1"', workflow)
        self.assertIn("--require-hashes -r requirements.lock", workflow)
        self.assertIn("coverage report --fail-under=85", workflow)
        self.assertIn("frontend-quality-gate", workflow)
        self.assertIn("fixed-fixture-e2e", workflow)
        self.assertIn("pnpm --dir frontend build", workflow)
        self.assertNotIn("docker build", workflow)
        self.assertNotIn("schedule:", workflow)

    def test_release_workflow_supports_tag_push_and_existing_tag_dispatch(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        # Future tags publish automatically, while workflow_dispatch can safely
        # recover a release for an annotated tag that already exists.
        self.assertIn('      - "v*"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertRegex(
            workflow,
            r"workflow_dispatch:\s+inputs:\s+release_tag:[\s\S]+?required: true",
        )
        self.assertIn(
            "RELEASE_TAG: ${{ github.event_name == 'workflow_dispatch' "
            "&& inputs.release_tag || github.ref_name }}",
            workflow,
        )
        self.assertNotIn("pull_request:", workflow)

        # The Windows checkout must preserve LF and build the selected tag,
        # never the dispatch branch. The source guard requires an annotated tag,
        # an exact tag/HEAD match, and a clean checkout.
        self.assertLess(
            workflow.index("git config --global core.autocrlf false"),
            workflow.index("uses: actions/checkout@v4"),
        )
        self.assertLess(
            workflow.index("git config --global core.eol lf"),
            workflow.index("uses: actions/checkout@v4"),
        )
        self.assertIn("ref: ${{ env.RELEASE_TAG }}", workflow)
        self.assertIn("git cat-file -t $tagRef", workflow)
        self.assertIn('$tagObjectType -ne "tag"', workflow)
        self.assertIn('git rev-parse "$tagRef^{commit}"', workflow)
        self.assertIn("git status --short", workflow)

        # Version identity, release notes, and the GitHub Release all bind to
        # the same resolved tag for both automatic and recovery runs.
        self.assertIn('if ("v$version" -ne $env:RELEASE_TAG)', workflow)
        self.assertIn('"RELEASE-NOTES-$($env:RELEASE_TAG).md"', workflow)
        self.assertIn("body_path: RELEASE-NOTES-${{ env.RELEASE_TAG }}.md", workflow)
        self.assertIn("tag_name: ${{ env.RELEASE_TAG }}", workflow)
        self.assertIn("draft: false", workflow)
        self.assertIn("prerelease: false", workflow)

        # Recovery retains every production release quality gate and artifact.
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn('QUANTLAB_OFFLINE: "1"', workflow)
        self.assertIn("--require-hashes -r requirements.lock", workflow)
        self.assertIn("python -m ruff check .", workflow)
        self.assertIn("python -m ruff format --check .", workflow)
        self.assertIn("pnpm --dir frontend format:check", workflow)
        self.assertIn("pnpm --dir frontend lint", workflow)
        self.assertIn("pnpm --dir frontend typecheck", workflow)
        self.assertIn("pnpm --dir frontend test", workflow)
        self.assertIn("pnpm --dir frontend build", workflow)
        self.assertIn("coverage run -m unittest discover -s tests", workflow)
        self.assertIn("coverage report --fail-under=85", workflow)
        self.assertIn("build_release.ps1", workflow)
        self.assertIn("release/QuantLab-v*-windows-x64.zip", workflow)
        self.assertIn("release/SHA256SUMS.txt", workflow)
        self.assertIn("timeout-minutes: 30", workflow)
        self.assertRegex(workflow, r"build-windows-release:[\s\S]+?permissions:\s+contents: write")

    def test_public_project_templates_are_scope_aware(self) -> None:
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        bug = (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
        feature = (ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").read_text(
            encoding="utf-8"
        )
        pull_request = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")

        self.assertIn("QUANTLAB_OFFLINE", contributing)
        self.assertIn("feature-frozen", contributing)
        self.assertIn("Private Vulnerability Reporting", security)
        self.assertIn("no brokerage connection", security)
        self.assertIn("Redacted logs", bug)
        self.assertIn("does not guarantee profit", feature)
        self.assertIn("live trading", feature)
        self.assertIn("G01-G13", pull_request)

    def test_release_guide_describes_formal_history_free_release(self) -> None:
        guide = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")

        self.assertIn("History-Free Public Export", guide)
        self.assertIn("prepare_public_repository.py", guide)
        self.assertIn("provided public author name", guide)
        self.assertIn("QuantLab-v0.2.1-windows-x64.zip", guide)
        self.assertIn("run_windows_smoke_watchdog.ps1", guide)
        self.assertIn("RELEASE-NOTES-v0.2.1.md", guide)
        self.assertNotIn("v0.1.1-pre-publication-test", guide)

    def test_release_notes_and_project_status_are_publication_ready(self) -> None:
        notes = RELEASE_NOTES.read_text(encoding="utf-8")
        status = PROJECT_STATUS.read_text(encoding="utf-8")

        for value in (
            "# QuantLab v0.2.1",
            "## Highlights",
            "## Known Limitations",
            "## Installation",
            "QuantLab-v0.2.1-windows-x64.zip",
        ):
            self.assertIn(value, notes)
        self.assertIn("feature-frozen", status)
        self.assertEqual(status.count("- "), 2)
        self.assertNotIn("AI strategy", status)

    def test_public_metadata_has_no_quantlab_identity_placeholder(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "pyproject.toml",
                ROOT / "README.md",
                ROOT / "CONTRIBUTING.md",
                ROOT / "SECURITY.md",
                RELEASE_NOTES,
            )
        )
        self.assertNotIn("".join(("QuantLab ", "Maintainer")), combined)
        self.assertNotIn("".join(("quantlab", "@example.invalid")), combined)


if __name__ == "__main__":
    unittest.main()
