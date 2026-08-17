from datetime import timedelta

import pytest

from nds_bot.domain.market.timeframe import Timeframe


@pytest.mark.parametrize(
    ("timeframe", "expected_duration"),
    [
        (Timeframe.M1, timedelta(minutes=1)),
        (Timeframe.M3, timedelta(minutes=3)),
        (Timeframe.M15, timedelta(minutes=15)),
        (Timeframe.H1, timedelta(hours=1)),
    ],
)
def test_timeframe_duration(
    timeframe: Timeframe,
    expected_duration: timedelta,
) -> None:
    assert timeframe.duration == expected_duration
