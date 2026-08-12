from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class DatabaseUnavailableError(RuntimeError):
    pass


def quantlab_local_data_directory() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "QuantLab"
    return Path.home() / "AppData" / "Local" / "QuantLab"


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    symbol: str
    benchmark: str
    created_at: str
    summary: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class StoredPreset:
    preset_id: int
    name: str
    payload: dict[str, Any]
    updated_at: str


class SQLiteRepository:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or quantlab_local_data_directory() / "quantlab.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            return connection
        except sqlite3.DatabaseError as exc:
            raise DatabaseUnavailableError("本地历史数据库无法读取，可以备份后重建。") from exc

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        try:
            with self._connection() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS schema_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        benchmark TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        summary_json TEXT NOT NULL,
                        result_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS presets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        payload_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS recent_symbols (
                        symbol TEXT PRIMARY KEY,
                        used_at TEXT NOT NULL
                    );
                    """
                )
                row = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?)",
                        (str(SCHEMA_VERSION),),
                    )
                elif int(row["value"]) != SCHEMA_VERSION:
                    raise DatabaseUnavailableError("本地数据库版本暂不受支持。")
        except sqlite3.DatabaseError as exc:
            raise DatabaseUnavailableError("本地历史数据库无法读取，可以备份后重建。") from exc

    def check_ready(self) -> bool:
        try:
            with self._connection() as connection:
                row = connection.execute("SELECT 1 AS ready").fetchone()
            return bool(row and row["ready"] == 1)
        except sqlite3.DatabaseError as exc:
            raise DatabaseUnavailableError("本地历史数据库暂时不可用。") from exc

    def save_run(self, result: dict[str, Any]) -> None:
        summary = {
            "run_id": result["run_id"],
            "symbol": result["symbol"]["normalized_symbol"],
            "benchmark": result["benchmark"]["normalized_symbol"],
            "created_at": result["created_at_utc"],
            "date_range": result["date_range"],
            "strategy_metrics": result["strategy_metrics"],
            "benchmark_metrics": result["benchmark_metrics"],
            "trade_count": len(result["trades"]),
        }
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO runs(run_id, symbol, benchmark, created_at, summary_json, result_json)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    created_at=excluded.created_at,
                    summary_json=excluded.summary_json,
                    result_json=excluded.result_json
                """,
                (
                    result["run_id"],
                    result["symbol"]["normalized_symbol"],
                    result["benchmark"]["normalized_symbol"],
                    result["created_at_utc"],
                    json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            connection.execute(
                """
                INSERT INTO recent_symbols(symbol, used_at) VALUES(?, ?)
                ON CONFLICT(symbol) DO UPDATE SET used_at=excluded.used_at
                """,
                (result["symbol"]["normalized_symbol"], result["created_at_utc"]),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def list_history(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT summary_json FROM runs ORDER BY created_at DESC"
            ).fetchall()
        return [json.loads(row["summary_json"]) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        return cursor.rowcount > 0

    def get_settings(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute("SELECT key, value_json FROM settings").fetchall()
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    def put_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        with self._connection() as connection:
            for key, value in settings.items():
                connection.execute(
                    """
                    INSERT INTO settings(key, value_json) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json
                    """,
                    (key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))),
                )
        return self.get_settings()

    def list_presets(self) -> list[StoredPreset]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id, name, payload_json, updated_at FROM presets ORDER BY name"
            ).fetchall()
        return [
            StoredPreset(
                preset_id=row["id"],
                name=row["name"],
                payload=json.loads(row["payload_json"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def create_preset(self, name: str, payload: dict[str, Any]) -> StoredPreset:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO presets(name, payload_json, updated_at) VALUES(?, ?, ?)",
                (
                    name,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    updated_at,
                ),
            )
        return StoredPreset(int(cursor.lastrowid), name, payload, updated_at)

    def update_preset(self, preset_id: int, name: str, payload: dict[str, Any]) -> bool:
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE presets SET name = ?, payload_json = ?, updated_at = ? WHERE id = ?",
                (
                    name,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    updated_at,
                    preset_id,
                ),
            )
        return cursor.rowcount > 0

    def delete_preset(self, preset_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
        return cursor.rowcount > 0

    def recent_symbols(self, limit: int = 5) -> list[str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT symbol FROM recent_symbols ORDER BY used_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [str(row["symbol"]) for row in rows]
