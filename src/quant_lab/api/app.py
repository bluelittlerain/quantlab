from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from quant_lab.__about__ import __version__
from quant_lab.api.schemas import (
    BacktestRequestModel,
    BacktestResponseModel,
    ErrorBody,
    ErrorResponse,
    ExportPreparationView,
    PairingInput,
    PresetInput,
    PresetView,
    RuntimeView,
    SettingsInput,
    SymbolResponse,
)
from quant_lab.api.security import (
    SESSION_COOKIE_NAME,
    SESSION_HEADER_NAME,
    LANPairingSession,
    is_loopback_client,
)
from quant_lab.api.static import SPAStaticFiles
from quant_lab.application.errors import QuantLabApplicationError
from quant_lab.application.hk_exports import build_hk_export_bundle
from quant_lab.application.hk_workflow import HKRunRequest
from quant_lab.application.service import BacktestApplicationService
from quant_lab.config import DeploymentMode, RuntimeConfig
from quant_lab.market.hk.models import BoardLotConfig, BoardLotSource, HKTradingCostConfig
from quant_lab.market.hk.symbols import normalize_hk_symbol
from quant_lab.providers.base import MarketDataProvider
from quant_lab.providers.cache import CachedMarketDataProvider
from quant_lab.providers.yahoo_hk import YahooHKProvider
from quant_lab.storage.repositories import QuantLabRepository
from quant_lab.storage.sqlite import DatabaseUnavailableError, SQLiteRepository


def _error(
    status: int,
    code: str,
    message: str,
    field: str | None = None,
    details: dict[str, Any] | None = None,
):
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error=ErrorBody(code=code, message=message, field=field, details=details)
        ).model_dump(),
    )


_FIELD_ERROR_METADATA: dict[str, tuple[str, str]] = {
    "symbol": ("INVALID_SYMBOL", "请输入有效的港股代码，例如 0700.HK。"),
    "benchmark_symbol": ("INVALID_BENCHMARK", "请输入有效的港股比较基准，例如 2800.HK。"),
    "start_date": ("INVALID_DATE_RANGE", "请选择有效的开始日期。"),
    "end_date": ("INVALID_DATE_RANGE", "结束日期必须晚于或等于开始日期。"),
    "short_window": ("INVALID_SMA_WINDOWS", "短均线必须是正整数并小于长均线。"),
    "long_window": ("INVALID_SMA_WINDOWS", "长均线必须大于短均线。"),
    "initial_capital": ("INVALID_INITIAL_CAPITAL", "初始资金必须大于零。"),
    "board_lot": ("INVALID_BOARD_LOT", "请确认标的的每手股数。"),
    "benchmark_board_lot": ("INVALID_BOARD_LOT", "请确认比较基准的每手股数。"),
}


def _validation_error(exc: RequestValidationError) -> tuple[str, str, str | None, dict[str, Any]]:
    normalized: list[dict[str, str]] = []
    first_field: str | None = None
    first_message: str | None = None
    first_code = "INVALID_REQUEST"
    for error in exc.errors():
        location = [str(item) for item in error.get("loc", ()) if str(item) != "body"]
        message = str(error.get("msg", "输入值无效。"))
        field = location[0] if location else None
        if not location:
            if "短均线" in message:
                field = "long_window"
            elif "结束日期" in message:
                field = "end_date"
            elif "每手股数" in message:
                field = "board_lot"
        if field in {"costs", "benchmark_costs"}:
            field = ".".join(location[:2])
            code, friendly = "INVALID_COST_RATE", "交易成本必须是有效的非负数。"
        else:
            code, friendly = _FIELD_ERROR_METADATA.get(
                field or "", ("INVALID_REQUEST", "请检查标红的输入项。")
            )
        normalized.append(
            {
                "field": field or "request",
                "message": friendly,
                "type": str(error.get("type", "validation_error")),
            }
        )
        if first_message is None:
            first_field = field
            first_message = friendly
            first_code = code
    return (
        first_code,
        first_message or "请检查输入参数。",
        first_field,
        {"errors": normalized},
    )


