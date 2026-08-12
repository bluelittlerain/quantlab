from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


class DeploymentMode(StrEnum):
    DESKTOP = "DESKTOP"
    LAN = "LAN"
    WEB = "WEB"


@dataclass(frozen=True)
class RuntimeConfig:
    mode: DeploymentMode
    host: str
    port: int
    data_directory: Path | None
    lan_url: str | None = None
    cors_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535.")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"Invalid explicit CORS origin: {origin!r}.")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> RuntimeConfig:
        values = os.environ if environment is None else environment
        mode_value = values.get("QUANTLAB_MODE", DeploymentMode.DESKTOP.value).upper()
        try:
            mode = DeploymentMode(mode_value)
        except ValueError as exc:
            raise ValueError("QUANTLAB_MODE must be DESKTOP, LAN, or WEB.") from exc
        default_host = (
            "0.0.0.0" if mode in {DeploymentMode.LAN, DeploymentMode.WEB} else "127.0.0.1"
        )
        host = values.get("QUANTLAB_HOST", default_host)
        port = int(values.get("QUANTLAB_PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError("QUANTLAB_PORT must be between 1 and 65535.")
        data = values.get("QUANTLAB_DATA_DIR")
        origins = tuple(
            item.strip()
            for item in values.get("QUANTLAB_CORS_ORIGINS", "").split(",")
            if item.strip()
        )
        return cls(
            mode=mode,
            host=host,
            port=port,
            data_directory=Path(data) if data else None,
            lan_url=values.get("QUANTLAB_LAN_URL") or None,
            cors_origins=origins,
        )
