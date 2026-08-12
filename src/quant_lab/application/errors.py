from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(eq=False)
class QuantLabApplicationError(Exception):
    code: str
    message: str
    field: str | None = None
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