def _costs(model: Any) -> HKTradingCostConfig:
    return HKTradingCostConfig(**model.model_dump())


def _request(model: BacktestRequestModel) -> HKRunRequest:
    now = datetime.now(timezone.utc)
    return HKRunRequest(
        symbol=model.symbol,
        benchmark_symbol=model.benchmark_symbol,
        start_date=model.start_date,
        end_date=model.end_date,
        short_window=model.short_window,
        long_window=model.long_window,
        initial_capital=model.initial_capital,
        board_lot=BoardLotConfig(
            lot_size=model.board_lot.lot_size,
            source=BoardLotSource.USER,
            verified_at=now,
            confirmed=model.board_lot.confirmed,
        ),
        benchmark_board_lot=BoardLotConfig(
            lot_size=model.benchmark_board_lot.lot_size,
            source=BoardLotSource.USER,
            verified_at=now,
            confirmed=model.benchmark_board_lot.confirmed,
        ),
        costs=_costs(model.costs),
        benchmark_costs=_costs(model.benchmark_costs),
    )


def create_app(
    *,
    provider: MarketDataProvider | None = None,
    repository: QuantLabRepository | None = None,
    database_path: Path | None = None,
    frontend_directory: Path | None = None,
    runtime_config: RuntimeConfig | None = None,
    pairing_session: LANPairingSession | None = None,
) -> FastAPI:
    runtime = runtime_config or RuntimeConfig.from_environment()
    app = FastAPI(
        title="QuantLab HK API",
        version=__version__,
        description="港股日线研究与回测本地 API",
    )
    if runtime.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(runtime.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", SESSION_HEADER_NAME],
        )
    cache_directory = runtime.data_directory / "data" if runtime.data_directory else None
    app.state.provider = provider or CachedMarketDataProvider(
        YahooHKProvider(), cache_directory=cache_directory
    )
    app.state.repository = repository
    app.state.database_path = database_path or (
        runtime.data_directory / "quantlab.db" if runtime.data_directory else None
    )
    app.state.export_cache = {}
    app.state.application_service = None
    app.state.runtime_config = runtime
    app.state.pairing_session = (
        pairing_session or LANPairingSession() if runtime.mode is DeploymentMode.LAN else None
    )

    def authenticated(request: Request) -> bool:
        if runtime.mode is not DeploymentMode.LAN:
            return True
        if is_loopback_client(request.client.host if request.client else None):
            return True
        session = app.state.pairing_session
        token = request.headers.get(SESSION_HEADER_NAME) or request.cookies.get(SESSION_COOKIE_NAME)
        return bool(session and session.accepts(token))

    @app.middleware("http")
    async def protect_lan_api(request: Request, call_next):
        if runtime.mode is not DeploymentMode.LAN or not request.url.path.startswith("/api/"):
            return await call_next(request)
        public_paths = {
            "/api/health",
            "/api/health/live",
            "/api/health/ready",
            "/api/runtime",
            "/api/session/pair",
        }
        if request.url.path not in public_paths and not authenticated(request):
            return _error(
                401,
                "PAIRING_REQUIRED",
                "请输入桌面端显示的 6 位配对码。",
                "pairing_code",
            )
        return await call_next(request)

    def local_repository() -> QuantLabRepository:
        if app.state.repository is None:
            app.state.repository = SQLiteRepository(app.state.database_path)
        return app.state.repository

    def application_service() -> BacktestApplicationService:
        if app.state.application_service is None:
            app.state.application_service = BacktestApplicationService(
                provider=app.state.provider,
                repository=local_repository(),
            )
        return app.state.application_service

    @app.exception_handler(QuantLabApplicationError)
    async def application_error(_request: Request, exc: QuantLabApplicationError):
        status = (
            422 if exc.code.startswith("INVALID") or exc.code == "INSUFFICIENT_CAPITAL" else 502
        )
        if exc.code == "CACHE_ERROR":
            status = 503
        return _error(status, exc.code, exc.message, exc.field, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        code, message, field, details = _validation_error(exc)
        return _error(422, code, message, field, details)

    @app.exception_handler(DatabaseUnavailableError)
    async def database_error(_request: Request, exc: DatabaseUnavailableError):
        return _error(503, "CACHE_ERROR", str(exc))

    @app.exception_handler(sqlite3.IntegrityError)
    async def sqlite_conflict(_request: Request, _exc: sqlite3.IntegrityError):
        return _error(409, "PRESET_CONFLICT", "预设名称已存在。")

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        code = str(exc.detail)
        messages = {
            "INVALID_SYMBOL": "港股代码无效。",
            "RUN_NOT_FOUND": "找不到该回测运行。",
        }
        return _error(exc.status_code, code, messages.get(code, "请求无法完成。"))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__, "market": "HKEX"}

    @app.get("/api/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "live", "version": __version__}

    @app.get("/api/health/ready")
    def health_ready() -> dict[str, str]:
        if not local_repository().check_ready():
            raise DatabaseUnavailableError("本地数据存储暂时不可用。")
        return {"status": "ready", "database": "ok", "version": __version__}

    @app.get("/api/runtime", response_model=RuntimeView)
    def runtime_info(request: Request) -> dict[str, Any]:
        local = is_loopback_client(request.client.host if request.client else None)
        session = app.state.pairing_session
        return {
            "mode": runtime.mode.value,
            "authenticated": authenticated(request),
            "pairing_required": runtime.mode is DeploymentMode.LAN,
            "lan_url": runtime.lan_url if local else None,
            "pairing_code": session.pairing_code if local and session else None,
        }

    @app.post("/api/session/pair")
    def pair_lan_session(model: PairingInput) -> JSONResponse:
        session = app.state.pairing_session
        if runtime.mode is not DeploymentMode.LAN or session is None:
            return _error(409, "PAIRING_UNAVAILABLE", "当前未启用局域网访问。")
        token = session.pair(model.code)
        if token is None:
            return _error(
                401, "INVALID_PAIRING_CODE", "配对码不正确，请查看桌面端后重试。", "pairing_code"
            )
        response = JSONResponse({"paired": True})
        response.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/symbols/{symbol}", response_model=SymbolResponse)
    def symbol_metadata(symbol: str) -> dict[str, Any]:
        try:
            normalized = normalize_hk_symbol(symbol)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="INVALID_SYMBOL") from exc
        metadata = app.state.provider.get_symbol_metadata(normalized)
        board_lot = app.state.provider.get_board_lot(normalized)
        if board_lot is None:
            stored = (
                local_repository()
                .get_settings()
                .get("board_lots", {})
                .get(normalized.normalized_symbol)
            )
            if isinstance(stored, dict) and isinstance(stored.get("lot_size"), int):
                board_lot = BoardLotConfig(
                    lot_size=stored["lot_size"],
                    source=BoardLotSource.USER,
                    verified_at=datetime.fromisoformat(stored["verified_at"]),
                    confirmed=True,
                )
        return {
            "symbol": asdict(metadata.symbol),
            "board_lot": asdict(board_lot) if board_lot else None,
            "board_lot_requires_confirmation": board_lot is None,
            "provider": app.state.provider.get_provider_metadata().name,
        }

    def execute_backtest(
        model: BacktestRequestModel, *, force_refresh: bool = False
    ) -> dict[str, Any]:
        return application_service().execute(_request(model), force_refresh=force_refresh)

    @app.post("/api/backtests", response_model=BacktestResponseModel)
    def run_backtest(model: BacktestRequestModel) -> dict[str, Any]:
        return execute_backtest(model)

    @app.post("/api/market-data/refresh", response_model=BacktestResponseModel)
    def refresh_market_data(model: BacktestRequestModel) -> dict[str, Any]:
        return execute_backtest(model, force_refresh=True)

    @app.get("/api/backtests/{run_id}", response_model=BacktestResponseModel)
    def get_backtest(run_id: str) -> dict[str, Any]:
        result = local_repository().get_run(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
        return result

    @app.get("/api/history")
    def history() -> list[dict[str, Any]]:
        return local_repository().list_history()

    @app.delete("/api/history/{run_id}")
    def delete_history(run_id: str) -> dict[str, bool]:
        app.state.export_cache.pop(run_id, None)
        return {"deleted": local_repository().delete_run(run_id)}

    @app.get("/api/settings")
    def settings() -> dict[str, Any]:
        return local_repository().get_settings()

    @app.put("/api/settings")
    def put_settings(model: SettingsInput) -> dict[str, Any]:
        return local_repository().put_settings(model.model_dump(exclude_none=True))

    @app.get("/api/presets", response_model=list[PresetView])
    def presets() -> list[dict[str, Any]]:
        return [
            {
                "id": item.preset_id,
                "name": item.name,
                "payload": item.payload,
                "updated_at": item.updated_at,
            }
            for item in local_repository().list_presets()
        ]

    @app.post("/api/presets", response_model=PresetView, status_code=201)
    def create_preset(model: PresetInput) -> dict[str, Any]:
        item = local_repository().create_preset(model.name, model.payload)
        return {
            "id": item.preset_id,
            "name": item.name,
            "payload": item.payload,
            "updated_at": item.updated_at,
        }

    @app.put("/api/presets/{preset_id}")
    def update_preset(preset_id: int, model: PresetInput) -> dict[str, bool]:
        return {"updated": local_repository().update_preset(preset_id, model.name, model.payload)}

    @app.delete("/api/presets/{preset_id}")
    def delete_preset(preset_id: int) -> dict[str, bool]:
        return {"deleted": local_repository().delete_preset(preset_id)}

    @app.get("/api/recent-symbols")
    def recent_symbols() -> list[str]:
        return local_repository().recent_symbols()

    def prepared_export(run_id: str):
        cached = app.state.export_cache.get(run_id)
        if cached is not None:
            return cached
        result = local_repository().get_run(run_id)
        if result is None:
            raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
        bundle = build_hk_export_bundle(result)
        app.state.export_cache[run_id] = bundle
        return bundle

    @app.post("/api/exports/{run_id}/prepare", response_model=ExportPreparationView)
    def prepare_export(run_id: str) -> dict[str, Any]:
        bundle = prepared_export(run_id)
        result = local_repository().get_run(run_id)
        return {
            "run_id": run_id,
            "generated_at_utc": result["created_at_utc"],
            "files": {
                "report.html": len(bundle.report_html),
                "trades.csv": len(bundle.trades_csv),
                "manifest.json": len(bundle.manifest_json),
                "bundle.zip": len(bundle.bundle_zip),
            },
        }

    @app.get("/api/exports/{run_id}/{artifact}")
    def export_run(run_id: str, artifact: str) -> Response:
        bundle = prepared_export(run_id)
        payloads = {
            "report.html": (bundle.report_html, "text/html; charset=utf-8", "report.html"),
            "trades.csv": (bundle.trades_csv, "text/csv; charset=utf-8", "trades.csv"),
            "manifest.json": (
                bundle.manifest_json,
                "application/json; charset=utf-8",
                "manifest.json",
            ),
            "bundle.zip": (bundle.bundle_zip, "application/zip", "QuantLab-HK-result.zip"),
        }
        if artifact not in payloads:
            raise HTTPException(status_code=404, detail="EXPORT_NOT_FOUND")
        payload, media_type, filename = payloads[artifact]
        return Response(
            content=payload,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    if frontend_directory is not None:
        resolved_frontend = frontend_directory.resolve()
        if not (resolved_frontend / "index.html").is_file():
            raise RuntimeError("Frontend assets are incomplete: index.html is missing.")
        app.mount(
            "/",
            SPAStaticFiles(directory=resolved_frontend, html=True, check_dir=True),
            name="frontend",
        )

    return app


app = create_app()
