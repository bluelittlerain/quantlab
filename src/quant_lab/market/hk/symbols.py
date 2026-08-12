from __future__ import annotations

import re

from quant_lab.market.hk.models import HKSymbol

_HK_INPUT = re.compile(r"^(?P<digits>\d{1,5})(?:\.HK)?$", re.IGNORECASE)


def normalize_hk_symbol(value: str, *, local_alias: str | None = None) -> HKSymbol:
    """Normalize an explicit HKEX ticker without guessing another market."""
    if not isinstance(value, str):
        raise TypeError("symbol must be a string.")
    candidate = value.strip().upper()
    match = _HK_INPUT.fullmatch(candidate)
    if match is None:
        raise ValueError("INVALID_SYMBOL: use 700, 0700, or 0700.HK.")
    digits = match.group("digits")
    if len(digits) > 4:
        raise ValueError("INVALID_SYMBOL: HKEX ticker must contain at most four digits.")
    normalized = f"{int(digits):04d}.HK"
    return HKSymbol(normalized_symbol=normalized, local_alias=local_alias)
