from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe

CACHE_VERSION = 1


@dataclass(frozen=True, slots=True)
class CandleHistoryCache:
    root: Path

    def load(self, *, symbol: str, timeframe: Timeframe) -> list[Candle]:
        path = self.path_for(symbol=symbol, timeframe=timeframe)
        if not path.exists():
            return []

        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid candle cache payload: {path}")

        if payload.get("version") != CACHE_VERSION:
            raise ValueError(f"Unsupported candle cache version: {path}")

        if payload.get("symbol") != symbol:
            raise ValueError(f"Candle cache symbol mismatch: {path}")

        if payload.get("timeframe") != timeframe.value:
            raise ValueError(f"Candle cache timeframe mismatch: {path}")

        raw_candles = payload.get("candles")
        if not isinstance(raw_candles, list):
            raise ValueError(f"Invalid candle cache rows: {path}")

        candles = [
            _deserialize_candle(
                row,
                symbol=symbol,
                timeframe=timeframe,
            )
            for row in raw_candles
        ]

        return merge_candle_history(candles)

    def save(
        self,
        *,
        symbol: str,
        timeframe: Timeframe,
        candles: Sequence[Candle],
    ) -> Path:
        normalized = merge_candle_history(candles)
        _validate_candles(
            symbol=symbol,
            timeframe=timeframe,
            candles=normalized,
        )

        path = self.path_for(symbol=symbol, timeframe=timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": CACHE_VERSION,
            "symbol": symbol,
            "timeframe": timeframe.value,
            "candles": [_serialize_candle(candle) for candle in normalized],
        }

        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary_path.replace(path)
        return path

    def path_for(self, *, symbol: str, timeframe: Timeframe) -> Path:
        safe_symbol = "".join(
            character if character.isalnum() else "_"
            for character in symbol.upper()
        ).strip("_")
        if not safe_symbol:
            raise ValueError("symbol cannot be empty")

        return self.root / f"{safe_symbol}_{timeframe.value}.json"


def merge_candle_history(
    *groups: Sequence[Candle],
    max_candles: int | None = None,
) -> list[Candle]:
    if max_candles is not None and max_candles <= 0:
        raise ValueError("max_candles must be positive when provided")

    candles_by_time = {
        candle.opened_at: candle
        for group in groups
        for candle in group
    }
    merged = sorted(
        candles_by_time.values(),
        key=lambda candle: candle.opened_at,
    )

    if max_candles is None:
        return merged

    return merged[-max_candles:]


def _validate_candles(
    *,
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
) -> None:
    if any(
        candle.symbol != symbol or candle.timeframe is not timeframe
        for candle in candles
    ):
        raise ValueError("cache key must match every candle")


def _serialize_candle(candle: Candle) -> dict[str, str]:
    return {
        "opened_at": candle.opened_at.isoformat(),
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
    }


def _deserialize_candle(
    row: Any,
    *,
    symbol: str,
    timeframe: Timeframe,
) -> Candle:
    if not isinstance(row, dict):
        raise ValueError("Invalid candle cache row")

    try:
        opened_at = datetime.fromisoformat(_read_str(row, "opened_at"))
        open_price = Decimal(_read_str(row, "open"))
        high_price = Decimal(_read_str(row, "high"))
        low_price = Decimal(_read_str(row, "low"))
        close_price = Decimal(_read_str(row, "close"))
        volume = Decimal(_read_str(row, "volume"))
    except (ValueError, ArithmeticError) as exc:
        raise ValueError("Invalid candle cache row values") from exc

    if opened_at.tzinfo is None:
        raise ValueError("Cached opened_at must be timezone-aware")

    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        opened_at=opened_at,
        closed_at=opened_at + timeframe.duration,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
    )


def _read_str(row: dict[Any, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Missing or invalid cache field: {key}")
    return value
