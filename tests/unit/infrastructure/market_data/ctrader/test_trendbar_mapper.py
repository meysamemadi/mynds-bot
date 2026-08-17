from datetime import UTC, datetime
from decimal import Decimal

from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.infrastructure.market_data.ctrader.trendbar_mapper import (
    CTraderTrendbar,
    map_trendbar_to_candle,
)


def test_maps_ctrader_trendbar_to_domain_candle() -> None:
    trendbar = CTraderTrendbar(
        low=115593,
        delta_open=4,
        delta_high=4,
        delta_close=1,
        volume=17,
        utc_timestamp_in_minutes=29768890,
    )

    candle = map_trendbar_to_candle(
        trendbar=trendbar,
        symbol="EURUSD",
        timeframe=Timeframe.M1,
        digits=5,
    )

    assert candle.symbol == "EURUSD"
    assert candle.timeframe is Timeframe.M1

    assert candle.opened_at == datetime(
        2026,
        8,
        7,
        20,
        10,
        tzinfo=UTC,
    )

    assert candle.closed_at == datetime(
        2026,
        8,
        7,
        20,
        11,
        tzinfo=UTC,
    )

    assert candle.open == Decimal("1.15597")
    assert candle.high == Decimal("1.15597")
    assert candle.low == Decimal("1.15593")
    assert candle.close == Decimal("1.15594")

    assert candle.volume == Decimal("17")