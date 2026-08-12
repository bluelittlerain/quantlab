from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from quant_lab.api.app import create_app
from quant_lab.config import RuntimeConfig


def main() -> None:
    runtime = RuntimeConfig.from_environment()
    frontend_value = os.environ.get("QUANTLAB_FRONTEND_DIR")
    frontend_directory = Path(frontend_value) if frontend_value else None
    log_level = os.environ.get("QUANTLAB_LOG_LEVEL", "INFO").lower()
    app = create_app(frontend_directory=frontend_directory, runtime_config=runtime)
    uvicorn.run(
        app,
        host=runtime.host,
        port=runtime.port,
        access_log=False,
        log_level=log_level,
        server_header=False,
    )


if __name__ == "__main__":
    main()
