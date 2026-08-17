from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.domain.market.trend import candle_midpoint, fit_cubic_midpoint_trend

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int, *, midpoint: Decimal) -> Candle:
    opened_at = BASE_TIME + timedelta(minutes=index)
    return Candle(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=1),
        open=midpoint,
        high=midpoint + Decimal("1"),
        low=midpoint - Decimal("1"),
        close=midpoint,
        volume=Decimal("1"),
    )


def test_candle_midpoint_averages_high_and_low() -> None:
    candle = _candle(0, midpoint=Decimal("10.25"))

    assert candle_midpoint(candle) == Decimal("10.25")


def test_cubic_fit_recovers_exact_degree_three_series() -> None:
    expected = (
        Decimal("2"),
        Decimal("3"),
        Decimal("-0.5"),
        Decimal("0.1"),
    )
    candles = []
    for index in range(12):
        x = Decimal(index)
        midpoint = (
            expected[0]
            + expected[1] * x
            + expected[2] * x**2
            + expected[3] * x**3
        )
        candles.append(_candle(index, midpoint=midpoint))

    fit = fit_cubic_midpoint_trend(candles)

    tolerance = Decimal("1e-40")
    for actual, wanted in zip(fit.coefficients, expected, strict=True):
        assert abs(actual - wanted) < tolerance

    assert fit.point_count == len(candles)
    assert fit.times[0] == candles[0].opened_at
    assert fit.times[-1] == candles[-1].opened_at
    assert fit.midpoint_prices[4] == candle_midpoint(candles[4])
    assert fit.mse < Decimal("1e-80")


def test_cubic_fit_requires_at_least_four_candles() -> None:
    candles = [_candle(index, midpoint=Decimal(index)) for index in range(3)]

    with pytest.raises(ValueError, match="at least 4 candles"):
        fit_cubic_midpoint_trend(candles)
