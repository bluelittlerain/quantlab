from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
CREATE_NEW_PROCESS_GROUP = 0x00000200
VIEWPORTS = ((1366, 768), (1920, 1080))


def find_edge_executable(environment: dict[str, str] | None = None) -> Path:
    values = os.environ if environment is None else environment
    roots = (
        values.get("ProgramFiles(x86)"),
        values.get("ProgramFiles"),
        values.get("LOCALAPPDATA"),
    )
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Microsoft Edge was not found in a supported Windows location.")


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_http(url: str, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"HTTP 200 was not available before the deadline: {url}")


def _wait_for_port_release(port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(0.25)
            if client.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.2)
    return False


def terminate_process_tree(process: subprocess.Popen[bytes], timeout: float = 8.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            shell=False,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Process tree rooted at PID {process.pid} did not stop.") from error


@dataclass
class CdpClient:
    socket: Any
    deadline: float
    next_id: int = 1

    def call(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if time.monotonic() >= self.deadline:
            raise TimeoutError(f"CDP deadline exceeded before {method}.")
        request_id = self.next_id
        self.next_id += 1
        payload: dict[str, object] = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        if session_id is not None:
            payload["sessionId"] = session_id
        self.socket.send(json.dumps(payload, ensure_ascii=False))
        while time.monotonic() < self.deadline:
            remaining = max(0.1, min(5.0, self.deadline - time.monotonic()))
            message = json.loads(self.socket.recv(timeout=remaining))
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method} failed: {message['error']}")
            return message.get("result", {})
        raise TimeoutError(f"CDP response deadline exceeded for {method}.")


def _evaluate(client: CdpClient, session_id: str, expression: str) -> Any:
    response = client.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
        },
        session_id=session_id,
    )
    if response.get("exceptionDetails"):
        raise RuntimeError(f"Browser evaluation failed: {response['exceptionDetails']}")
    return response["result"].get("value")


def _wait_for_expression(
    client: CdpClient,
    session_id: str,
    expression: str,
    *,
    timeout: float,
) -> Any:
    deadline = min(client.deadline, time.monotonic() + timeout)
    while time.monotonic() < deadline:
        value = _evaluate(client, session_id, expression)
        if value:
            return value
        time.sleep(0.1)
    raise TimeoutError(f"Browser condition was not satisfied: {expression[:120]}")


def _element_rect(
    client: CdpClient,
    session_id: str,
    selector: str,
    *,
    text: str | None = None,
) -> dict[str, float]:
    selector_json = json.dumps(selector)
    text_json = json.dumps(text, ensure_ascii=False)
    expression = f"""
    (() => {{
      const nodes = Array.from(document.querySelectorAll({selector_json}));
      const element = {f"nodes.find(node => node.innerText.trim() === {text_json})" if text else "nodes[0]"};
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return {{
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        centerX: rect.x + rect.width / 2,
        centerY: rect.y + rect.height / 2
      }};
    }})()
    """
    value = _evaluate(client, session_id, expression)
    if not value:
        raise LookupError(f"Element was not found: selector={selector!r}, text={text!r}")
    return value


def _mouse_move(client: CdpClient, session_id: str, x: float, y: float) -> None:
    client.call(
        "Input.dispatchMouseEvent",
        {"type": "mouseMoved", "x": x, "y": y},
        session_id=session_id,
    )


def _click_rect(client: CdpClient, session_id: str, rect: dict[str, float]) -> None:
    x = rect["centerX"]
    y = rect["centerY"]
    _mouse_move(client, session_id, x, y)
    client.call(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        session_id=session_id,
    )
    client.call(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        session_id=session_id,
    )


