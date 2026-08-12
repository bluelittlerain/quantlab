from __future__ import annotations

from pathlib import Path

from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    """Serve a Vite build with deterministic cache policy and safe SPA fallback."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._should_fallback(path, scope):
                raise
            response = await super().get_response("index.html", scope)

        if response.status_code == 404 and self._should_fallback(path, scope):
            response = await super().get_response("index.html", scope)
        response_path = Path(str(getattr(response, "path", "")))
        is_vite_asset = "assets" in response_path.parts
        if is_vite_asset and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @staticmethod
    def _should_fallback(path: str, scope: Scope) -> bool:
        request_path = str(scope.get("path", "")).lstrip("/")
        return (
            scope.get("method") in {"GET", "HEAD"}
            and not path.startswith("api/")
            and not request_path.startswith("api/")
            and "." not in Path(path).name
        )
