from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.domain.market.z import ZAnchor
from nds_bot.infrastructure.visualization.plotly_candles import (
    build_candlestick_figure,
)


def test_build_figure_renders_nodecounter_style_z_marker() -> None:
    opened_at = datetime(2026, 1, 1, tzinfo=UTC)
    candle = Candle(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=1),
        open=Decimal("5.50"),
        high=Decimal("6.00"),
        low=Decimal("5.00"),
        close=Decimal("5.50"),
        volume=Decimal("1"),
    )
    second = Candle(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        opened_at=opened_at + timedelta(minutes=1),
        closed_at=opened_at + timedelta(minutes=2),
        open=Decimal("5.75"),
        high=Decimal("6.25"),
        low=Decimal("5.25"),
        close=Decimal("5.75"),
        volume=Decimal("1"),
    )
    z_anchor = ZAnchor(
        bar_index=0,
        time=candle.opened_at,
        price=candle.low,
        reference_index=1,
        reference_high=second.high,
        left_boundary_index=None,
        all_time_high_mode=True,
    )

    figure = build_candlestick_figure(
        [candle, second],
        z_anchor=z_anchor,
    )

    assert len(figure.data) == 2
    z_trace = figure.data[1]
    assert list(z_trace.text) == ["Z"]
    assert list(z_trace.x) == [candle.opened_at]

    # NodeCounterv2 renderer offset:
    # max((6.00 - 5.00) * 0.35, 15 * 0.01) = 0.35
    assert float(z_trace.y[0]) == pytest.approx(4.65)
