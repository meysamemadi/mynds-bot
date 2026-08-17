from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.domain.market.z import (
    ZSelectionMode,
    find_bull_reference_high,
    find_bull_z_anchor,
    resolve_z_anchor,
)

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int, *, high: str, low: str) -> Candle:
    opened_at = BASE_TIME + timedelta(minutes=index)
    high_value = Decimal(high)
    low_value = Decimal(low)
    middle = (high_value + low_value) / Decimal("2")

    return Candle(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=1),
        open=middle,
        high=high_value,
        low=low_value,
        close=middle,
        volume=Decimal("1"),
    )


def test_reference_high_uses_latest_lookback_and_newest_equal_high_wins() -> None:
    candles = [
        _candle(0, high="20", low="10"),
        _candle(1, high="12", low="8"),
        _candle(2, high="12", low="7"),
        _candle(3, high="11", low="6"),
    ]

    assert find_bull_reference_high(candles, reference_lookback=3) == 2


def test_z_uses_nearest_older_high_strictly_above_reference_as_boundary() -> None:
    candles = [
        _candle(0, high="15", low="1"),
        _candle(1, high="9", low="5"),
        _candle(2, high="12", low="6"),
        _candle(3, high="11", low="7"),
    ]

    z = find_bull_z_anchor(candles, reference_lookback=3)

    assert z is not None
    assert z.reference_index == 2
    assert z.reference_high == Decimal("12")
    assert z.left_boundary_index == 0
    assert z.bar_index == 1
    assert z.price == Decimal("5")
    assert z.all_time_high_mode is False


def test_equal_older_high_is_not_a_left_boundary() -> None:
    candles = [
        _candle(0, high="12", low="4"),
        _candle(1, high="9", low="5"),
        _candle(2, high="12", low="6"),
        _candle(3, high="11", low="7"),
    ]

    z = find_bull_z_anchor(candles, reference_lookback=3)

    assert z is not None
    assert z.reference_index == 2
    assert z.left_boundary_index is None
    assert z.all_time_high_mode is True
    assert z.bar_index == 0


def test_boundary_candle_is_excluded_from_z_low_search() -> None:
    candles = [
        _candle(0, high="15", low="1"),
        _candle(1, high="9", low="5"),
        _candle(2, high="12", low="6"),
    ]

    z = find_bull_z_anchor(candles, reference_lookback=2)

    assert z is not None
    assert z.left_boundary_index == 0
    assert z.bar_index == 1
    assert z.price == Decimal("5")


def test_equal_low_uses_newest_low() -> None:
    candles = [
        _candle(0, high="15", low="2"),
        _candle(1, high="9", low="5"),
        _candle(2, high="12", low="5"),
        _candle(3, high="11", low="7"),
    ]

    z = find_bull_z_anchor(candles, reference_lookback=3)

    assert z is not None
    assert z.bar_index == 2
    assert z.price == Decimal("5")


def test_ath_mode_searches_from_loaded_history_start_to_reference() -> None:
    candles = [
        _candle(0, high="10", low="5"),
        _candle(1, high="11", low="4"),
        _candle(2, high="12", low="6"),
    ]

    z = find_bull_z_anchor(candles, reference_lookback=3)

    assert z is not None
    assert z.reference_index == 2
    assert z.left_boundary_index is None
    assert z.all_time_high_mode is True
    assert z.bar_index == 1
    assert z.price == Decimal("4")


def test_manual_time_resolves_to_latest_closed_candle_open_at_or_before_time() -> None:
    candles = [
        _candle(0, high="10", low="5"),
        _candle(1, high="11", low="4"),
        _candle(2, high="12", low="3"),
        _candle(3, high="13", low="2"),
    ]
    manual_time = candles[2].opened_at + timedelta(seconds=30)

    z = resolve_z_anchor(
        candles,
        mode=ZSelectionMode.MANUAL_TIME,
        manual_time=manual_time,
    )

    assert z is not None
    assert z.bar_index == 2
    assert z.time == candles[2].opened_at
    assert z.price == candles[2].low
    assert z.reference_index is None
    assert z.reference_high == candles[2].high


def test_manual_time_outside_loaded_closed_history_is_rejected() -> None:
    candles = [
        _candle(0, high="10", low="5"),
        _candle(1, high="11", low="4"),
    ]

    z = resolve_z_anchor(
        candles,
        mode=ZSelectionMode.MANUAL_TIME,
        manual_time=candles[-1].opened_at + timedelta(seconds=1),
    )

    assert z is None
