from __future__ import annotations

import ctypes
import ipaddress
import logging
import multiprocessing
import os
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable, Collection, Mapping
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.request import urlopen

from quant_lab.__about__ import __version__

APP_NAME = "QuantLab"
DEFAULT_PORT = 3000
STARTUP_TIMEOUT_SECONDS = 60
SMOKE_SERVER_STOP_TIMEOUT_SECONDS = 15
SMOKE_SERVER_KILL_TIMEOUT_SECONDS = 5
SMOKE_PORT_RELEASE_TIMEOUT_SECONDS = 20
BROWSER_PROFILE_VERSION = "browser-profile-v1"
BROWSER_SHUTDOWN_TIMEOUT_SECONDS = 5
BROWSER_MONITOR_INTERVAL_SECONDS = 0.75
SINGLE_INSTANCE_MUTEX_NAME = "Local\\QuantLabDesktopLauncher-v1"
SECOND_INSTANCE_MESSAGE = "QuantLab 已经在运行，请切换到已打开的 QuantLab 浏览器窗口。"
_ERROR_ALREADY_EXISTS = 183
DEFAULT_BROWSER_WARNING = (
    "当前未找到可用的隔离浏览器。浏览器扩展可能影响页面显示；"
    "如页面异常，请使用无痕窗口或将 localhost 加入插件白名单。"
)
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000


@dataclass(frozen=True)
class DesktopNetworkPlan:
    mode: str
    bind_host: str
    lan_url: str | None


class _JobObjectBasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class BrowserKind(str, Enum):
    EDGE = "edge"
    CHROME = "chrome"


@dataclass(frozen=True)
class BrowserExecutable:
    kind: BrowserKind
    path: Path


@dataclass(frozen=True)
class BrowserLaunchPlan:
    browser: BrowserExecutable
    url: str
    profile_directory: Path
    command: tuple[str, ...]


