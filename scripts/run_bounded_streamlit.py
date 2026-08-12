from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

CREATE_NEW_PROCESS_GROUP = 0x00000200


def _write_state(path: Path, **values: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, sort_keys=True), encoding="utf-8")


def _wait_for_http_200(url: str, process: subprocess.Popen[bytes], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Streamlit exited with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"Streamlit did not return HTTP 200 within {timeout:.0f} seconds.")


def _stop_process(process: subprocess.Popen[bytes], timeout: float = 5.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T"],
        shell=False,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
    )
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def _service_command(args: argparse.Namespace) -> list[str]:
    return [
        str(args.python),
        "-m",
        "streamlit",
        "run",
        str(args.app),
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]


def run_supervisor(args: argparse.Namespace) -> int:
    health_url = f"http://127.0.0.1:{args.port}/_stcore/health"
    app_url = f"http://127.0.0.1:{args.port}/"
    process: subprocess.Popen[bytes] | None = None
    args.ready_file.unlink(missing_ok=True)
    args.stop_file.unlink(missing_ok=True)
    args.stdout_log.parent.mkdir(parents=True, exist_ok=True)
    args.stderr_log.parent.mkdir(parents=True, exist_ok=True)
    with args.stdout_log.open("wb") as stdout, args.stderr_log.open("wb") as stderr:
        try:
            process = subprocess.Popen(
                _service_command(args),
                cwd=args.cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                close_fds=True,
                creationflags=CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            _wait_for_http_200(health_url, process, args.health_timeout)
            _write_state(
                args.ready_file,
                status="ready",
                supervisor_pid=os.getpid(),
                service_pid=process.pid,
                url=app_url,
            )
            deadline = time.monotonic() + args.max_seconds
            while time.monotonic() < deadline:
                if args.stop_file.exists() or process.poll() is not None:
                    break
                time.sleep(0.25)
            return 0
        except Exception as error:
            _write_state(
                args.ready_file,
                status="error",
                supervisor_pid=os.getpid(),
                service_pid=process.pid if process is not None else None,
                error=f"{error.__class__.__name__}: {error}",
            )
            return 1
        finally:
            if process is not None:
                _stop_process(process)
            args.stop_file.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--stdout-log", type=Path, required=True)
    parser.add_argument("--stderr-log", type=Path, required=True)
    parser.add_argument("--health-timeout", type=float, default=60.0)
    parser.add_argument("--max-seconds", type=float, default=300.0)
    args = parser.parse_args(argv)
    if args.health_timeout <= 0 or args.health_timeout > 60:
        parser.error("--health-timeout must be in (0, 60].")
    if args.max_seconds <= 0 or args.max_seconds > 300:
        parser.error("--max-seconds must be in (0, 300].")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_supervisor(args)


if __name__ == "__main__":
    raise SystemExit(main())
