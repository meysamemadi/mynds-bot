from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.infrastructure.market_data.history_cache import (
    CandleHistoryCache,
    merge_candle_history,
)


def _candle(index: int, *, close: str | None = None) -> Candle:
    opened_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    close_value = Decimal(close) if close is not None else Decimal("10")

    return Candle(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=1),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=close_value,
        volume=Decimal("5"),
    )


def test_cache_round_trip_preserves_decimal_candles(tmp_path) -> None:
    cache = CandleHistoryCache(tmp_path)
    candles = [_candle(0), _candle(1, close="10.25")]

    path = cache.save(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        candles=candles,
    )
    loaded = cache.load(symbol="GOLD", timeframe=Timeframe.M1)

    assert path.exists()
    assert loaded == candles
    assert loaded[1].close == Decimal("10.25")


def test_cache_save_can_replace_existing_series(tmp_path) -> None:
    cache = CandleHistoryCache(tmp_path)

    cache.save(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        candles=[_candle(0, close="10.10")],
    )
    cache.save(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        candles=[_candle(0, close="10.90"), _candle(1)],
    )

    loaded = cache.load(symbol="GOLD", timeframe=Timeframe.M1)

    assert len(loaded) == 2
    assert loaded[0].close == Decimal("10.90")


def test_merge_replaces_same_timestamp_with_newer_value_and_keeps_order() -> None:
    original = [_candle(0), _candle(1, close="10.10")]
    refreshed = [_candle(1, close="10.50"), _candle(2)]

    merged = merge_candle_history(original, refreshed)

    assert [candle.opened_at for candle in merged] == [
        original[0].opened_at,
        original[1].opened_at,
        refreshed[1].opened_at,
    ]
    assert merged[1].close == Decimal("10.50")


def test_merge_can_keep_only_latest_target_count() -> None:
    candles = [_candle(index) for index in range(5)]

    merged = merge_candle_history(candles, max_candles=3)

    assert merged == candles[-3:]
