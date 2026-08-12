from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class PresetRecord(Protocol):
    preset_id: int
    name: str
    payload: dict[str, Any]
    updated_at: str


class RunHistoryRepository(Protocol):
    def save_run(self, result: dict[str, Any]) -> None: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def list_history(self) -> list[dict[str, Any]]: ...

    def delete_run(self, run_id: str) -> bool: ...

    def recent_symbols(self, limit: int = 5) -> list[str]: ...


class PresetRepository(Protocol):
    def list_presets(self) -> list[PresetRecord]: ...

    def create_preset(self, name: str, payload: dict[str, Any]) -> PresetRecord: ...

    def update_preset(self, preset_id: int, name: str, payload: dict[str, Any]) -> bool: ...

    def delete_preset(self, preset_id: int) -> bool: ...


class SettingsRepository(Protocol):
    def get_settings(self) -> dict[str, Any]: ...

    def put_settings(self, settings: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class QuantLabRepository(RunHistoryRepository, PresetRepository, SettingsRepository, Protocol):
    def check_ready(self) -> bool: ...
