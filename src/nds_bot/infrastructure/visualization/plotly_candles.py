from collections.abc import Sequence

import plotly.graph_objects as go

from nds_bot.domain.market.candle import Candle


def build_candlestick_figure(
    candles: Sequence[Candle],
    *,
    title: str | None = None,
) -> go.Figure:
    if not candles:
        raise ValueError("candles cannot be empty")

    first = candles[0]

    if any(
        candle.symbol != first.symbol or candle.timeframe is not first.timeframe
        for candle in candles
    ):
        raise ValueError("all candles must use the same symbol and timeframe")

    figure = go.Figure(
        data=[
            go.Candlestick(
                x=[candle.opened_at for candle in candles],
                open=[float(candle.open) for candle in candles],
                high=[float(candle.high) for candle in candles],
                low=[float(candle.low) for candle in candles],
                close=[float(candle.close) for candle in candles],
                name=f"{first.symbol} {first.timeframe.value}",
            )
        ]
    )

    figure.update_layout(
        title=title or f"{first.symbol} — {first.timeframe.value}",
        xaxis_title="Time (UTC)",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        hovermode="x",
    )

    return figure
