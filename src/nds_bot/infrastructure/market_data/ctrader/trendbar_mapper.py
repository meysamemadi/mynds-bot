from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe

CTRADER_PRICE_DIVISOR = Decimal("100000")


@dataclass(frozen=True, slots=True)
class CTraderTrendbar:
    low: int
    delta_open: int
    delta_high: int
    delta_close: int
    volume: int
    utc_timestamp_in_minutes: int


def map_trendbar_to_candle(
    *,
    trendbar: CTraderTrendbar,
    symbol: str,
    timeframe: Timeframe,
    digits: int,
) -> Candle:
    opened_at = datetime.fromtimestamp(
        trendbar.utc_timestamp_in_minutes * 60,
        tz=UTC,
    )

    closed_at = opened_at + timeframe.duration

    low_raw = trendbar.low
    open_raw = low_raw + trendbar.delta_open
    high_raw = low_raw + trendbar.delta_high
    close_raw = low_raw + trendbar.delta_close

    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        opened_at=opened_at,
        closed_at=closed_at,
        open=_to_price(open_raw, digits),
        high=_to_price(high_raw, digits),
        low=_to_price(low_raw, digits),
        close=_to_price(close_raw, digits),
        volume=Decimal(trendbar.volume),
    )


def _to_price(
    raw_price: int,
    digits: int,
) -> Decimal:
    price = Decimal(raw_price) / CTRADER_PRICE_DIVISOR

    precision = Decimal(1).scaleb(-digits)

    return price.quantize(precision)