from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.application.errors import QuantLabApplicationError
from quant_lab.data import validate_standardized_prices
from quant_lab.fingerprint import calculate_market_data_sha256
from quant_lab.market.hk.models import BoardLotConfig, HKSymbol
from quant_lab.models import MarketDataMetadata, MarketDataResult
from quant_lab.providers.base import MarketDataProvider, ProviderMetadata, SymbolMetadata
from quant_lab.storage.sqlite import quantlab_local_data_directory


class CachedMarketDataProvider:
    """Disk-cache decorator; cached prices remain provider-neutral market facts."""

    def __init__(self, provider: MarketDataProvider, cache_directory: Path | None = None) -> None:
        self.provider = provider
        self.cache_directory = cache_directory or quantlab_local_data_directory() / "data"
        self._last_cache_hits: dict[str, bool] = {}

    def _cache_stem(
        self,
        symbol: HKSymbol,
        start_date: date,
        end_date: date,
        longest_lookback: int,
    ) -> str:
        metadata = self.provider.get_provider_metadata()
        payload = {
            "adjustment_policy": metadata.adjustment_policy,
            "end_date": end_date.isoformat(),
            "longest_lookback": longest_lookback,
            "provider": metadata.name,
            "provider_version": metadata.version,
            "start_date": start_date.isoformat(),
            "symbol": symbol.normalized_symbol,
        }
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _paths(self, stem: str) -> tuple[Path, Path]:
        return self.cache_directory / f"{stem}.csv", self.cache_directory / f"{stem}.json"

    @staticmethod
    def _metadata_payload(metadata: MarketDataMetadata) -> dict[str, Any]:
        values = asdict(metadata)
        for key, value in tuple(values.items()):
            if isinstance(value, (date, datetime)):
                values[key] = value.isoformat()
        return values

    @staticmethod
    def _restore_metadata(values: dict[str, Any]) -> MarketDataMetadata:
        return MarketDataMetadata(
            symbol=str(values["symbol"]),
            source=str(values["source"]),
            source_version=str(values["source_version"]),
            fetched_at_utc=datetime.fromisoformat(str(values["fetched_at_utc"])),
            requested_start_date=date.fromisoformat(str(values["requested_start_date"])),
            requested_end_date=date.fromisoformat(str(values["requested_end_date"])),
            actual_start_date=date.fromisoformat(str(values["actual_start_date"])),
            actual_end_date=date.fromisoformat(str(values["actual_end_date"])),
            analysis_start_date=date.fromisoformat(str(values["analysis_start_date"])),
            analysis_end_date=date.fromisoformat(str(values["analysis_end_date"])),
            longest_lookback=int(values["longest_lookback"]),
            warmup_row_count=int(values["warmup_row_count"]),
            analysis_row_count=int(values["analysis_row_count"]),
            total_row_count=int(values["total_row_count"]),
            adjustment_method=str(values["adjustment_method"]),
            data_sha256=str(values["data_sha256"]),
        )

    def _read(self, prices_path: Path, metadata_path: Path) -> MarketDataResult:
        try:
            values = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata = self._restore_metadata(values)
            # Cache files are written with enough digits to round-trip binary floats.
            # Pandas' default parser can still move a value across the fingerprint's
            # decimal boundary, so the matching round-trip parser is required here.
            prices = pd.read_csv(prices_path, float_precision="round_trip")
            prices["date"] = [date.fromisoformat(str(value)) for value in prices["date"]]
            validate_standardized_prices(
                prices,
                start_date=metadata.requested_start_date,
                end_date=metadata.requested_end_date,
                longest_lookback=metadata.longest_lookback,
            )
            fingerprint = calculate_market_data_sha256(prices)
            if fingerprint != metadata.data_sha256:
                raise ValueError("cached data fingerprint does not match metadata")
            return MarketDataResult(prices=prices, metadata=metadata)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise QuantLabApplicationError(
                "CACHE_ERROR",
                "本地行情缓存无法读取，请明确选择重新获取行情。",
            ) from exc

    def _write(self, prices_path: Path, metadata_path: Path, result: MarketDataResult) -> None:
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        prices_temp = prices_path.with_suffix(".csv.tmp")
        metadata_temp = metadata_path.with_suffix(".json.tmp")
        frame = result.prices.copy()
        frame["date"] = [value.isoformat() for value in frame["date"]]
        try:
            frame.to_csv(
                prices_temp,
                index=False,
                encoding="utf-8",
                lineterminator="\n",
                float_format="%.17g",
            )
            metadata_temp.write_text(
                json.dumps(
                    self._metadata_payload(result.metadata),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            prices_temp.replace(prices_path)
            metadata_temp.replace(metadata_path)
        except OSError as exc:
            raise QuantLabApplicationError("CACHE_ERROR", "本地行情缓存无法写入。") from exc
        finally:
            prices_temp.unlink(missing_ok=True)
            metadata_temp.unlink(missing_ok=True)

    def get_daily_prices(
        self,
        symbol: HKSymbol,
        start_date: date,
        end_date: date,
        longest_lookback: int,
        *,
        fetched_at_utc: datetime | None = None,
        force_refresh: bool = False,
    ) -> MarketDataResult:
        stem = self._cache_stem(symbol, start_date, end_date, longest_lookback)
        prices_path, metadata_path = self._paths(stem)
        if not force_refresh and prices_path.is_file() and metadata_path.is_file():
            self._last_cache_hits[symbol.normalized_symbol] = True
            return self._read(prices_path, metadata_path)
        result = self.provider.get_daily_prices(
            symbol,
            start_date,
            end_date,
            longest_lookback,
            fetched_at_utc=fetched_at_utc,
            force_refresh=force_refresh,
        )
        self._write(prices_path, metadata_path, result)
        self._last_cache_hits[symbol.normalized_symbol] = False
        return result

    def was_cache_hit(self, symbol: HKSymbol) -> bool:
        return self._last_cache_hits.get(symbol.normalized_symbol, False)

    def get_symbol_metadata(self, symbol: HKSymbol) -> SymbolMetadata:
        return self.provider.get_symbol_metadata(symbol)

    def get_board_lot(self, symbol: HKSymbol) -> BoardLotConfig | None:
        return self.provider.get_board_lot(symbol)

    def get_provider_metadata(self) -> ProviderMetadata:
        return self.provider.get_provider_metadata()
