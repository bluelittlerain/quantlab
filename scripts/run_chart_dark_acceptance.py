from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

try:
    from scripts.run_dark_theme_acceptance import (
        CREATE_NEW_PROCESS_GROUP,
        CdpClient,
        _capture_screenshot,
        _click_rect,
        _element_rect,
        _evaluate,
        _mouse_move,
        _set_viewport,
        _wait_for_expression,
        _wait_for_http,
        _wait_for_port_release,
        find_edge_executable,
        reserve_local_port,
        terminate_process_tree,
    )
except ModuleNotFoundError:  # Direct execution puts the scripts directory on sys.path.
    from run_dark_theme_acceptance import (
        CREATE_NEW_PROCESS_GROUP,
        CdpClient,
        _capture_screenshot,
        _click_rect,
        _element_rect,
        _evaluate,
        _mouse_move,
        _set_viewport,
        _wait_for_expression,
        _wait_for_http,
        _wait_for_port_release,
        find_edge_executable,
        reserve_local_port,
        terminate_process_tree,
    )
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = ((1366, 768), (1920, 1080))
BANNED_VISIBLE_TEXT = (
    "Show data",
    "Press Enter to submit form",
    "January",
    "Monday",
    " Mo ",
    " Tu ",
)


def find_chrome_executable(environment: dict[str, str] | None = None) -> Path:
    values = os.environ if environment is None else environment
    roots = (
        values.get("ProgramFiles"),
        values.get("ProgramFiles(x86)"),
        values.get("LOCALAPPDATA"),
    )
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Google Chrome was not found in a supported Windows location.")


def _visible_rect(
    client: CdpClient,
    session_id: str,
    selector: str,
    *,
    text: str | None = None,
) -> dict[str, float]:
    selector_json = json.dumps(selector)
    text_json = json.dumps(text, ensure_ascii=False)
    value = _evaluate(
        client,
        session_id,
        f"""
        (() => {{
          const nodes = Array.from(document.querySelectorAll({selector_json}));
          const element = nodes.find(node => {{
            const rect = node.getBoundingClientRect();
            const style = getComputedStyle(node);
            const textMatches = {"true" if text is None else f"node.innerText.trim() === {text_json}"};
            return textMatches && rect.width > 0 && rect.height > 0 &&
              style.display !== 'none' && style.visibility !== 'hidden';
          }});
          if (!element) return null;
          const rect = element.getBoundingClientRect();
          return {{
            x: rect.x, y: rect.y, width: rect.width, height: rect.height,
            centerX: rect.x + rect.width / 2,
            centerY: rect.y + rect.height / 2
          }};
        }})()
        """,
    )
    if not value:
        raise LookupError(f"Visible element was not found: {selector!r}, {text!r}")
    return value


def _set_text_input(client: CdpClient, session_id: str, label: str, value: str) -> None:
    label_json = json.dumps(label, ensure_ascii=False)
    value_json = json.dumps(value, ensure_ascii=False)
    updated = _evaluate(
        client,
        session_id,
        f"""
        (() => {{
          const input = Array.from(document.querySelectorAll('input')).find(
            item => item.getAttribute('aria-label') === {label_json}
          );
          if (!input) return false;
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype,
            'value'
          ).set;
          setter.call(input, {value_json});
          input.dispatchEvent(new Event('input', {{bubbles: true}}));
          input.dispatchEvent(new Event('change', {{bubbles: true}}));
          input.blur();
          return true;
        }})()
        """,
    )
    if not updated:
        raise LookupError(f"Text input was not found: {label}")


def _click_button(client: CdpClient, session_id: str, text: str) -> None:
    _click_rect(client, session_id, _visible_rect(client, session_id, "button", text=text))


def _set_dark_mode(client: CdpClient, session_id: str, enabled: bool) -> None:
    state = bool(
        _evaluate(
            client,
            session_id,
            'Boolean(document.querySelector(\'input[role="switch"][aria-label="深色模式"]\')?.checked)',
        )
    )
    if state == enabled:
        return
    toggle = _visible_rect(client, session_id, '[data-testid="stCheckbox"] label')
    _click_rect(client, session_id, toggle)
    expected = "true" if enabled else "false"
    _wait_for_expression(
        client,
        session_id,
        (
            "Boolean(document.querySelector("
            '\'input[role="switch"][aria-label="深色模式"]\')?.checked) === ' + expected
        ),
        timeout=8,
    )


