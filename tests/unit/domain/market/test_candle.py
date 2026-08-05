from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe


def make_valid_candle() -> Candle:
    return Candle(
        symbol="EURUSD",
        timeframe=Timeframe.M1,
        opened_at=datetime(
            2026,
            8,
            5,
            8,
            0,
            tzinfo=UTC,
        ),
        closed_at=datetime(
            2026,
            8,
            5,
            8,
            1,
            tzinfo=UTC,
        ),
        open=Decimal("1.15000"),
        high=Decimal("1.15100"),
        low=Decimal("1.14900"),
        close=Decimal("1.15050"),
        volume=Decimal("100"),
    )


def test_valid_candle_can_be_created() -> None:
    candle = make_valid_candle()

    assert candle.symbol == "EURUSD"
    assert candle.timeframe is Timeframe.M1
    assert candle.close == Decimal("1.15050")


def test_candle_rejects_low_above_high() -> None:
    with pytest.raises(
        ValueError,
        match="low cannot be greater than high",
    ):
        Candle(
            symbol="EURUSD",
            timeframe=Timeframe.M1,
            opened_at=datetime(
                2026,
                8,
                5,
                8,
                0,
                tzinfo=UTC,
            ),
            closed_at=datetime(
                2026,
                8,
                5,
                8,
                1,
                tzinfo=UTC,
            ),
            open=Decimal("1.15000"),
            high=Decimal("1.14900"),
            low=Decimal("1.15100"),
            close=Decimal("1.15050"),
            volume=Decimal("100"),
        )
