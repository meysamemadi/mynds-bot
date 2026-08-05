from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from nds_bot.domain.market.timeframe import Timeframe


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    timeframe: Timeframe

    opened_at: datetime
    closed_at: datetime

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    volume: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol cannot be empty")

        if self.opened_at.tzinfo is None:
            raise ValueError("opened_at must be timezone-aware")

        if self.closed_at.tzinfo is None:
            raise ValueError("closed_at must be timezone-aware")

        if self.closed_at <= self.opened_at:
            raise ValueError("closed_at must be after opened_at")

        if self.low > self.high:
            raise ValueError("low cannot be greater than high")

        if not self.low <= self.open <= self.high:
            raise ValueError("open must be between low and high")

        if not self.low <= self.close <= self.high:
            raise ValueError("close must be between low and high")

        if self.volume < 0:
            raise ValueError("volume cannot be negative")