def _collapse_sidebar(client: CdpClient, session_id: str) -> None:
    collapse = _visible_rect(
        client,
        session_id,
        '[data-testid="stSidebarCollapseButton"] button',
    )
    _click_rect(client, session_id, collapse)
    _wait_for_expression(
        client,
        session_id,
        """
        (() => {
          const button = document.querySelector(
            '[data-testid="stExpandSidebarButton"] button,' +
            '[data-testid="collapsedControl"] button'
          );
          if (!button) return false;
          const rect = button.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        })()
        """,
        timeout=8,
    )


def _expand_sidebar(client: CdpClient, session_id: str) -> None:
    expand = _visible_rect(
        client,
        session_id,
        ('[data-testid="stExpandSidebarButton"] button,[data-testid="collapsedControl"] button'),
    )
    _click_rect(client, session_id, expand)
    _wait_for_expression(
        client,
        session_id,
        """
        (() => {
          const sidebar = document.querySelector('[data-testid="stSidebar"]');
          const button = document.querySelector('[data-testid="stSidebarCollapseButton"] button');
          if (!sidebar || !button) return false;
          return sidebar.getBoundingClientRect().width > 100 &&
            button.getBoundingClientRect().width > 0;
        })()
        """,
        timeout=8,
    )


def _open_chart_tooltip(
    client: CdpClient,
    session_id: str,
) -> dict[str, Any]:
    chart = _element_rect(client, session_id, '[data-testid="stVegaLiteChart"]')
    left = chart["x"] + 40
    right = chart["x"] + chart["width"] - 20
    top = chart["y"] + 20
    bottom = chart["y"] + chart["height"] - 30
    for x_fraction in (0.08, 0.25, 0.5, 0.75, 0.92):
        x = left + ((right - left) * x_fraction)
        y = top
        while y <= bottom:
            _mouse_move(client, session_id, x, y)
            tooltip = _evaluate(
                client,
                session_id,
                """
                (() => {
                  const element = document.querySelector('#vg-tooltip-element.vg-tooltip');
                  if (!element || !element.innerText.trim()) return null;
                  const rect = element.getBoundingClientRect();
                  const style = getComputedStyle(element);
                  if (rect.width <= 0 || rect.height <= 0 || style.visibility === 'hidden') return null;
                  return true;
                })()
                """,
            )
            if tooltip:
                return _evaluate(
                    client,
                    session_id,
                    """
                    (() => {
                      const element = document.querySelector('#vg-tooltip-element.vg-tooltip');
                      const rect = element.getBoundingClientRect();
                      const style = getComputedStyle(element);
                      const rows = Array.from(element.querySelectorAll('table tr')).map(row =>
                        Array.from(row.querySelectorAll('td,th')).map(cell => cell.innerText.trim())
                      );
                      return {
                        text: element.innerText,
                        rows,
                        x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom,
                        width: rect.width, height: rect.height,
                        background: style.backgroundColor,
                        color: style.color
                      };
                    })()
                    """,
                )
            y += 5
    raise TimeoutError("A visible Vega tooltip could not be opened within the chart bounds.")


