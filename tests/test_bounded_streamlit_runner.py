from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "run_bounded_streamlit.py"
SPEC = importlib.util.spec_from_file_location("quantlab_bounded_streamlit_runner", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load bounded Streamlit runner.")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def valid_arguments() -> list[str]:
    return [
        "--python",
        "python.exe",
        "--app",
        "app.py",
        "--cwd",
        ".",
        "--port",
        "3004",
        "--ready-file",
        "ready.json",
        "--stop-file",
        "stop",
        "--stdout-log",
        "stdout.log",
        "--stderr-log",
        "stderr.log",
    ]


class BoundedStreamlitRunnerTests(unittest.TestCase):
    def test_service_command_is_an_argument_list_with_headless_server(self) -> None:
        args = RUNNER.parse_args(valid_arguments())

        command = RUNNER._service_command(args)

        self.assertEqual(command[0], "python.exe")
        self.assertIn("streamlit", command)
        self.assertIn("3004", command)
        self.assertIn("--server.headless", command)
        self.assertNotIn("shell=True", repr(command))

    def test_time_limits_reject_values_above_contract(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                RUNNER.parse_args(valid_arguments() + ["--health-timeout", "61"])
            with self.assertRaises(SystemExit):
                RUNNER.parse_args(valid_arguments() + ["--max-seconds", "301"])

    def test_forced_cleanup_targets_only_saved_pid_tree(self) -> None:
        process = Mock()
        process.pid = 4321
        process.poll.return_value = None
        process.wait.side_effect = [
            subprocess.TimeoutExpired(["python"], 5),
            None,
        ]

        with patch.object(RUNNER.subprocess, "run") as command_runner:
            RUNNER._stop_process(process)

        process.terminate.assert_called_once_with()
        command_runner.assert_called_once_with(
            ["taskkill", "/PID", "4321", "/T"],
            shell=False,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5.0,
        )
        self.assertNotIn("/IM", repr(command_runner.call_args))

    def test_runner_never_uses_global_process_names_or_start_process(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Start-Process", source)
        self.assertNotIn('"/IM"', source)
        self.assertNotIn("msedge.exe", source)
        self.assertNotIn("chrome.exe", source)
        self.assertNotIn("--detach", source)


if __name__ == "__main__":
    unittest.main()
