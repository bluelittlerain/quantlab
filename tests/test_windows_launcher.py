from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = ROOT / "packaging" / "windows" / "desktop_launcher.py"
BUILD_SCRIPT_PATH = ROOT / "packaging" / "windows" / "build_release.ps1"
SMOKE_WATCHDOG_PATH = ROOT / "scripts" / "run_windows_smoke_watchdog.ps1"
WINDOWS_README_PATH = ROOT / "packaging" / "windows" / "README-WINDOWS.txt"
APP_PATH = ROOT / "app" / "streamlit_app.py"
FRONTEND_DIST_PATH = ROOT / "frontend" / "dist"
EXAMPLE_DIRECTORY = ROOT / "examples" / "spy-sma-20-60"

SPEC = importlib.util.spec_from_file_location("quantlab_windows_launcher", LAUNCHER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load the Windows launcher module for tests.")
LAUNCHER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LAUNCHER
SPEC.loader.exec_module(LAUNCHER)

FAKE_ENVIRONMENT = {
    "ProgramFiles(x86)": "X:/Programs With Spaces (x86)",
    "ProgramFiles": "X:/Programs With Spaces",
    "LOCALAPPDATA": "X:/Test User/Local App Data",
}
EDGE_PATH = (
    Path(FAKE_ENVIRONMENT["ProgramFiles(x86)"])
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe"
)
CHROME_PATH = (
    Path(FAKE_ENVIRONMENT["ProgramFiles"]) / "Google" / "Chrome" / "Application" / "chrome.exe"
)
APP_DATA_ROOT = Path(FAKE_ENVIRONMENT["LOCALAPPDATA"]) / "QuantLab"
URL = "http://localhost:3000/"


def path_checker(*existing: Path):
    available = set(existing)
    return lambda candidate: candidate in available


def make_process(pid: int = 4100) -> MagicMock:
    process = MagicMock()
    process.pid = pid
    process.poll.return_value = None
    return process


def make_process_job(active_process_count: int = 1) -> MagicMock:
    process_job = MagicMock()
    process_job.active_process_count.return_value = active_process_count
    return process_job


def make_plan(kind=LAUNCHER.BrowserKind.EDGE) -> object:
    executable = EDGE_PATH if kind is LAUNCHER.BrowserKind.EDGE else CHROME_PATH
    profile = LAUNCHER.get_quantlab_browser_profile_dir(kind, APP_DATA_ROOT)
    browser = LAUNCHER.BrowserExecutable(kind=kind, path=executable)
    return LAUNCHER.BrowserLaunchPlan(
        browser=browser,
        url=URL,
        profile_directory=profile,
        command=LAUNCHER.build_browser_command(executable, URL, profile),
    )


class BrowserSelectionTests(unittest.TestCase):
    def test_edge_is_preferred_over_chrome(self) -> None:
        browser = LAUNCHER.find_supported_browser(
            FAKE_ENVIRONMENT,
            path_is_file=path_checker(EDGE_PATH, CHROME_PATH),
        )
        self.assertEqual(browser.kind, LAUNCHER.BrowserKind.EDGE)
        self.assertEqual(browser.path, EDGE_PATH)

    def test_chrome_is_selected_when_edge_is_unavailable(self) -> None:
        browser = LAUNCHER.find_supported_browser(
            FAKE_ENVIRONMENT,
            path_is_file=path_checker(CHROME_PATH),
        )
        self.assertEqual(browser.kind, LAUNCHER.BrowserKind.CHROME)
        self.assertEqual(browser.path, CHROME_PATH)

    def test_edge_command_contains_isolation_switches(self) -> None:
        plan = make_plan()
        self.assertIn(f"--app={URL}", plan.command)
        self.assertIn("--disable-extensions", plan.command)
        self.assertIn("--no-first-run", plan.command)
        self.assertIn("--no-default-browser-check", plan.command)
        self.assertIn(f"--user-data-dir={plan.profile_directory}", plan.command)

    def test_profiles_are_versioned_and_browser_specific(self) -> None:
        edge = LAUNCHER.get_quantlab_browser_profile_dir(LAUNCHER.BrowserKind.EDGE, APP_DATA_ROOT)
        chrome = LAUNCHER.get_quantlab_browser_profile_dir(
            LAUNCHER.BrowserKind.CHROME, APP_DATA_ROOT
        )
        self.assertEqual(edge, APP_DATA_ROOT / "browser-profile-v1" / "edge")
        self.assertEqual(chrome, APP_DATA_ROOT / "browser-profile-v1" / "chrome")
        self.assertNotEqual(edge, chrome)
        self.assertNotIn("Microsoft/Edge/User Data", edge.as_posix())
        self.assertNotIn("Google/Chrome/User Data", chrome.as_posix())

    def test_paths_with_spaces_remain_single_command_arguments(self) -> None:
        profile = APP_DATA_ROOT / "browser-profile-v1" / "edge"
        command = LAUNCHER.build_browser_command(EDGE_PATH, URL, profile)
        self.assertEqual(command[0], str(EDGE_PATH))
        self.assertEqual(command[-1], f"--user-data-dir={profile}")
        self.assertEqual(len(command), 6)

    def test_isolated_launch_uses_argument_list_and_shell_false(self) -> None:
        process = make_process()
        process_job = make_process_job()
        popen_factory = MagicMock(return_value=process)
        directory_maker = MagicMock()
        plan = make_plan()

        actual = LAUNCHER.launch_isolated_browser(
            plan,
            popen_factory=popen_factory,
            directory_maker=directory_maker,
            process_job_factory=MagicMock(return_value=process_job),
        )

        self.assertIs(actual.process, process)
        self.assertIs(actual.process_job, process_job)
        directory_maker.assert_called_once_with(plan.profile_directory)
        popen_factory.assert_called_once_with(list(plan.command), shell=False)
        process_job.assign.assert_called_once_with(process)

    def test_job_creation_failure_does_not_start_browser(self) -> None:
        popen_factory = MagicMock()
        with self.assertRaises(OSError):
            LAUNCHER.launch_isolated_browser(
                make_plan(),
                popen_factory=popen_factory,
                directory_maker=MagicMock(),
                process_job_factory=MagicMock(side_effect=OSError("job unavailable")),
            )
        popen_factory.assert_not_called()


class SingleInstanceTests(unittest.TestCase):
    def test_first_instance_holds_and_releases_named_mutex_once(self) -> None:
        kernel32 = MagicMock()
        kernel32.CreateMutexW.return_value = 1234
        guard = LAUNCHER.acquire_single_instance_guard(
            kernel32=kernel32,
            get_last_error=MagicMock(return_value=0),
            set_last_error=MagicMock(),
        )
        self.assertIsNotNone(guard)
        kernel32.CreateMutexW.assert_called_once_with(
            None,
            False,
            LAUNCHER.SINGLE_INSTANCE_MUTEX_NAME,
        )
        guard.close()
        guard.close()
        kernel32.CloseHandle.assert_called_once_with(1234)

    def test_second_instance_exits_without_starting_service_or_browser(self) -> None:
        message = MagicMock()
        with (
            patch.object(LAUNCHER.multiprocessing, "freeze_support"),
            patch.object(LAUNCHER, "configure_logging"),
            patch.object(LAUNCHER, "acquire_single_instance_guard", return_value=None),
            patch.object(LAUNCHER, "show_second_instance_message", message),
            patch.object(LAUNCHER, "start_server") as start_server,
            patch.object(LAUNCHER, "open_quantlab_browser") as open_browser,
        ):
            LAUNCHER.main()
        message.assert_called_once_with()
        start_server.assert_not_called()
        open_browser.assert_not_called()

    def test_existing_mutex_is_closed_before_second_instance_returns(self) -> None:
        kernel32 = MagicMock()
        kernel32.CreateMutexW.return_value = 5678
        guard = LAUNCHER.acquire_single_instance_guard(
            kernel32=kernel32,
            get_last_error=MagicMock(return_value=LAUNCHER._ERROR_ALREADY_EXISTS),
            set_last_error=MagicMock(),
        )
        self.assertIsNone(guard)
        kernel32.CloseHandle.assert_called_once_with(5678)

    def test_second_instance_message_is_a_one_shot_system_message(self) -> None:
        show_message = MagicMock()
        LAUNCHER.show_second_instance_message(show_message)
        show_message.assert_called_once_with(
            LAUNCHER.APP_NAME,
            LAUNCHER.SECOND_INSTANCE_MESSAGE,
        )


class BrowserFallbackTests(unittest.TestCase):
    def test_edge_failure_tries_chrome_once(self) -> None:
        chrome_process = make_process(4200)
        popen_factory = MagicMock(side_effect=[OSError("edge failed"), chrome_process])
        default_open = MagicMock()

        result = LAUNCHER.open_quantlab_browser(
            URL,
            app_data_root=APP_DATA_ROOT,
            environment=FAKE_ENVIRONMENT,
            path_is_file=path_checker(EDGE_PATH, CHROME_PATH),
            popen_factory=popen_factory,
            directory_maker=MagicMock(),
            process_job_factory=MagicMock(return_value=make_process_job()),
            default_browser_open=default_open,
        )

        self.assertEqual(result.plan.browser.kind, LAUNCHER.BrowserKind.CHROME)
        self.assertEqual(popen_factory.call_count, 2)
        self.assertEqual(popen_factory.call_args_list[0].args[0][0], str(EDGE_PATH))
        self.assertEqual(popen_factory.call_args_list[1].args[0][0], str(CHROME_PATH))
        default_open.assert_not_called()

    def test_successful_edge_exit_does_not_trigger_chrome(self) -> None:
        edge_process = make_process()
        popen_factory = MagicMock(return_value=edge_process)

        result = LAUNCHER.open_quantlab_browser(
            URL,
            app_data_root=APP_DATA_ROOT,
            environment=FAKE_ENVIRONMENT,
            path_is_file=path_checker(EDGE_PATH, CHROME_PATH),
            popen_factory=popen_factory,
            directory_maker=MagicMock(),
            process_job_factory=MagicMock(return_value=make_process_job()),
            default_browser_open=MagicMock(),
        )
        edge_process.poll.return_value = 0

        self.assertEqual(result.plan.browser.kind, LAUNCHER.BrowserKind.EDGE)
        popen_factory.assert_called_once()

    def test_early_edge_exit_is_a_startup_failure_then_chrome_is_tried(self) -> None:
        edge_process = make_process()
        edge_process.poll.return_value = 1
        chrome_process = make_process(4200)
        popen_factory = MagicMock(side_effect=[edge_process, chrome_process])
        edge_job = make_process_job()
        chrome_job = make_process_job()

        result = LAUNCHER.open_quantlab_browser(
            URL,
            app_data_root=APP_DATA_ROOT,
            environment=FAKE_ENVIRONMENT,
            path_is_file=path_checker(EDGE_PATH, CHROME_PATH),
            popen_factory=popen_factory,
            directory_maker=MagicMock(),
            process_job_factory=MagicMock(side_effect=[edge_job, chrome_job]),
            default_browser_open=MagicMock(),
        )

        self.assertEqual(result.plan.browser.kind, LAUNCHER.BrowserKind.CHROME)
        self.assertEqual(popen_factory.call_count, 2)
        edge_job.terminate.assert_called_once_with()
        edge_job.close.assert_called_once_with()

    def test_both_isolated_browsers_failing_opens_default_once(self) -> None:
        default_open = MagicMock(return_value=True)
        popen_factory = MagicMock(side_effect=[OSError("edge"), OSError("chrome")])
        process_job_factory = MagicMock(side_effect=[make_process_job(), make_process_job()])

        result = LAUNCHER.open_quantlab_browser(
            URL,
            app_data_root=APP_DATA_ROOT,
            environment=FAKE_ENVIRONMENT,
            path_is_file=path_checker(EDGE_PATH, CHROME_PATH),
            popen_factory=popen_factory,
            directory_maker=MagicMock(),
            process_job_factory=process_job_factory,
            default_browser_open=default_open,
        )

        self.assertTrue(result.used_default_browser)
        self.assertIsNone(result.process)
        self.assertEqual(result.warning, LAUNCHER.DEFAULT_BROWSER_WARNING)
        self.assertEqual(popen_factory.call_count, 2)
        default_open.assert_called_once_with(URL, new=1)

    def test_missing_browsers_use_default_with_complete_warning(self) -> None:
        default_open = MagicMock(return_value=True)
        result = LAUNCHER.open_quantlab_browser(
            URL,
            app_data_root=APP_DATA_ROOT,
            environment=FAKE_ENVIRONMENT,
            path_is_file=path_checker(),
            default_browser_open=default_open,
        )
        self.assertEqual(
            result.warning,
            "当前未找到可用的隔离浏览器。浏览器扩展可能影响页面显示；"
            "如页面异常，请使用无痕窗口或将 localhost 加入插件白名单。",
        )
        default_open.assert_called_once_with(URL, new=1)

    def test_browser_failure_log_does_not_include_executable_path(self) -> None:
        browser_path = str(EDGE_PATH)
        with patch.object(LAUNCHER.logging, "warning") as warning:
            LAUNCHER.open_quantlab_browser(
                URL,
                app_data_root=APP_DATA_ROOT,
                environment=FAKE_ENVIRONMENT,
                path_is_file=path_checker(EDGE_PATH),
                popen_factory=MagicMock(side_effect=OSError(f"failed: {browser_path}")),
                directory_maker=MagicMock(),
                process_job_factory=MagicMock(return_value=make_process_job()),
                default_browser_open=MagicMock(),
            )
        self.assertNotIn(browser_path, repr(warning.call_args_list))


class LauncherLifecycleTests(unittest.TestCase):
    def test_choose_port_uses_first_available_local_port(self) -> None:
        with patch.object(LAUNCHER, "port_is_available", side_effect=[False, False, True]):
            self.assertEqual(LAUNCHER.choose_port(3000), 3002)

    def test_choose_port_reports_exhaustion(self) -> None:
        with patch.object(LAUNCHER, "port_is_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "No free local port"):
                LAUNCHER.choose_port(3000)

    def test_http_failure_never_opens_browser_and_stops_server(self) -> None:
        server_process = MagicMock()
        browser_open = MagicMock()
        with (
            patch.object(LAUNCHER, "stop_server") as stop_server,
            patch.object(LAUNCHER, "wait_for_port_release", return_value=True) as wait_port,
        ):
            LAUNCHER.run_desktop_session(
                server_process,
                3000,
                server_waiter=MagicMock(return_value=False),
                browser_opener=browser_open,
                sleep=MagicMock(),
            )
        browser_open.assert_not_called()
        stop_server.assert_called_once_with(server_process)
        wait_port.assert_called_once_with(3000)

    def test_ready_opens_browser_once_and_browser_close_stops_service(self) -> None:
        server_process = MagicMock()
        server_process.is_alive.return_value = True
        process = make_process()
        process_job = make_process_job()
        process_job.active_process_count.side_effect = [1, 0]
        plan = make_plan()
        result = LAUNCHER.BrowserLaunchResult(plan, process, False, None, process_job)
        browser_open = MagicMock(return_value=result)
        sleep = MagicMock()
        with (
            patch.object(LAUNCHER, "terminate_browser_process_tree") as terminate_browser,
            patch.object(LAUNCHER, "stop_server") as stop_server,
            patch.object(LAUNCHER, "wait_for_port_release", return_value=True) as wait_port,
        ):
            LAUNCHER.run_desktop_session(
                server_process,
                3000,
                server_waiter=MagicMock(return_value=True),
                browser_opener=browser_open,
                sleep=sleep,
            )
        browser_open.assert_called_once_with(URL)
        sleep.assert_called_once_with(LAUNCHER.BROWSER_MONITOR_INTERVAL_SECONDS)
        terminate_browser.assert_called_once_with(process, process_job)
        stop_server.assert_called_once_with(server_process)
        wait_port.assert_called_once_with(3000)

    def test_exited_proxy_is_not_mistaken_for_closed_job(self) -> None:
        process = make_process()
        process.poll.return_value = 0
        process_job = make_process_job(active_process_count=2)
        result = LAUNCHER.BrowserLaunchResult(make_plan(), process, False, None, process_job)
        self.assertTrue(LAUNCHER.isolated_browser_is_active(result))

    def test_launcher_has_no_visible_tk_or_tray_control_surface(self) -> None:
        source = LAUNCHER_PATH.read_text(encoding="utf-8")
        readme = WINDOWS_README_PATH.read_text(encoding="utf-8")
        for excluded in (
            "LauncherWindow",
            "tk.Tk()",
            "ttk.Frame",
            "QuantLab 正在运行",
            "关闭 QuantLab",
            "TrayController",
            "pystray",
        ):
            self.assertNotIn(excluded, source)
        self.assertIn("不显示额外的桌面控制面板", readme)

    def test_streamlit_page_cannot_relaunch_desktop_browser(self) -> None:
        app_source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("desktop_launcher", app_source)
        self.assertNotIn("open_quantlab_browser", app_source)
        self.assertNotIn("webbrowser.open", app_source)

    def test_desktop_default_server_is_fastapi_not_streamlit(self) -> None:
        source = LAUNCHER_PATH.read_text(encoding="utf-8")
        self.assertIn("def run_fastapi_server", source)
        self.assertIn("/api/health", source)
        self.assertNotIn("from streamlit.web import bootstrap", source)
        self.assertNotIn("write_streamlit_entry", source)

    def test_wait_for_server_requires_http_200(self) -> None:
        process = MagicMock()
        process.is_alive.return_value = True
        response = MagicMock()
        response.status = 200
        response.__enter__.return_value = response
        with patch.object(LAUNCHER, "urlopen", return_value=response) as request:
            self.assertTrue(LAUNCHER.wait_for_server(process, 3000))
        self.assertEqual(
            request.call_args_list,
            [
                call("http://127.0.0.1:3000/api/health", timeout=0.75),
                call("http://127.0.0.1:3000/", timeout=0.75),
            ],
        )

    def test_source_frontend_assets_resolve_to_vite_dist(self) -> None:
        self.assertEqual(
            LAUNCHER.resolve_frontend_directory(source_root=ROOT),
            FRONTEND_DIST_PATH,
        )

    def test_missing_frontend_assets_fail_before_service_start(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "React assets are missing"):
            LAUNCHER.resolve_frontend_directory(source_root=ROOT / "missing")

    def test_stop_server_terminates_and_joins_child(self) -> None:
        process = MagicMock()
        process.is_alive.side_effect = [True, False, False]
        self.assertTrue(LAUNCHER.stop_server(process))
        process.terminate.assert_called_once_with()
        process.join.assert_called_once_with(timeout=8)
        process.kill.assert_not_called()

    def test_wait_for_port_release_observes_released_port(self) -> None:
        port_check = MagicMock(side_effect=[False, True])
        monotonic = MagicMock(side_effect=[0.0, 0.0, 0.1])
        sleep = MagicMock()
        self.assertTrue(
            LAUNCHER.wait_for_port_release(
                3000,
                timeout=1,
                port_check=port_check,
                monotonic=monotonic,
                sleep=sleep,
            )
        )
        sleep.assert_called_once_with(0.1)


class DesktopNetworkPlanTests(unittest.TestCase):
    def test_private_ipv4_discovery_is_filtered_deduplicated_and_sorted(self) -> None:
        resolver = MagicMock(
            return_value=[
                (2, 1, 6, "", ("169.254.1.2", 0)),
                (2, 1, 6, "", ("192.168.10.8", 0)),
                (2, 1, 6, "", ("127.0.0.1", 0)),
                (2, 1, 6, "", ("10.0.0.4", 0)),
                (2, 1, 6, "", ("192.168.10.8", 0)),
                (2, 1, 6, "", ("8.8.8.8", 0)),
            ]
        )

        actual = LAUNCHER.discover_private_ipv4(
            hostname_factory=lambda: "quantlab-pc",
            address_resolver=resolver,
        )

        self.assertEqual(actual, ("10.0.0.4", "192.168.10.8"))
        resolver.assert_called_once_with(
            "quantlab-pc",
            None,
            family=LAUNCHER.socket.AF_INET,
            type=LAUNCHER.socket.SOCK_STREAM,
        )

    def test_desktop_is_the_default_and_lan_requires_a_private_address(self) -> None:
        desktop = LAUNCHER.select_desktop_network_plan(
            3000,
            lan_enabled=False,
            address_discoverer=MagicMock(side_effect=AssertionError("must not scan")),
        )
        unavailable = LAUNCHER.select_desktop_network_plan(
            3000,
            lan_enabled=True,
            address_discoverer=lambda: (),
        )

        self.assertEqual(desktop, LAUNCHER.DesktopNetworkPlan("DESKTOP", "127.0.0.1", None))
        self.assertEqual(unavailable, desktop)

    def test_lan_plan_binds_all_interfaces_but_publishes_only_private_url(self) -> None:
        plan = LAUNCHER.select_desktop_network_plan(
            3012,
            lan_enabled=True,
            address_discoverer=lambda: ("192.168.50.7",),
        )

        self.assertEqual(plan.mode, "LAN")
        self.assertEqual(plan.bind_host, "0.0.0.0")
        self.assertEqual(plan.lan_url, "http://192.168.50.7:3012/")

    def test_lan_setting_is_explicit_opt_in_and_read_failure_is_safe(self) -> None:
        self.assertTrue(LAUNCHER.load_lan_access_setting(lambda: {"lan_enabled": True}))
        self.assertFalse(LAUNCHER.load_lan_access_setting(lambda: {"lan_enabled": "true"}))
        self.assertFalse(
            LAUNCHER.load_lan_access_setting(
                MagicMock(side_effect=RuntimeError("database unavailable"))
            )
        )

    def test_network_environment_is_complete_and_disables_stale_lan_url(self) -> None:
        environment = {"QUANTLAB_LAN_URL": "http://stale/"}
        plan = LAUNCHER.DesktopNetworkPlan("LAN", "0.0.0.0", "http://192.168.1.5:3010/")
        LAUNCHER.apply_network_plan_environment(plan, 3010, environment=environment)
        self.assertEqual(
            environment,
            {
                "QUANTLAB_MODE": "LAN",
                "QUANTLAB_HOST": "0.0.0.0",
                "QUANTLAB_PORT": "3010",
                "QUANTLAB_LAN_URL": "http://192.168.1.5:3010/",
            },
        )

        LAUNCHER.apply_network_plan_environment(
            LAUNCHER.DesktopNetworkPlan("DESKTOP", "127.0.0.1", None),
            3010,
            environment=environment,
        )
        self.assertNotIn("QUANTLAB_LAN_URL", environment)
        self.assertEqual(environment["QUANTLAB_HOST"], "127.0.0.1")

    def test_browser_continues_to_use_loopback_in_lan_mode(self) -> None:
        process = MagicMock()
        process.is_alive.side_effect = [True, False, False]
        browser_result = LAUNCHER.BrowserLaunchResult(None, None, True, None)
        browser_opener = MagicMock(return_value=browser_result)

        LAUNCHER.run_desktop_session(
            process,
            3015,
            server_waiter=MagicMock(return_value=True),
            browser_opener=browser_opener,
            sleep=MagicMock(),
        )

        browser_opener.assert_called_once_with("http://localhost:3015/")


class SmokeTestLifecycleTests(unittest.TestCase):
    def make_smoke_dependencies(self) -> tuple[dict[str, object], MagicMock]:
        process = MagicMock()
        process.pid = 8123
        dependencies: dict[str, object] = {
            "port_selector": MagicMock(return_value=3000),
            "frontend_locator": MagicMock(return_value=Path("frontend")),
            "offline_runner": MagicMock(),
            "server_starter": MagicMock(return_value=process),
            "server_waiter": MagicMock(return_value=True),
            "server_stopper": MagicMock(return_value=True),
            "port_waiter": MagicMock(return_value=True),
            "logger": MagicMock(),
        }
        return dependencies, process

    def test_smoke_success_is_bounded_and_closes_process_handle(self) -> None:
        dependencies, process = self.make_smoke_dependencies()

        status = LAUNCHER.run_smoke_test(**dependencies)

        self.assertEqual(status, 0)
        dependencies["server_stopper"].assert_called_once_with(
            process,
            terminate_timeout=LAUNCHER.SMOKE_SERVER_STOP_TIMEOUT_SECONDS,
            kill_timeout=LAUNCHER.SMOKE_SERVER_KILL_TIMEOUT_SECONDS,
        )
        dependencies["port_waiter"].assert_called_once_with(
            3000,
            timeout=LAUNCHER.SMOKE_PORT_RELEASE_TIMEOUT_SECONDS,
        )
        process.close.assert_called_once_with()
        dependencies["offline_runner"].assert_called_once_with()
        messages = [call.args[0] for call in dependencies["logger"].call_args_list]
        self.assertEqual(
            messages,
            [
                "SMOKE_START",
                "OFFLINE_FIXTURE_OK",
                "SERVICE_PID 8123",
                "HTTP_READY",
                "CLEANUP_START",
                "SERVICE_STOPPED",
                "PORT_RELEASED",
                "SMOKE_SUCCESS",
            ],
        )

    def test_http_failure_still_stops_service_and_releases_port(self) -> None:
        dependencies, process = self.make_smoke_dependencies()
        dependencies["server_waiter"].return_value = False

        status = LAUNCHER.run_smoke_test(**dependencies)

        self.assertEqual(status, 1)
        dependencies["server_stopper"].assert_called_once()
        dependencies["port_waiter"].assert_called_once()
        process.close.assert_called_once_with()
        messages = [call.args[0] for call in dependencies["logger"].call_args_list]
        self.assertIn("SMOKE_FAILURE HTTP_NOT_READY", messages)

    def test_start_failure_still_releases_port(self) -> None:
        dependencies, _ = self.make_smoke_dependencies()
        dependencies["server_starter"].side_effect = RuntimeError("failed")

        status = LAUNCHER.run_smoke_test(**dependencies)

        self.assertEqual(status, 1)
        dependencies["server_stopper"].assert_not_called()
        dependencies["port_waiter"].assert_called_once_with(
            3000,
            timeout=LAUNCHER.SMOKE_PORT_RELEASE_TIMEOUT_SECONDS,
        )
        dependencies["offline_runner"].assert_called_once_with()

    def test_offline_fixture_failure_never_starts_service(self) -> None:
        dependencies, _ = self.make_smoke_dependencies()
        dependencies["offline_runner"].side_effect = RuntimeError("fixture failed")

        status = LAUNCHER.run_smoke_test(**dependencies)

        self.assertEqual(status, 1)
        dependencies["server_starter"].assert_not_called()
        dependencies["port_waiter"].assert_called_once()

    def test_stop_timeout_returns_failure_without_closing_live_handle(self) -> None:
        dependencies, process = self.make_smoke_dependencies()
        dependencies["server_stopper"].return_value = False

        status = LAUNCHER.run_smoke_test(**dependencies)

        self.assertEqual(status, 1)
        process.close.assert_not_called()
        messages = [call.args[0] for call in dependencies["logger"].call_args_list]
        self.assertIn("SMOKE_FAILURE SERVICE_STOP_TIMEOUT", messages)

    def test_port_release_timeout_returns_failure(self) -> None:
        dependencies, _ = self.make_smoke_dependencies()
        dependencies["port_waiter"].return_value = False

        status = LAUNCHER.run_smoke_test(**dependencies)

        self.assertEqual(status, 1)
        messages = [call.args[0] for call in dependencies["logger"].call_args_list]
        self.assertIn("SMOKE_FAILURE PORT_NOT_RELEASED", messages)

    def test_smoke_main_skips_mutex_message_browser_and_desktop_session(self) -> None:
        with (
            patch.object(LAUNCHER.multiprocessing, "freeze_support"),
            patch.object(LAUNCHER, "configure_logging"),
            patch.object(LAUNCHER.sys, "argv", ["QuantLab.exe", "--smoke-test"]),
            patch.dict(LAUNCHER.os.environ, {"QUANTLAB_PORT": "32117"}),
            patch.object(LAUNCHER, "run_smoke_test", return_value=0) as smoke,
            patch.object(LAUNCHER, "acquire_single_instance_guard") as acquire_guard,
            patch.object(LAUNCHER, "show_second_instance_message") as message,
            patch.object(LAUNCHER, "open_quantlab_browser") as browser,
            patch.object(LAUNCHER, "run_desktop_session") as desktop,
            patch.object(LAUNCHER.logging, "shutdown") as logging_shutdown,
            self.assertRaises(SystemExit) as exit_context,
        ):
            LAUNCHER.main()

        self.assertEqual(exit_context.exception.code, 0)
        smoke.assert_called_once_with(preferred_port=32117)
        acquire_guard.assert_not_called()
        message.assert_not_called()
        browser.assert_not_called()
        desktop.assert_not_called()
        logging_shutdown.assert_called_once_with()

    def test_repeated_smoke_runs_close_each_process_before_reusing_port(self) -> None:
        first_dependencies, first_process = self.make_smoke_dependencies()
        second_dependencies, second_process = self.make_smoke_dependencies()

        self.assertEqual(LAUNCHER.run_smoke_test(**first_dependencies), 0)
        self.assertEqual(LAUNCHER.run_smoke_test(**second_dependencies), 0)

        first_process.close.assert_called_once_with()
        second_process.close.assert_called_once_with()
        first_dependencies["port_waiter"].assert_called_once()
        second_dependencies["port_waiter"].assert_called_once()

    def test_server_process_is_daemonized_but_cleanup_remains_explicit(self) -> None:
        process = MagicMock()
        context = MagicMock()
        context.Process.return_value = process
        with patch.object(LAUNCHER.multiprocessing, "get_context", return_value=context):
            actual = LAUNCHER.start_server(3000, Path("frontend"))

        self.assertIs(actual, process)
        self.assertTrue(context.Process.call_args.kwargs["daemon"])
        self.assertEqual(context.Process.call_args.kwargs["target"], LAUNCHER.run_fastapi_server)
        self.assertEqual(
            context.Process.call_args.kwargs["args"],
            (3000, "frontend"),
        )
        self.assertEqual(context.Process.call_args.kwargs["name"], "QuantLab FastAPI")
        process.start.assert_called_once_with()


class BrowserProcessCleanupTests(unittest.TestCase):
    def test_graceful_cleanup_targets_only_saved_root_pid(self) -> None:
        process = make_process(4400)
        command_runner = MagicMock()

        LAUNCHER.terminate_browser_process_tree(
            process,
            command_runner=command_runner,
        )

        command_runner.assert_called_once_with(
            ["taskkill", "/PID", "4400", "/T"],
            shell=False,
            check=False,
            stdout=LAUNCHER.subprocess.DEVNULL,
            stderr=LAUNCHER.subprocess.DEVNULL,
        )
        process.wait.assert_called_once_with(timeout=5)
        self.assertNotIn("msedge.exe", repr(command_runner.call_args_list))
        self.assertNotIn("chrome.exe", repr(command_runner.call_args_list))

    def test_cleanup_forces_same_pid_tree_only_after_timeout(self) -> None:
        process = make_process(4500)
        process.wait.side_effect = [
            LAUNCHER.subprocess.TimeoutExpired(cmd="taskkill", timeout=5),
            None,
        ]
        command_runner = MagicMock()

        LAUNCHER.terminate_browser_process_tree(
            process,
            command_runner=command_runner,
        )

        self.assertEqual(
            command_runner.call_args_list,
            [
                call(
                    ["taskkill", "/PID", "4500", "/T"],
                    shell=False,
                    check=False,
                    stdout=LAUNCHER.subprocess.DEVNULL,
                    stderr=LAUNCHER.subprocess.DEVNULL,
                ),
                call(
                    ["taskkill", "/PID", "4500", "/T", "/F"],
                    shell=False,
                    check=False,
                    stdout=LAUNCHER.subprocess.DEVNULL,
                    stderr=LAUNCHER.subprocess.DEVNULL,
                ),
            ],
        )

    def test_already_exited_browser_is_not_scanned_or_killed(self) -> None:
        process = make_process(4600)
        process.poll.return_value = 0
        command_runner = MagicMock()
        LAUNCHER.terminate_browser_process_tree(process, command_runner=command_runner)
        command_runner.assert_not_called()
        process.wait.assert_not_called()

    def test_exited_proxy_still_terminates_its_assigned_job(self) -> None:
        process = make_process(4700)
        process.poll.return_value = 0
        process_job = make_process_job()
        command_runner = MagicMock()

        LAUNCHER.terminate_browser_process_tree(
            process,
            process_job,
            command_runner=command_runner,
        )

        command_runner.assert_not_called()
        process_job.terminate.assert_called_once_with()
        process_job.close.assert_called_once_with()

    def test_timeout_terminates_assigned_job_without_browser_name_cleanup(self) -> None:
        process = make_process(4800)
        process.wait.side_effect = [
            LAUNCHER.subprocess.TimeoutExpired(cmd="taskkill", timeout=5),
            None,
        ]
        process_job = make_process_job()
        command_runner = MagicMock()

        LAUNCHER.terminate_browser_process_tree(
            process,
            process_job,
            command_runner=command_runner,
        )

        command_runner.assert_called_once_with(
            ["taskkill", "/PID", "4800", "/T"],
            shell=False,
            check=False,
            stdout=LAUNCHER.subprocess.DEVNULL,
            stderr=LAUNCHER.subprocess.DEVNULL,
        )
        process_job.terminate.assert_called_once_with()
        process_job.close.assert_called_once_with()
        self.assertNotIn("msedge.exe", repr(command_runner.call_args_list))
        self.assertNotIn("chrome.exe", repr(command_runner.call_args_list))

    def test_launcher_source_never_uses_global_browser_name_termination(self) -> None:
        source = LAUNCHER_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"/IM"', source)
        self.assertNotIn("taskkill /IM", source)
        self.assertNotIn("Get-CimInstance", source)


class WindowsPackagingTests(unittest.TestCase):
    def test_formal_build_can_reuse_verified_environment_and_copies_release_notes(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("[switch]$UseExistingEnvironment", script)
        self.assertIn("if ($UseExistingEnvironment)", script)
        self.assertIn("import PyInstaller, quant_lab", script)
        self.assertIn('"QuantLab-v$Version-windows-x64.zip"', script)
        self.assertIn('Join-Path $ProjectRoot "RELEASE-NOTES-v$Version.md"', script)
        self.assertIn("Release notes are missing", script)
        self.assertIn("Copy-Item -LiteralPath $ReleaseNotesSource", script)

    def test_test_build_uses_separate_output_directories_and_name(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("[switch]$BrowserIsolationTest", script)
        self.assertIn("browser-isolation-test-v0.1.1", script)
        self.assertIn("build\\ql-v011-venv", script)
        self.assertIn("build\\pip-cache-v011", script)
        self.assertIn("QuantLab-v0.1.1-browser-isolation-test-windows-x64.zip", script)
        self.assertIn('Join-Path $ProjectRoot "release"', script)

    def test_sidebar_test_build_cannot_overwrite_v010_release(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("[switch]$SidebarTest", script)
        self.assertIn("build\\ql-v011-sidebar", script)
        self.assertIn("dist\\ql-v011-sidebar", script)
        self.assertIn("release-v0.1.1-sidebar-test", script)
        self.assertIn("QuantLab-v0.1.1-sidebar-test-windows-x64.zip", script)

    def test_autonomous_ux_build_uses_only_independent_output_paths(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("[switch]$AutonomousUxTest", script)
        self.assertIn("build-autonomous-ux-test", script)
        self.assertIn("dist-autonomous-ux-test", script)
        self.assertIn("release-autonomous-ux-test", script)
        self.assertIn("QuantLab-v0.1.1-autonomous-ux-test-windows-x64.zip", script)

    def test_rc1_build_uses_independent_paths_and_runtime_version_filename(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("[switch]$ReleaseCandidate", script)
        self.assertIn("build-v0.1.1-rc1", script)
        self.assertIn("dist-v0.1.1-rc1", script)
        self.assertIn("release-v0.1.1-rc1", script)
        self.assertIn('"QuantLab-v$Version-rc1-windows-x64.zip"', script)
        self.assertIn("Refusing to overwrite an existing RC1 artifact", script)
        self.assertIn("THIRD-PARTY-NOTICES.txt", script)
        self.assertIn("RC1-TEST-CHECKLIST.md", script)

    def test_usability_mobile_preview_bundles_react_and_uses_independent_paths(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        spec = (ROOT / "packaging" / "windows" / "QuantLab.spec").read_text(encoding="utf-8")

        self.assertIn('[Alias("HKProductPreview")]', script)
        self.assertIn("[switch]$UsabilityMobilePreview", script)
        self.assertIn('Join-Path $ProjectRoot "build\\q21"', script)
        self.assertIn("dist-v0.2.1-usability-mobile-preview", script)
        self.assertIn("release-v0.2.1-usability-mobile-preview", script)
        self.assertIn('"QuantLab-v$Version-usability-mobile-preview-windows-x64.zip"', script)
        self.assertIn("Refusing to overwrite an existing usability/mobile preview artifact", script)
        self.assertIn('Join-Path $ReleasePath "TEST-CHECKLIST.md"', script)
        self.assertIn("node_modules\\vite\\bin\\vite.js", script)
        self.assertIn('"frontend", "dist"', spec)
        self.assertIn('"fastapi"', spec)
        self.assertIn('"uvicorn"', spec)
        self.assertNotIn('"app.streamlit_app"', spec)

    def test_pre_publication_build_uses_independent_paths_and_refuses_overwrite(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("[switch]$PrePublicationTest", script)
        self.assertIn("build-v0.1.1-pre-publication-test", script)
        self.assertIn("dist-v0.1.1-pre-publication-test", script)
        self.assertIn("release-v0.1.1-pre-publication-test", script)
        self.assertIn('"QuantLab-v$Version-pre-publication-test-windows-x64.zip"', script)
        self.assertIn("ql-v011-prepub-pip", script)
        self.assertIn("Refusing to overwrite an existing pre-publication artifact", script)

    def test_chart_dark_final_build_uses_independent_paths_and_refuses_overwrite(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("[switch]$ChartDarkFinalTest", script)
        self.assertIn("build-chart-dark-final-test", script)
        self.assertIn("dist-chart-dark-final-test", script)
        self.assertIn("release-chart-dark-final-test", script)
        self.assertIn('"QuantLab-v$Version-chart-dark-final-test-windows-x64.zip"', script)
        self.assertIn("ql-v011-chart-dark-final-pip", script)
        self.assertIn("Refusing to overwrite an existing chart dark final artifact", script)
        self.assertIn("CHART-DARK-FINAL-CHECKLIST.md", script)

    def test_reproducibility_builds_use_two_isolated_offline_capable_paths(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('[ValidateSet("a", "b")]', script)
        self.assertIn("build-repro-$ReproducibilityRun", script)
        self.assertIn("dist-repro-$ReproducibilityRun", script)
        self.assertIn("release-repro-$ReproducibilityRun", script)
        self.assertIn('"QuantLab-v$Version-repro-$ReproducibilityRun-windows-x64.zip"', script)
        self.assertIn("QUANTLAB_WHEELHOUSE", script)
        self.assertIn('"--no-index", "--find-links", $Wheelhouse', script)
        self.assertIn("Refusing to overwrite an existing reproducibility artifact", script)

    def test_repeated_build_removes_only_known_setuptools_intermediates(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('Join-Path $ProjectRoot "build\\lib"', script)
        self.assertIn('Join-Path $ProjectRoot "build\\bdist.win-amd64"', script)
        self.assertIn("Remove-SafeProjectPath $Target", script)

    def test_headless_launcher_build_does_not_require_tk(self) -> None:
        script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import tkinter", script)
        self.assertNotIn("tk.Tk()", script)
        self.assertNotIn("Tcl/Tk", script)
        self.assertIn("QUANTLAB_BUILD_PYTHON", script)

    def test_repository_outputs_do_not_contain_local_browser_paths(self) -> None:
        checked_files = [LAUNCHER_PATH, BUILD_SCRIPT_PATH, WINDOWS_README_PATH]
        checked_files.extend(
            path
            for path in EXAMPLE_DIRECTORY.iterdir()
            if path.suffix.lower() in {".html", ".json", ".csv", ".md"}
        )
        forbidden = (
            "C:\\Program Files\\Microsoft\\Edge",
            "C:\\Program Files\\Google\\Chrome",
        )
        for path in checked_files:
            content = path.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, content, path)
            self.assertIsNone(
                re.search(r"(?i)\b[A-Z]:\\Users\\[^\\\r\n]+", content),
                path,
            )

    def test_smoke_watchdog_is_bounded_and_targets_only_saved_root_pid(self) -> None:
        script = SMOKE_WATCHDOG_PATH.read_text(encoding="utf-8")
        self.assertIn("[ValidateRange(1, 120)]", script)
        self.assertIn("$StartInfo.RedirectStandardOutput = $true", script)
        self.assertIn("$StartInfo.RedirectStandardError = $true", script)
        self.assertIn("$Process.StandardOutput.ReadToEndAsync()", script)
        self.assertIn("$Process.StandardError.ReadToEndAsync()", script)
        self.assertIn("$Process.Dispose()", script)
        self.assertIn('"WATCHDOG_ROOT_PID=$($Process.Id)"', script)
        self.assertIn("& taskkill.exe /PID $Process.Id /T /F", script)
        self.assertNotIn("/IM", script)
        self.assertIn('"--smoke-test"', script)
        for marker in (
            "SMOKE_START",
            "SERVICE_PID",
            "HTTP_READY",
            "CLEANUP_START",
            "SERVICE_STOPPED",
            "PORT_RELEASED",
            "SMOKE_SUCCESS",
        ):
            self.assertIn(marker, script)


if __name__ == "__main__":
    unittest.main()
