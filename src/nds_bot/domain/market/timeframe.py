from datetime import timedelta
from enum import StrEnum


class Timeframe(StrEnum):
    M1 = "M1"
    M3 = "M3"
    M15 = "M15"
    H1 = "H1"

    @property
    def duration(self) -> timedelta:
        match self:
            case Timeframe.M1:
                return timedelta(minutes=1)
            case Timeframe.M3:
                return timedelta(minutes=3)
            case Timeframe.M15:
                return timedelta(minutes=15)
            case Timeframe.H1:
                return timedelta(hours=1)
