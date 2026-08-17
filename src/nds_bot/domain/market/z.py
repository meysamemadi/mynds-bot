from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from nds_bot.domain.market.candle import Candle

DEFAULT_Z_REFERENCE_LOOKBACK_BARS = 200


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