def _runtime_snapshot(
    client: CdpClient, session_id: str, tooltip: dict[str, Any]
) -> dict[str, Any]:
    snapshot = _evaluate(
        client,
        session_id,
        """
        (() => {
          const facts = document.querySelector('.ql-chart-domain');
          const toolbar = document.querySelector(
            '.st-key-phase1_chart_shell [data-testid="stElementToolbar"]'
          );
          const toolbarStyle = toolbar ? getComputedStyle(toolbar) : null;
          const toolbarRect = toolbar ? toolbar.getBoundingClientRect() : null;
          const iconSelectors = [
            '[data-testid="stNumberInputStepDown"] svg',
            '[data-testid="stNumberInputStepUp"] svg',
            '[data-testid="stTooltipIcon"] button svg',
            '[data-testid="stSidebarCollapseButton"] button svg',
            '[data-testid="stExpandSidebarButton"] button svg',
            '[data-testid="collapsedControl"] button svg'
          ];
          const icons = iconSelectors.flatMap(selector =>
            Array.from(document.querySelectorAll(selector)).map(icon => {
              const parent = icon.closest('button');
              const iconRect = icon.getBoundingClientRect();
              const parentRect = parent.getBoundingClientRect();
              return {
                selector,
                inside: iconRect.left >= parentRect.left - 0.5 &&
                  iconRect.top >= parentRect.top - 0.5 &&
                  iconRect.right <= parentRect.right + 0.5 &&
                  iconRect.bottom <= parentRect.bottom + 0.5,
                icon: {x: iconRect.x, y: iconRect.y, width: iconRect.width, height: iconRect.height},
                parent: {x: parentRect.x, y: parentRect.y, width: parentRect.width, height: parentRect.height}
              };
            })
          );
          const axisYears = Array.from(
            document.querySelectorAll('.st-key-phase1_chart_shell svg text')
          ).map(node => node.textContent.trim()).filter(value => /^\\d{4}$/.test(value));
          const bodyText = document.body.innerText;
          return {
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            viewportOverflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
            bannedVisibleText: bodyText,
            nativeToolbarVisible: Boolean(
              toolbar && toolbarStyle.display !== 'none' && toolbarStyle.visibility !== 'hidden' &&
              toolbarRect.width > 0 && toolbarRect.height > 0
            ),
            chartFacts: facts ? {
              startDate: facts.dataset.startDate,
              endDate: facts.dataset.endDate,
              startStrategy: Number(facts.dataset.startStrategy),
              endStrategy: Number(facts.dataset.endStrategy),
              startBenchmark: Number(facts.dataset.startBenchmark),
              endBenchmark: Number(facts.dataset.endBenchmark)
            } : null,
            axisYears,
            icons
          };
        })()
        """,
    )
    snapshot["tooltip"] = tooltip
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot["viewportOverflow"] > 1:
        raise AssertionError(f"Horizontal overflow: {snapshot['viewportOverflow']}px")
    if snapshot["nativeToolbarVisible"]:
        raise AssertionError("The native Streamlit chart toolbar is visible.")
    for text in BANNED_VISIBLE_TEXT:
        if text in snapshot["bannedVisibleText"]:
            raise AssertionError(f"Unexpected visible English control text: {text!r}")
    if not snapshot["icons"] or any(not item["inside"] for item in snapshot["icons"]):
        raise AssertionError("At least one tested icon exceeds its parent button bounds.")
    facts = snapshot["chartFacts"]
    if not facts:
        raise AssertionError("Chart endpoint facts are missing.")
    if facts["endDate"] > "2024-12-31":
        raise AssertionError(f"Chart domain extends beyond the fixture: {facts['endDate']}")
    if (
        min(
            facts["startStrategy"],
            facts["endStrategy"],
            facts["startBenchmark"],
            facts["endBenchmark"],
        )
        <= 100
    ):
        raise AssertionError("A chart equity endpoint is implausibly close to zero.")
    if snapshot["axisYears"]:
        end_year = int(facts["endDate"][:4])
        if max(int(value) for value in snapshot["axisYears"]) > end_year:
            raise AssertionError("The rendered x-axis contains a future year.")
    tooltip = snapshot["tooltip"]
    if tooltip["right"] > snapshot["viewportWidth"] + 0.5 or tooltip["x"] < -0.5:
        raise AssertionError("The Vega tooltip exceeds the horizontal viewport.")
    if tooltip["bottom"] > snapshot["viewportHeight"] + 0.5 or tooltip["y"] < -0.5:
        raise AssertionError("The Vega tooltip exceeds the vertical viewport.")
    if tooltip["width"] > 289:
        raise AssertionError(f"The Vega tooltip is too wide: {tooltip['width']}")
    rows = tooltip["rows"]
    if len(rows) != 3 or [row[0] for row in rows] != ["日期", "系列", "账户净值"]:
        raise AssertionError(f"Unexpected Vega tooltip row order: {rows!r}")


