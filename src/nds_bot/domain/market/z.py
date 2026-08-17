from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from os import getenv

from nds_bot.domain.market.candle import Candle

DEFAULT_Z_REFERENCE_LOOKBACK_BARS = 200


def _non_negative_env_int(name: str, default: int) -> int:
    value = getenv(name)
    parsed = int(value) if value else default

    if parsed < 0:
        raise RuntimeError(f"{name} must be zero or greater")

    return parsed


DEFAULT_Z_BARS_AFTER = _non_negative_env_int("Z_BARS_AFTER", 200)


class ZSelectionMode(StrEnum):
    AUTO = "auto"
    MANUAL_TIME = "manual_time"


@dataclass(frozen=True, slots=True)
class ZAnchor:
    bar_index: int
    time: datetime
    price: Decimal
    reference_index: int | None
    reference_high: Decimal
    left_boundary_index: int | None
    all_time_high_mode: bool


@dataclass(frozen=True, slots=True)
class ZCalculationWindow:
    """Closed candles available after Z for downstream calculations.

    Z itself is intentionally not counted. With bars_after_z=200, the window
    contains at most Z+1 through Z+200. With bars_after_z=0, the window contains
    every supplied closed candle after Z through the latest available candle.
    """

    z_anchor: ZAnchor
    candles: tuple[Candle, ...]
    first_bar_index: int | None
    last_bar_index: int | None
    requested_bars_after_z: int

    @property
    def available_bars(self) -> int:
        return len(self.candles)

    @property
    def complete(self) -> bool:
        if self.requested_bars_after_z == 0:
            return True
        return self.available_bars == self.requested_bars_after_z


def find_bull_reference_high(
    candles: Sequence[Candle],
    *,
    reference_lookback: int = DEFAULT_Z_REFERENCE_LOOKBACK_BARS,
) -> int | None:
    """Return the active Bull reference High index.

    This intentionally mirrors NodeCounterv2:
    - reference is the highest High in the latest N closed candles;
    - when Highs are equal, the newest candle wins;
    - reference_lookback <= 0 means the whole supplied history.
    """
    if not candles:
        return None

    first_reference_bar = 0
    if reference_lookback > 0:
        first_reference_bar = max(0, len(candles) - reference_lookback)

    reference_index = first_reference_bar
    reference_high = candles[reference_index].high

    for index in range(first_reference_bar + 1, len(candles)):
        if candles[index].high >= reference_high:
            reference_high = candles[index].high
            reference_index = index

    return reference_index


def find_bull_z_anchor(
    candles: Sequence[Candle],
    *,
    reference_lookback: int = DEFAULT_Z_REFERENCE_LOOKBACK_BARS,
) -> ZAnchor | None:
    """Find Bull Z with the same selection contract as NodeCounterv2.

    The input must contain chronological, closed candles only.
    """
    if len(candles) < 2:
        return None

    reference_index = find_bull_reference_high(
        candles,
        reference_lookback=reference_lookback,
    )
    if reference_index is None:
        return None

    reference_high = candles[reference_index].high

    left_boundary_index: int | None = None
    for index in range(reference_index - 1, -1, -1):
        if candles[index].high > reference_high:
            left_boundary_index = index
            break

    if left_boundary_index is None:
        search_start = 0
        all_time_high_mode = True
    else:
        search_start = left_boundary_index + 1
        all_time_high_mode = False

    z_index = search_start
    lowest_low = candles[z_index].low

    for index in range(search_start + 1, reference_index + 1):
        if candles[index].low <= lowest_low:
            lowest_low = candles[index].low
            z_index = index

    return ZAnchor(
        bar_index=z_index,
        time=candles[z_index].opened_at,
        price=candles[z_index].low,
        reference_index=reference_index,
        reference_high=reference_high,
        left_boundary_index=left_boundary_index,
        all_time_high_mode=all_time_high_mode,
    )


def build_z_calculation_window(
    candles: Sequence[Candle],
    z_anchor: ZAnchor,
    *,
    bars_after_z: int = DEFAULT_Z_BARS_AFTER,
) -> ZCalculationWindow:
    if bars_after_z < 0:
        raise ValueError("bars_after_z must be zero or greater")

    if z_anchor.bar_index < 0 or z_anchor.bar_index >= len(candles):
        raise ValueError("Z anchor index is outside the supplied candles")

    anchor_candle = candles[z_anchor.bar_index]
    if anchor_candle.opened_at != z_anchor.time:
        raise ValueError("Z anchor index/time does not match supplied candles")

    first_index = z_anchor.bar_index + 1
    if bars_after_z == 0:
        end_exclusive = len(candles)
    else:
        end_exclusive = min(len(candles), first_index + bars_after_z)
    window_candles = tuple(candles[first_index:end_exclusive])

    if not window_candles:
        first_bar_index: int | None = None
        last_bar_index: int | None = None
    else:
        first_bar_index = first_index
        last_bar_index = end_exclusive - 1

    return ZCalculationWindow(
        z_anchor=z_anchor,
        candles=window_candles,
        first_bar_index=first_bar_index,
        last_bar_index=last_bar_index,
        requested_bars_after_z=bars_after_z,
    )


def find_manual_z_bar_by_time(
    manual_time: datetime,
    candles: Sequence[Candle],
) -> int | None:
    """Mirror NodeCounterv2 manual-time resolution on closed candles."""
    if not candles:
        return None

    if manual_time.tzinfo is None:
        raise ValueError("manual_time must be timezone-aware")

    if manual_time < candles[0].opened_at or manual_time > candles[-1].opened_at:
        return None

    result: int | None = None
    for index, candle in enumerate(candles):
        if candle.opened_at <= manual_time:
            result = index
        else:
            break

    return result


def build_manual_z_anchor(
    manual_time: datetime,
    candles: Sequence[Candle],
) -> ZAnchor | None:
    bar_index = find_manual_z_bar_by_time(manual_time, candles)
    if bar_index is None:
        return None

    candle = candles[bar_index]
    return ZAnchor(
        bar_index=bar_index,
        time=candle.opened_at,
        price=candle.low,
        reference_index=None,
        reference_high=candle.high,
        left_boundary_index=None,
        all_time_high_mode=False,
    )


def resolve_z_anchor(
    candles: Sequence[Candle],
    *,
    mode: ZSelectionMode = ZSelectionMode.AUTO,
    reference_lookback: int = DEFAULT_Z_REFERENCE_LOOKBACK_BARS,
    manual_time: datetime | None = None,
) -> ZAnchor | None:
    if mode is ZSelectionMode.MANUAL_TIME:
        if manual_time is None:
            return None
        return build_manual_z_anchor(manual_time, candles)

    return find_bull_z_anchor(
        candles,
        reference_lookback=reference_lookback,
    )
