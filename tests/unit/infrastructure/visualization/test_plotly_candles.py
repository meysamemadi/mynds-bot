from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.domain.market.trend import (
    fit_cubic_close_trend,
    fit_cubic_midpoint_trend,
)
from nds_bot.domain.market.z import ZAnchor, build_z_calculation_window
from nds_bot.infrastructure.visualization.plotly_candles import (
    build_candlestick_figure,
)


def _sample_candles() -> tuple[Candle, Candle]:
    opened_at = datetime(2026, 1, 1, tzinfo=UTC)
    first = Candle(
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
    return first, second


def _z_anchor(first: Candle, second: Candle) -> ZAnchor:
    return ZAnchor(
        bar_index=0,
        time=first.opened_at,
        price=first.low,
        reference_index=1,
        reference_high=second.high,
        left_boundary_index=None,
        all_time_high_mode=True,
    )


def _trend_candle(
    index: int,
    midpoint: Decimal,
    *,
    close: Decimal | None = None,
) -> Candle:
    opened_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
    close_price = midpoint if close is None else close
    return Candle(
        symbol="GOLD",
        timeframe=Timeframe.M1,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=1),
        open=midpoint,
        high=midpoint + Decimal("0.50"),
        low=midpoint - Decimal("0.50"),
        close=close_price,
        volume=Decimal("1"),
    )


def test_build_figure_renders_nodecounter_style_z_marker() -> None:
    first, second = _sample_candles()
    z_anchor = _z_anchor(first, second)

    figure = build_candlestick_figure(
        [first, second],
        z_anchor=z_anchor,
    )

    assert len(figure.data) == 2
    z_trace = figure.data[1]
    assert list(z_trace.text) == ["Z"]
    assert list(z_trace.x) == [first.opened_at]

    # NodeCounterv2 renderer offset:
    # max((6.00 - 5.00) * 0.35, 15 * 0.01) = 0.35
    assert float(z_trace.y[0]) == pytest.approx(4.65)


def test_build_figure_renders_z_window_end_marker() -> None:
    first, second = _sample_candles()
    candles = [first, second]
    z_anchor = _z_anchor(first, second)
    z_window = build_z_calculation_window(candles, z_anchor)

    figure = build_candlestick_figure(
        candles,
        z_anchor=z_anchor,
        z_window=z_window,
    )

    assert len(figure.data) == 3
    end_trace = figure.data[2]
    assert list(end_trace.text) == ["Z+1"]
    assert list(end_trace.x) == [second.opened_at]


def test_build_figure_renders_cubic_midpoint_trend() -> None:
    first, second = _sample_candles()
    candles = [first, second]
    for index, midpoint in enumerate(
        (Decimal("6.00"), Decimal("6.50")),
        start=2,
    ):
        opened_at = first.opened_at + timedelta(minutes=index)
        candles.append(
            Candle(
                symbol="GOLD",
                timeframe=Timeframe.M1,
                opened_at=opened_at,
                closed_at=opened_at + timedelta(minutes=1),
                open=midpoint,
                high=midpoint + Decimal("0.50"),
                low=midpoint - Decimal("0.50"),
                close=midpoint,
                volume=Decimal("1"),
            )
        )

    trend_fit = fit_cubic_midpoint_trend(candles)
    figure = build_candlestick_figure(candles, trend_fit=trend_fit)

    assert len(figure.data) == 2
    trend_trace = figure.data[1]
    assert trend_trace.name == "Cubic midpoint trend"
    assert list(trend_trace.x) == list(trend_fit.times)
    assert list(trend_trace.y) == pytest.approx(
        [float(value) for value in trend_fit.fitted_prices]
    )


def test_node_markers_have_no_text_and_show_derivative_sign() -> None:
    candles = []
    for index in range(7):
        x = Decimal(index)
        midpoint = Decimal(100) + x**3 - Decimal(6) * x**2 + Decimal(9) * x
        candles.append(_trend_candle(index, midpoint))

    trend_fit = fit_cubic_midpoint_trend(candles)
    figure = build_candlestick_figure(candles, trend_fit=trend_fit)

    assert len(figure.data) == 4
    first_derivative_trace = figure.data[2]
    second_derivative_trace = figure.data[3]

    assert first_derivative_trace.mode == "markers"
    assert first_derivative_trace.text is None
    assert first_derivative_trace.marker.symbol == "circle"
    assert first_derivative_trace.marker.color == "#ffd700"
    assert list(first_derivative_trace.x) == [
        candles[1].opened_at,
        candles[3].opened_at,
    ]

    assert second_derivative_trace.mode == "markers"
    assert second_derivative_trace.text is None
    assert second_derivative_trace.marker.symbol == "circle"
    assert list(second_derivative_trace.marker.color) == [
        "#ef5350",
        "#26a69a",
    ]
    assert all(
        upper > lower
        for upper, lower in zip(
            second_derivative_trace.y,
            first_derivative_trace.y,
            strict=True,
        )
    )


def test_build_figure_renders_midpoint_and_close_trends_together() -> None:
    candles = []
    for index in range(7):
        x = Decimal(index)
        midpoint = Decimal(100) + x**3 - Decimal(6) * x**2 + Decimal(9) * x
        close = Decimal(105) - x**3 + Decimal(6) * x**2 - Decimal(9) * x
        candles.append(_trend_candle(index, midpoint, close=close))

    midpoint_fit = fit_cubic_midpoint_trend(candles)
    close_fit = fit_cubic_close_trend(candles)
    figure = build_candlestick_figure(
        candles,
        trend_fit=midpoint_fit,
        close_trend_fit=close_fit,
    )

    trace_names = [trace.name for trace in figure.data]
    assert "Cubic midpoint trend" in trace_names
    assert "Cubic close trend" in trace_names