def _capture_screenshot(
    client: CdpClient,
    session_id: str,
    path: Path,
) -> None:
    payload = client.call(
        "Page.captureScreenshot",
        {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
        session_id=session_id,
    )
    path.write_bytes(base64.b64decode(payload["data"]))


def _parse_rgb(value: str) -> tuple[float, float, float]:
    start = value.find("(")
    end = value.find(")")
    if start < 0 or end < 0:
        raise ValueError(f"Unsupported computed color: {value!r}")
    channels = value[start + 1 : end].replace(",", " ").split()
    if len(channels) < 3:
        raise ValueError(f"Unsupported computed color: {value!r}")
    return tuple(float(channel) for channel in channels[:3])


def _relative_luminance(value: str) -> float:
    channels = []
    for channel in _parse_rgb(value):
        normalized = channel / 255.0
        channels.append(
            normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4
        )
    return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2])


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def validate_runtime_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot["viewportOverflow"] > 1:
        raise AssertionError(f"Horizontal viewport overflow: {snapshot['viewportOverflow']}px")
    disabled = snapshot["disabledButton"]
    if not disabled["disabled"]:
        raise AssertionError("The refresh form button was not disabled during the request.")
    if _parse_rgb(disabled["background"]) == (255.0, 255.0, 255.0):
        raise AssertionError("The disabled refresh button still uses a white background.")
    if contrast_ratio(disabled["color"], disabled["background"]) < 3.0:
        raise AssertionError("The disabled refresh button label contrast is below 3:1.")
    tooltip = snapshot["tooltip"]
    if tooltip["right"] > snapshot["viewportWidth"] + 0.5 or tooltip["x"] < -0.5:
        raise AssertionError("The tooltip exceeds the horizontal viewport.")
    if tooltip["bottom"] > snapshot["viewportHeight"] + 0.5 or tooltip["y"] < -0.5:
        raise AssertionError("The tooltip exceeds the vertical viewport.")
    if tooltip["width"] > 321:
        raise AssertionError(f"The tooltip is unexpectedly wide: {tooltip['width']}")
    if contrast_ratio(tooltip["color"], tooltip["background"]) < 4.5:
        raise AssertionError("The tooltip text contrast is below 4.5:1.")
    if any(not item["inside"] for item in snapshot["icons"]):
        raise AssertionError("At least one visible button SVG exceeds its parent button.")
    if snapshot["segments"]["activeBackground"] == snapshot["segments"]["normalBackground"]:
        raise AssertionError("Segmented-control active and normal backgrounds are identical.")
    if snapshot["segments"]["activeBorder"] == snapshot["segments"]["normalBorder"]:
        raise AssertionError("Segmented-control active and normal borders are identical.")
    if not snapshot["sidebarRestoreVisible"]:
        raise AssertionError("The native sidebar collapse or restore control is not visible.")


def _set_viewport(
    client: CdpClient,
    session_id: str,
    width: int,
    height: int,
) -> None:
    client.call(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
        },
        session_id=session_id,
    )
    time.sleep(0.35)


def _scroll_sidebar(client: CdpClient, session_id: str, position: str) -> None:
    position_json = json.dumps(position)
    _evaluate(
        client,
        session_id,
        f"""
        (() => {{
          const sidebar = document.querySelector('[data-testid="stSidebar"]');
          let node = sidebar;
          while (node && node.scrollHeight <= node.clientHeight) node = node.firstElementChild;
          if (!node) return false;
          node.scrollTop = {position_json} === 'bottom' ? node.scrollHeight : 0;
          return true;
        }})()
        """,
    )
    time.sleep(0.2)