class BrowserProcessJob:
    def __init__(self, handle: int, kernel32: object) -> None:
        self._handle = handle
        self._kernel32 = kernel32
        self._closed = False

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise OSError("The browser process handle is unavailable.")
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def active_process_count(self) -> int:
        if self._closed:
            return 0
        information = _JobObjectBasicAccountingInformation()
        returned_length = wintypes.DWORD()
        if not self._kernel32.QueryInformationJobObject(
            self._handle,
            _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
            ctypes.byref(returned_length),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(information.ActiveProcesses)

    def terminate(self) -> None:
        if self._closed:
            return
        if not self._kernel32.TerminateJobObject(self._handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._kernel32.CloseHandle(self._handle):
            logging.warning("Closing the isolated browser Job Object failed.")


class SingleInstanceGuard:
    def __init__(self, handle: int | None, kernel32: object | None) -> None:
        self._handle = handle
        self._kernel32 = kernel32
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._handle is None or self._kernel32 is None:
            return
        if not self._kernel32.CloseHandle(self._handle):
            logging.warning("Closing the QuantLab single-instance mutex failed.")


@dataclass(frozen=True)
class ManagedBrowserProcess:
    process: subprocess.Popen[bytes]
    process_job: BrowserProcessJob


@dataclass(frozen=True)
class BrowserLaunchResult:
    plan: BrowserLaunchPlan | None
    process: subprocess.Popen[bytes] | None
    used_default_browser: bool
    warning: str | None
    process_job: BrowserProcessJob | None = None


def _load_mutex_kernel32() -> object:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def acquire_single_instance_guard(
    *,
    kernel32: object | None = None,
    get_last_error: Callable[[], int] | None = None,
    set_last_error: Callable[[int], None] | None = None,
) -> SingleInstanceGuard | None:
    if os.name != "nt" and kernel32 is None:
        return SingleInstanceGuard(None, None)
    api = _load_mutex_kernel32() if kernel32 is None else kernel32
    read_error = ctypes.get_last_error if get_last_error is None else get_last_error
    clear_error = ctypes.set_last_error if set_last_error is None else set_last_error
    clear_error(0)
    handle = api.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(read_error())
    if read_error() == _ERROR_ALREADY_EXISTS:
        api.CloseHandle(handle)
        return None
    return SingleInstanceGuard(int(handle), api)


def show_second_instance_message(
    show_message: Callable[[str, str], object] | None = None,
) -> None:
    if show_message is not None:
        show_message(APP_NAME, SECOND_INSTANCE_MESSAGE)
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.MessageBoxW(None, SECOND_INSTANCE_MESSAGE, APP_NAME, 0x40)


def _local_app_data_path(environment: Mapping[str, str] | None = None) -> Path:
    values = os.environ if environment is None else environment
    base = Path(values.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / APP_NAME


def local_app_data_root() -> Path:
    root = _local_app_data_path()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _browser_candidate_paths(
    kind: BrowserKind,
    environment: Mapping[str, str],
) -> tuple[Path, ...]:
    relative_path = (
        ("Microsoft", "Edge", "Application", "msedge.exe")
        if kind is BrowserKind.EDGE
        else ("Google", "Chrome", "Application", "chrome.exe")
    )
    roots = (
        environment.get("ProgramFiles(x86)"),
        environment.get("ProgramFiles"),
        environment.get("LOCALAPPDATA"),
    )
    candidates: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root:
            continue
        candidate = Path(root).joinpath(*relative_path)
        normalized = os.path.normcase(str(candidate))
        if normalized not in seen:
            seen.add(normalized)
            candidates.append(candidate)
    return tuple(candidates)


def find_supported_browser(
    environment: Mapping[str, str] | None = None,
    *,
    excluded: Collection[BrowserKind] = (),
    path_is_file: Callable[[Path], bool] | None = None,
) -> BrowserExecutable | None:
    values = os.environ if environment is None else environment
    is_file = Path.is_file if path_is_file is None else path_is_file
    excluded_kinds = set(excluded)
    for kind in (BrowserKind.EDGE, BrowserKind.CHROME):
        if kind in excluded_kinds:
            continue
        for candidate in _browser_candidate_paths(kind, values):
            if is_file(candidate):
                return BrowserExecutable(kind=kind, path=candidate)
    return None


def get_quantlab_browser_profile_dir(
    kind: BrowserKind,
    app_data_root: Path | None = None,
) -> Path:
    root = _local_app_data_path() if app_data_root is None else app_data_root
    return root / BROWSER_PROFILE_VERSION / kind.value


def build_browser_command(
    executable: Path,
    url: str,
    profile_directory: Path,
) -> tuple[str, ...]:
    return (
        str(executable),
        f"--app={url}",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile_directory}",
    )


def select_browser_launch_plan(
    url: str,
    *,
    app_data_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
    excluded: Collection[BrowserKind] = (),
    path_is_file: Callable[[Path], bool] | None = None,
) -> BrowserLaunchPlan | None:
    browser = find_supported_browser(
        environment,
        excluded=excluded,
        path_is_file=path_is_file,
    )
    if browser is None:
        return None
    profile_directory = get_quantlab_browser_profile_dir(browser.kind, app_data_root)
    return BrowserLaunchPlan(
        browser=browser,
        url=url,
        profile_directory=profile_directory,
        command=build_browser_command(browser.path, url, profile_directory),
    )


def _create_profile_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def create_browser_process_job() -> BrowserProcessJob:
    if os.name != "nt":
        raise OSError("Isolated browser process control requires Windows.")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    information = _JobObjectExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        handle,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        error_code = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(error_code)
    return BrowserProcessJob(handle, kernel32)


def _stop_unmanaged_browser_process(process: subprocess.Popen[bytes]) -> None:
    try:
        process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    except OSError:
        logging.warning("Stopping an unassigned isolated browser process failed.")


def launch_isolated_browser(
    plan: BrowserLaunchPlan,
    *,
    popen_factory: Callable[..., subprocess.Popen[bytes]] | None = None,
    directory_maker: Callable[[Path], None] | None = None,
    process_job_factory: Callable[[], BrowserProcessJob] | None = None,
) -> ManagedBrowserProcess:
    make_directory = _create_profile_directory if directory_maker is None else directory_maker
    make_directory(plan.profile_directory)
    create_process = subprocess.Popen if popen_factory is None else popen_factory
    create_job = create_browser_process_job if process_job_factory is None else process_job_factory
    process_job = create_job()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = create_process(list(plan.command), shell=False)
        process_job.assign(process)
    except (OSError, subprocess.SubprocessError):
        process_job.close()
        if process is not None:
            _stop_unmanaged_browser_process(process)
        raise
    return ManagedBrowserProcess(process=process, process_job=process_job)


def open_quantlab_browser(
    url: str,
    *,
    app_data_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
    path_is_file: Callable[[Path], bool] | None = None,
    popen_factory: Callable[..., subprocess.Popen[bytes]] | None = None,
    directory_maker: Callable[[Path], None] | None = None,
    process_job_factory: Callable[[], BrowserProcessJob] | None = None,
    default_browser_open: Callable[..., bool] | None = None,
) -> BrowserLaunchResult:
    failed: set[BrowserKind] = set()
    while True:
        plan = select_browser_launch_plan(
            url,
            app_data_root=app_data_root,
            environment=environment,
            excluded=failed,
            path_is_file=path_is_file,
        )
        if plan is None:
            break
        try:
            managed_process = launch_isolated_browser(
                plan,
                popen_factory=popen_factory,
                directory_maker=directory_maker,
                process_job_factory=process_job_factory,
            )
        except (OSError, subprocess.SubprocessError) as error:
            logging.warning(
                "Isolated %s browser launch failed (%s).",
                plan.browser.kind.value,
                type(error).__name__,
            )
            failed.add(plan.browser.kind)
            continue
        process = managed_process.process
        if process.poll() is not None:
            logging.warning(
                "Isolated %s browser exited during startup.",
                plan.browser.kind.value,
            )
            terminate_browser_process_tree(process, managed_process.process_job)
            failed.add(plan.browser.kind)
            continue
        logging.info("Opened QuantLab in isolated %s application mode.", plan.browser.kind.value)
        return BrowserLaunchResult(
            plan=plan,
            process=process,
            used_default_browser=False,
            warning=None,
            process_job=managed_process.process_job,
        )

    open_default = webbrowser.open if default_browser_open is None else default_browser_open
    try:
        open_default(url, new=1)
    except OSError as error:
        logging.warning("Default browser launch failed (%s).", type(error).__name__)
    return BrowserLaunchResult(
        plan=None,
        process=None,
        used_default_browser=True,
        warning=DEFAULT_BROWSER_WARNING,
    )


def terminate_browser_process_tree(
    process: subprocess.Popen[bytes] | None,
    process_job: BrowserProcessJob | None = None,
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
    wait_timeout: float = BROWSER_SHUTDOWN_TIMEOUT_SECONDS,
) -> None:
    if process is None:
        if process_job is not None:
            process_job.close()
        return
    runner = subprocess.run if command_runner is None else command_runner
    root_pid = int(process.pid)
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    process_was_running = process.poll() is None
    timed_out = False
    if process_was_running:
        runner(
            ["taskkill", "/PID", str(root_pid), "/T"],
            shell=False,
            check=False,
            **quiet,
        )
        try:
            process.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True

    if process_job is not None:
        try:
            process_job.terminate()
        except OSError:
            logging.warning("Terminating the isolated browser Job Object failed.")
        finally:
            process_job.close()
        if timed_out:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logging.warning("Isolated browser process tree did not exit before timeout.")
        return

    if timed_out:
        runner(
            ["taskkill", "/PID", str(root_pid), "/T", "/F"],
            shell=False,
            check=False,
            **quiet,
        )
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logging.warning("Isolated browser process tree did not exit before timeout.")


def configure_logging() -> Path:
    log_directory = local_app_data_root() / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / "QuantLab.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    return log_path


def port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def choose_port(preferred: int = DEFAULT_PORT) -> int:
    for port in range(preferred, preferred + 20):
        if port_is_available(port):
            return port
    raise RuntimeError(f"No free local port is available near {preferred}.")


def discover_private_ipv4(
    *,
    hostname_factory: Callable[[], str] = socket.gethostname,
    address_resolver: Callable[..., list[tuple[object, ...]]] = socket.getaddrinfo,
) -> tuple[str, ...]:
    """Return deterministic private IPv4 candidates without changing firewall state."""
    try:
        addresses = address_resolver(
            hostname_factory(),
            None,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return ()

    candidates: set[str] = set()
    for address in addresses:
        try:
            value = str(address[4][0])
            parsed = ipaddress.ip_address(value)
        except (IndexError, TypeError, ValueError):
            continue
        if (
            isinstance(parsed, ipaddress.IPv4Address)
            and parsed.is_private
            and not parsed.is_loopback
            and not parsed.is_link_local
            and not parsed.is_unspecified
        ):
            candidates.add(value)
    return tuple(sorted(candidates, key=lambda item: tuple(int(part) for part in item.split("."))))


def select_desktop_network_plan(
    port: int,
    *,
    lan_enabled: bool,
    address_discoverer: Callable[[], tuple[str, ...]] = discover_private_ipv4,
) -> DesktopNetworkPlan:
    if lan_enabled:
        candidates = address_discoverer()
        if candidates:
            return DesktopNetworkPlan(
                mode="LAN",
                bind_host="0.0.0.0",
                lan_url=f"http://{candidates[0]}:{port}/",
            )
        logging.warning("LAN access was requested, but no private IPv4 address was found.")
    return DesktopNetworkPlan(mode="DESKTOP", bind_host="127.0.0.1", lan_url=None)


def load_lan_access_setting(
    settings_loader: Callable[[], Mapping[str, object]] | None = None,
) -> bool:
    """Read the explicit opt-in without making LAN availability a startup requirement."""
    try:
        if settings_loader is None:
            from quant_lab.storage.sqlite import SQLiteRepository

            settings_loader = SQLiteRepository().get_settings
        return settings_loader().get("lan_enabled") is True
    except Exception:
        logging.warning("LAN preference could not be read; continuing in desktop-only mode.")
        return False


def apply_network_plan_environment(
    plan: DesktopNetworkPlan,
    port: int,
    *,
    environment: dict[str, str] | None = None,
) -> None:
    values = os.environ if environment is None else environment
    values["QUANTLAB_MODE"] = plan.mode
    values["QUANTLAB_HOST"] = plan.bind_host
    values["QUANTLAB_PORT"] = str(port)
    if plan.lan_url is None:
        values.pop("QUANTLAB_LAN_URL", None)
    else:
        values["QUANTLAB_LAN_URL"] = plan.lan_url


def resolve_frontend_directory(
    *,
    runtime_root: Path | None = None,
    source_root: Path | None = None,
) -> Path:
    """Locate the built React assets without exposing the resolved path to the UI."""
    if runtime_root is not None:
        candidate = runtime_root / "frontend"
    elif getattr(sys, "frozen", False):
        candidate = Path(getattr(sys, "_MEIPASS")) / "frontend"
    else:
        project_root = source_root or Path(__file__).resolve().parents[2]
        candidate = project_root / "frontend" / "dist"
    if not (candidate / "index.html").is_file():
        raise RuntimeError("QuantLab React assets are missing; rebuild the frontend.")
    return candidate


def run_fastapi_server(port: int, frontend_directory: str) -> None:
    configure_logging()
    bind_host = os.environ.get("QUANTLAB_HOST", "127.0.0.1")
    mode = os.environ.get("QUANTLAB_MODE", "DESKTOP")
    logging.info("Starting QuantLab v%s in %s mode on port %s", __version__, mode, port)
    os.environ["QUANTLAB_DATA_DIR"] = str(local_app_data_root())

    import uvicorn

    from quant_lab.api.app import create_app

    app = create_app(frontend_directory=Path(frontend_directory))
    config = uvicorn.Config(
        app,
        host=bind_host,
        port=port,
        access_log=False,
        log_config=None,
        log_level="warning",
        server_header=False,
    )
    server = uvicorn.Server(config)
    server.run()


def wait_for_server(process: multiprocessing.Process, port: int) -> bool:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    health_url = f"http://127.0.0.1:{port}/api/health"
    frontend_url = f"http://127.0.0.1:{port}/"
    while time.monotonic() < deadline and process.is_alive():
        try:
            with urlopen(health_url, timeout=0.75) as response:
                api_ready = response.status == 200
            with urlopen(frontend_url, timeout=0.75) as response:
                frontend_ready = response.status == 200
            if api_ready and frontend_ready:
                return True
        except OSError:
            time.sleep(0.35)
    return False


def stop_server(
    process: multiprocessing.Process,
    *,
    terminate_timeout: float = 8,
    kill_timeout: float = 3,
) -> bool:
    if not process.is_alive():
        return True
    process.terminate()
    process.join(timeout=terminate_timeout)
    if process.is_alive():
        process.kill()
        process.join(timeout=kill_timeout)
    return not process.is_alive()


def wait_for_port_release(
    port: int,
    timeout: float = 5,
    *,
    port_check: Callable[[int], bool] | None = None,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bool:
    check = port_is_available if port_check is None else port_check
    clock = time.monotonic if monotonic is None else monotonic
    pause = time.sleep if sleep is None else sleep
    deadline = clock() + timeout
    while clock() < deadline:
        if check(port):
            return True
        pause(0.1)
    return check(port)


def start_server(port: int, frontend_directory: Path) -> multiprocessing.Process:
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=run_fastapi_server,
        args=(port, str(frontend_directory)),
        name="QuantLab FastAPI",
        daemon=True,
    )
    process.start()
    return process


def run_smoke_test(
    *,
    preferred_port: int = DEFAULT_PORT,
    port_selector: Callable[[int], int] = choose_port,
    frontend_locator: Callable[[], Path] = resolve_frontend_directory,
    offline_runner: Callable[[], object] | None = None,
    server_starter: Callable[[int, Path], multiprocessing.Process] = start_server,
    server_waiter: Callable[[multiprocessing.Process, int], bool] = wait_for_server,
    server_stopper: Callable[..., bool] = stop_server,
    port_waiter: Callable[..., bool] = wait_for_port_release,
    logger: Callable[[str], None] = logging.info,
) -> int:
    """Run a bounded, browser-free service health check."""
    process: multiprocessing.Process | None = None
    port: int | None = None
    http_ready = False
    service_stopped = True
    port_released = True
    cleanup_ok = True
    failure_reason: str | None = None
    if offline_runner is None:
        from quant_lab.application.hk_smoke import run_offline_hk_smoke

        offline_runner = run_offline_hk_smoke

    logger("SMOKE_START")
    try:
        port = port_selector(preferred_port)
        frontend_directory = frontend_locator()
        offline_runner()
        logger("OFFLINE_FIXTURE_OK")
        process = server_starter(port, frontend_directory)
        logger(f"SERVICE_PID {process.pid}")
        http_ready = server_waiter(process, port)
        if http_ready:
            logger("HTTP_READY")
        else:
            failure_reason = "HTTP_NOT_READY"
    except Exception as error:
        failure_reason = error.__class__.__name__
    finally:
        logger("CLEANUP_START")
        if process is not None:
            try:
                service_stopped = server_stopper(
                    process,
                    terminate_timeout=SMOKE_SERVER_STOP_TIMEOUT_SECONDS,
                    kill_timeout=SMOKE_SERVER_KILL_TIMEOUT_SECONDS,
                )
            except Exception:
                service_stopped = False
            if service_stopped:
                logger("SERVICE_STOPPED")
            else:
                cleanup_ok = False
                failure_reason = failure_reason or "SERVICE_STOP_TIMEOUT"

        if port is not None:
            try:
                port_released = port_waiter(
                    port,
                    timeout=SMOKE_PORT_RELEASE_TIMEOUT_SECONDS,
                )
            except Exception:
                port_released = False
            if port_released:
                logger("PORT_RELEASED")
            else:
                cleanup_ok = False
                failure_reason = failure_reason or "PORT_NOT_RELEASED"

        if process is not None and service_stopped:
            try:
                process.close()
            except Exception:
                cleanup_ok = False
                failure_reason = failure_reason or "PROCESS_HANDLE_CLOSE_FAILED"

    if http_ready and service_stopped and port_released and cleanup_ok:
        logger("SMOKE_SUCCESS")
        return 0
    logger(f"SMOKE_FAILURE {failure_reason or 'UNKNOWN'}")
    return 1


def isolated_browser_is_active(result: BrowserLaunchResult) -> bool:
    """Return whether the browser process tree launched by QuantLab is still active."""
    if result.plan is None:
        return True
    if result.process_job is not None:
        try:
            return result.process_job.active_process_count() > 0
        except OSError:
            logging.warning("Reading the isolated browser Job Object failed.")
    return result.process is not None and result.process.poll() is None


def run_desktop_session(
    server_process: multiprocessing.Process,
    port: int,
    *,
    server_waiter: Callable[[multiprocessing.Process, int], bool] = wait_for_server,
    browser_opener: Callable[[str], BrowserLaunchResult] = open_quantlab_browser,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run the local service without presenting a second desktop control surface."""
    browser_result: BrowserLaunchResult | None = None
    try:
        if not server_waiter(server_process, port):
            logging.error("QuantLab local service did not become healthy.")
            return

        browser_result = browser_opener(f"http://localhost:{port}/")
        while server_process.is_alive() and isolated_browser_is_active(browser_result):
            sleep(BROWSER_MONITOR_INTERVAL_SECONDS)
    finally:
        if browser_result is not None:
            terminate_browser_process_tree(
                browser_result.process,
                browser_result.process_job,
            )
        stop_server(server_process)
        if not wait_for_port_release(port):
            logging.warning("Local FastAPI port was not released before timeout.")


def main() -> None:
    multiprocessing.freeze_support()
    configure_logging()
    if "--smoke-test" in sys.argv:
        try:
            smoke_port = int(os.environ.get("QUANTLAB_PORT", DEFAULT_PORT))
            apply_network_plan_environment(
                DesktopNetworkPlan("DESKTOP", "127.0.0.1", None),
                smoke_port,
            )
            status = run_smoke_test(preferred_port=smoke_port)
        finally:
            logging.shutdown()
        raise SystemExit(status)

    instance_guard: SingleInstanceGuard | None = None
    process: multiprocessing.Process | None = None
    try:
        instance_guard = acquire_single_instance_guard()
        if instance_guard is None:
            show_second_instance_message()
            return
        port = choose_port(int(os.environ.get("QUANTLAB_PORT", DEFAULT_PORT)))
        network_plan = select_desktop_network_plan(
            port,
            lan_enabled=load_lan_access_setting(),
        )
        apply_network_plan_environment(network_plan, port)
        frontend_directory = resolve_frontend_directory()
        process = start_server(port, frontend_directory)
        run_desktop_session(process, port)
    finally:
        if process is not None:
            stop_server(process)
        if instance_guard is not None:
            instance_guard.close()
        logging.shutdown()


if __name__ == "__main__":
    main()
