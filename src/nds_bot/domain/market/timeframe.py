from datetime import timedelta
from enum import StrEnum


class Timeframe(StrEnum):
    M1 = "M1"

    @property
    def duration(self) -> timedelta:
        match self:
            case Timeframe.M1:
                return timedelta(minutes=1)