def _screenshot_states(
    client: CdpClient,
    session_id: str,
    output_directory: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    prefix = f"{width}x{height}"
    _set_viewport(client, session_id, width, height)
    _evaluate(client, session_id, "window.scrollTo(0, 0)")

    _scroll_sidebar(client, session_id, "top")
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-sidebar.png")
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-result-navigation.png")

    number_input = _element_rect(
        client,
        session_id,
        '[data-testid="stNumberInput"]',
    )
    _evaluate(
        client,
        session_id,
        """
        (() => {
          const element = document.querySelector('[data-testid="stNumberInput"]');
          element.scrollIntoView({block: 'center', inline: 'nearest'});
          return true;
        })()
        """,
    )
    time.sleep(0.2)
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-number-input.png")

    _evaluate(client, session_id, "window.scrollTo(0, 0)")
    chart_button = _element_rect(client, session_id, 'button[role="radio"]', text="净值对比")
    _click_rect(client, session_id, chart_button)
    _wait_for_expression(
        client,
        session_id,
        "document.body.innerText.includes('图表内容')",
        timeout=10,
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-chart-segmented.png")

    help_button = _element_rect(
        client,
        session_id,
        'button[aria-label="Help for 显示完整分辨率"]',
    )
    _mouse_move(client, session_id, help_button["centerX"], help_button["centerY"])
    _wait_for_expression(
        client,
        session_id,
        "Boolean(document.querySelector('[data-testid=\"stTooltipContent\"]'))",
        timeout=3,
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-tooltip.png")
    tooltip_style = _evaluate(
        client,
        session_id,
        """
        (() => {
          const element = document.querySelector('[data-testid="stTooltipContent"]');
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return {
            background: style.backgroundColor,
            color: style.color,
            border: style.borderColor,
            opacity: style.opacity,
            overflow: style.overflow,
            maxWidth: style.maxWidth,
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            right: rect.right,
            bottom: rect.bottom
          };
        })()
        """,
    )
    _mouse_move(client, session_id, width - 10, 10)
    time.sleep(0.4)

    _scroll_sidebar(client, session_id, "bottom")
    refresh_button = _element_rect(
        client,
        session_id,
        "button",
        text="重新获取行情并运行",
    )
    _click_rect(client, session_id, refresh_button)
    disabled_style = _wait_for_expression(
        client,
        session_id,
        """
        (() => {
          const button = Array.from(document.querySelectorAll('button'))
            .find(item => item.innerText.trim() === '重新获取行情并运行');
          if (!button || !button.disabled) return null;
          const style = getComputedStyle(button);
          const rect = button.getBoundingClientRect();
          return {
            disabled: button.disabled,
            ariaDisabled: button.getAttribute('aria-disabled'),
            background: style.backgroundColor,
            color: style.color,
            border: style.borderColor,
            opacity: style.opacity,
            cursor: style.cursor,
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height
          };
        })()
        """,
        timeout=2,
    )
    _capture_screenshot(
        client,
        session_id,
        output_directory / f"{prefix}-disabled-refresh.png",
    )
    _wait_for_expression(
        client,
        session_id,
        """
        (() => {
          const button = Array.from(document.querySelectorAll('button'))
            .find(item => item.innerText.trim() === '重新获取行情并运行');
          return Boolean(button && !button.disabled && document.body.innerText.includes('结果导航'));
        })()
        """,
        timeout=15,
    )

    icon_state = _evaluate(
        client,
        session_id,
        """
        Array.from(document.querySelectorAll('button svg'))
          .filter(svg => svg.getBoundingClientRect().width > 0)
          .map(svg => {
            const button = svg.closest('button');
            const iconRect = svg.getBoundingClientRect();
            const buttonRect = button.getBoundingClientRect();
            const style = getComputedStyle(svg);
            return {
              aria: button.getAttribute('aria-label'),
              buttonTestId: button.getAttribute('data-testid'),
              inside:
                iconRect.x >= buttonRect.x - 0.5 &&
                iconRect.y >= buttonRect.y - 0.5 &&
                iconRect.right <= buttonRect.right + 0.5 &&
                iconRect.bottom <= buttonRect.bottom + 0.5,
              color: style.color,
              fill: style.fill,
              stroke: style.stroke,
              transform: style.transform
            };
          })
        """,
    )
    segment_state = _evaluate(
        client,
        session_id,
        """
        (() => {
          const group = Array.from(document.querySelectorAll('[data-testid="stButtonGroup"]'))
            .find(item => item.querySelector('[role="radiogroup"]')
              ?.getAttribute('aria-label') === '图表内容');
          const active = group.querySelector('button[aria-checked="true"]');
          const normal = group.querySelector('button[aria-checked="false"]');
          const activeStyle = getComputedStyle(active);
          const normalStyle = getComputedStyle(normal);
          return {
            activeAriaChecked: active.getAttribute('aria-checked'),
            normalAriaChecked: normal.getAttribute('aria-checked'),
            activeBackground: activeStyle.backgroundColor,
            normalBackground: normalStyle.backgroundColor,
            activeBorder: activeStyle.borderColor,
            normalBorder: normalStyle.borderColor,
            activeColor: activeStyle.color,
            normalColor: normalStyle.color
          };
        })()
        """,
    )
    viewport_state = _evaluate(
        client,
        session_id,
        """
        (() => {
          const collapse = document.querySelector(
            '[data-testid="stSidebarCollapseButton"],' +
            '[data-testid="stExpandSidebarButton"],' +
            '[data-testid="collapsedControl"]'
          );
          const style = collapse ? getComputedStyle(collapse) : null;
          const rect = collapse ? collapse.getBoundingClientRect() : null;
          return {
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            viewportOverflow: Math.max(
              0,
              document.documentElement.scrollWidth - window.innerWidth
            ),
            sidebarRestoreVisible: Boolean(
              collapse &&
              style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              Number(style.opacity) > 0 &&
              rect.width > 0 &&
              rect.height > 0
            )
          };
        })()
        """,
    )
    return {
        **viewport_state,
        "disabledButton": disabled_style,
        "tooltip": tooltip_style,
        "icons": icon_state,
        "segments": segment_state,
        "numberInputProbe": number_input,
    }


def run_acceptance(args: argparse.Namespace) -> int:
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.timeout
    streamlit_port = args.port or reserve_local_port()
    debug_port = reserve_local_port()
    service: subprocess.Popen[bytes] | None = None
    edge: subprocess.Popen[bytes] | None = None
    profile_directory: Path | None = None
    results: dict[str, object] = {}

    service_stdout = (output_directory / "streamlit-stdout.log").open("wb")
    service_stderr = (output_directory / "streamlit-stderr.log").open("wb")
    browser_stdout = (output_directory / "edge-stdout.log").open("wb")
    browser_stderr = (output_directory / "edge-stderr.log").open("wb")
    try:
        service = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "tests" / "browser_dark_theme_app.py"),
                "--server.address",
                "127.0.0.1",
                "--server.port",
                str(streamlit_port),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=service_stdout,
            stderr=service_stderr,
            shell=False,
            close_fds=True,
            creationflags=CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        _wait_for_http(
            f"http://127.0.0.1:{streamlit_port}/_stcore/health",
            min(deadline, time.monotonic() + 60),
        )
        edge_path = find_edge_executable()
        profile_directory = Path(tempfile.mkdtemp(prefix="quantlab-dark-theme-"))
        edge = subprocess.Popen(
            [
                str(edge_path),
                "--headless=new",
                "--disable-gpu",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={profile_directory}",
                "--window-size=1920,1080",
                "about:blank",
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=browser_stdout,
            stderr=browser_stderr,
            shell=False,
            close_fds=True,
            creationflags=CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        version_url = f"http://127.0.0.1:{debug_port}/json/version"
        _wait_for_http(version_url, min(deadline, time.monotonic() + 30))
        with urllib.request.urlopen(version_url, timeout=2) as response:
            browser_info = json.loads(response.read().decode("utf-8"))
        with connect(
            browser_info["webSocketDebuggerUrl"],
            open_timeout=5,
            close_timeout=5,
        ) as websocket:
            client = CdpClient(websocket, deadline)
            target = client.call("Target.createTarget", {"url": "about:blank"})
            attached = client.call(
                "Target.attachToTarget",
                {"targetId": target["targetId"], "flatten": True},
            )
            session_id = attached["sessionId"]
            client.call("Page.enable", session_id=session_id)
            client.call("Runtime.enable", session_id=session_id)
            _set_viewport(client, session_id, *VIEWPORTS[0])
            client.call(
                "Page.navigate",
                {"url": f"http://127.0.0.1:{streamlit_port}/"},
                session_id=session_id,
            )
            _wait_for_expression(
                client,
                session_id,
                "document.body.innerText.includes('运行回测')",
                timeout=20,
            )
            theme_toggle = _element_rect(
                client,
                session_id,
                '[data-testid="stCheckbox"] label',
            )
            _click_rect(client, session_id, theme_toggle)
            _wait_for_expression(
                client,
                session_id,
                """
                (() => {
                  const input = document.querySelector(
                    'input[role="switch"][aria-label="深色模式"]'
                  );
                  return Boolean(input?.checked);
                })()
                """,
                timeout=5,
            )
            run_button = _element_rect(client, session_id, "button", text="运行回测")
            _click_rect(client, session_id, run_button)
            _wait_for_expression(
                client,
                session_id,
                "document.body.innerText.includes('结果导航')",
                timeout=20,
            )
            for width, height in VIEWPORTS:
                snapshot = _screenshot_states(
                    client,
                    session_id,
                    output_directory,
                    width,
                    height,
                )
                validate_runtime_snapshot(snapshot)
                results[f"{width}x{height}"] = snapshot
            (output_directory / "acceptance-results.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return 0
    finally:
        if edge is not None:
            terminate_process_tree(edge)
        if service is not None:
            terminate_process_tree(service)
        service_stdout.close()
        service_stderr.close()
        browser_stdout.close()
        browser_stderr.close()
        if profile_directory is not None:
            shutil.rmtree(profile_directory, ignore_errors=True)
        if not _wait_for_port_release(streamlit_port, time.monotonic() + 20):
            raise RuntimeError(f"Streamlit port {streamlit_port} was not released.")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Dark-theme acceptance exceeded {args.timeout:.0f} seconds.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "artifacts" / "dark-theme-rendering" / "acceptance",
    )
    parser.add_argument("--port", type=int)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 300:
        parser.error("--timeout must be in (0, 300].")
    return args


def main(argv: list[str] | None = None) -> int:
    return run_acceptance(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