def _capture_viewport_states(
    client: CdpClient,
    session_id: str,
    output_directory: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    prefix = f"{width}x{height}"
    _set_viewport(client, session_id, width, height)
    _set_dark_mode(client, session_id, False)
    _evaluate(client, session_id, "window.scrollTo(0, 0)")
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-01-sidebar-expanded.png")

    number_input = _element_rect(client, session_id, '[data-testid="stNumberInput"]')
    _evaluate(
        client,
        session_id,
        "document.querySelector('[data-testid=\"stNumberInput\"]')?.scrollIntoView({block:'center'})",
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-04-number-input.png")

    _set_text_input(client, session_id, "开始日期", "2015/01/01")
    _wait_for_expression(
        client,
        session_id,
        "document.body.innerText.includes('请输入 YYYY-MM-DD 格式')",
        timeout=8,
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-05-date-validation.png")
    _set_text_input(client, session_id, "开始日期", "2015-01-01")
    _wait_for_expression(
        client,
        session_id,
        "!document.body.innerText.includes('请输入 YYYY-MM-DD 格式')",
        timeout=8,
    )

    for iteration in range(10):
        _collapse_sidebar(client, session_id)
        if iteration == 0:
            _capture_screenshot(
                client,
                session_id,
                output_directory / f"{prefix}-02-sidebar-collapsed.png",
            )
            _capture_screenshot(
                client,
                session_id,
                output_directory / f"{prefix}-03-sidebar-restore-entry.png",
            )
        _expand_sidebar(client, session_id)

    _evaluate(client, session_id, "window.scrollTo(0, 0)")
    _click_button(client, session_id, "净值对比")
    _wait_for_expression(
        client,
        session_id,
        "document.body.innerText.includes('交互图表')",
        timeout=10,
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-06-chart-controls.png")
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-07-interactive-chart.png")

    _click_button(client, session_id, "查看数据")
    _wait_for_expression(
        client,
        session_id,
        "Boolean(document.querySelector('[data-testid=\"stDataFrame\"]'))",
        timeout=10,
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-08-data-view.png")
    _click_button(client, session_id, "交互图")
    _wait_for_expression(
        client,
        session_id,
        "Boolean(document.querySelector('[data-testid=\"stVegaLiteChart\"]'))",
        timeout=10,
    )
    _click_button(client, session_id, "重置视图")
    _wait_for_expression(
        client,
        session_id,
        "Boolean(document.querySelector('[data-testid=\"stVegaLiteChart\"]'))",
        timeout=10,
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-09-reset-view.png")

    _capture_screenshot(client, session_id, output_directory / f"{prefix}-11-light-theme.png")
    _set_dark_mode(client, session_id, True)
    _wait_for_expression(
        client,
        session_id,
        "getComputedStyle(document.body).colorScheme.includes('dark')",
        timeout=8,
    )
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-12-dark-theme.png")
    tooltip = _open_chart_tooltip(client, session_id)
    _capture_screenshot(client, session_id, output_directory / f"{prefix}-10-tooltip.png")
    snapshot = _runtime_snapshot(client, session_id, tooltip)
    snapshot["numberInput"] = number_input
    validate_snapshot(snapshot)
    return snapshot


def run_acceptance(args: argparse.Namespace) -> int:
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.timeout
    streamlit_port = args.port or reserve_local_port()
    debug_port = reserve_local_port()
    service: subprocess.Popen[bytes] | None = None
    edge: subprocess.Popen[bytes] | None = None
    profile_directory: Path | None = None
    handles = [
        (output_directory / "streamlit-stdout.log").open("wb"),
        (output_directory / "streamlit-stderr.log").open("wb"),
        (output_directory / "edge-stdout.log").open("wb"),
        (output_directory / "edge-stderr.log").open("wb"),
    ]
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
            stdout=handles[0],
            stderr=handles[1],
            shell=False,
            close_fds=True,
            creationflags=CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        _wait_for_http(
            f"http://127.0.0.1:{streamlit_port}/_stcore/health",
            min(deadline, time.monotonic() + 60),
        )
        profile_directory = Path(tempfile.mkdtemp(prefix="quantlab-chart-dark-"))
        browser_executable = (
            find_chrome_executable() if args.browser == "chrome" else find_edge_executable()
        )
        edge = subprocess.Popen(
            [
                str(browser_executable),
                "--headless=new",
                "--disable-gpu",
                "--disable-features=Vulkan,DawnGraphite",
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
            stdout=handles[2],
            stderr=handles[3],
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
            _click_button(client, session_id, "运行回测")
            _wait_for_expression(
                client,
                session_id,
                "document.body.innerText.includes('结果导航')",
                timeout=30,
            )
            results = {
                f"{width}x{height}": _capture_viewport_states(
                    client,
                    session_id,
                    output_directory,
                    width,
                    height,
                )
                for width, height in VIEWPORTS
            }
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
        for handle in handles:
            handle.close()
        if profile_directory is not None:
            shutil.rmtree(profile_directory, ignore_errors=True)
        if not _wait_for_port_release(streamlit_port, time.monotonic() + 20):
            raise RuntimeError(f"Streamlit port {streamlit_port} was not released.")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Chart acceptance exceeded {args.timeout:.0f} seconds.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "artifacts" / "chart-dark-rendering" / "acceptance",
    )
    parser.add_argument("--port", type=int)
    parser.add_argument("--browser", choices=("edge", "chrome"), default="edge")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 300:
        parser.error("--timeout must be in (0, 300].")
    return args


def main(argv: list[str] | None = None) -> int:
    return run_acceptance(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
