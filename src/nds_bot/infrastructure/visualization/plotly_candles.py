from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe


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
            _build_trace(
                candles,
                name=f"{first.symbol} {first.timeframe.value}",
                visible=True,
            )
        ]
    )

    _apply_layout(
        figure,
        title=title or f"{first.symbol} — {first.timeframe.value}",
    )

    return figure


def write_switchable_candlestick_chart(
    series: Mapping[tuple[str, Timeframe], Sequence[Candle]],
    *,
    output_path: Path,
    initial_symbol: str,
    initial_timeframe: Timeframe,
) -> Path:
    if not series:
        raise ValueError("series cannot be empty")

    initial_key = (initial_symbol, initial_timeframe)

    if initial_key not in series:
        raise ValueError("initial symbol/timeframe combination is not available")

    figure = go.Figure()
    trace_keys: list[str] = []

    for (symbol, timeframe), candles in series.items():
        _validate_series(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
        )

        key = _selection_key(symbol, timeframe)
        trace_keys.append(key)

        figure.add_trace(
            _build_trace(
                candles,
                name=f"{symbol} {timeframe.value}",
                visible=(symbol, timeframe) == initial_key,
            )
        )

    initial_title = f"{initial_symbol} — {initial_timeframe.value} — cTrader"
    _apply_layout(figure, title=initial_title)
    figure.update_layout(showlegend=False)

    symbols = list(dict.fromkeys(symbol for symbol, _ in series))
    timeframes = list(dict.fromkeys(timeframe for _, timeframe in series))

    chart_div = pio.to_html(
        figure,
        include_plotlyjs="cdn",
        full_html=False,
        div_id="candlestick-chart",
        config={
            "displaylogo": False,
            "responsive": True,
        },
    )

    symbol_options = "".join(
        _option_html(
            value=symbol,
            selected=symbol == initial_symbol,
        )
        for symbol in symbols
    )

    timeframe_options = "".join(
        _option_html(
            value=timeframe.value,
            selected=timeframe is initial_timeframe,
        )
        for timeframe in timeframes
    )

    trace_keys_json = json.dumps(trace_keys)

    document = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escape(initial_title)}</title>
  <style>
    html, body {{
      margin: 0;
      min-height: 100%;
      background: #111827;
      color: #f9fafb;
      font-family: Arial, sans-serif;
    }}
    .toolbar {{
      display: flex;
      gap: 12px;
      align-items: end;
      padding: 14px 18px 4px;
      background: #111827;
    }}
    .control {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      color: #9ca3af;
    }}
    select {{
      min-width: 150px;
      padding: 8px 10px;
      border: 1px solid #374151;
      border-radius: 6px;
      background: #1f2937;
      color: #f9fafb;
      font-size: 14px;
    }}
    #candlestick-chart {{
      width: 100%;
      height: calc(100vh - 76px);
    }}
  </style>
</head>
<body>
  <div class=\"toolbar\">
    <label class=\"control\">
      Symbol
      <select id=\"symbol-select\">{symbol_options}</select>
    </label>
    <label class=\"control\">
      Timeframe
      <select id=\"timeframe-select\">{timeframe_options}</select>
    </label>
  </div>
  {chart_div}
  <script>
    const chartId = "candlestick-chart";
    const traceKeys = {trace_keys_json};
    const symbolSelect = document.getElementById("symbol-select");
    const timeframeSelect = document.getElementById("timeframe-select");

    function updateChart() {{
      const selectedKey = `${{symbolSelect.value}}::${{timeframeSelect.value}}`;
      const updates = traceKeys.map((key, index) =>
        Plotly.restyle(chartId, {{visible: key === selectedKey}}, [index])
      );

      Promise.all(updates).then(() => {{
        Plotly.relayout(chartId, {{
          "title.text": `${{symbolSelect.value}} — ${{timeframeSelect.value}} — cTrader`,
          "xaxis.autorange": true,
          "yaxis.autorange": true
        }});
      }});
    }}

    symbolSelect.addEventListener("change", updateChart);
    timeframeSelect.addEventListener("change", updateChart);
  </script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def _validate_series(
    *,
    symbol: str,
    timeframe: Timeframe,
    candles: Sequence[Candle],
) -> None:
    if not candles:
        raise ValueError(f"candles cannot be empty for {symbol} {timeframe.value}")

    if any(
        candle.symbol != symbol or candle.timeframe is not timeframe
        for candle in candles
    ):
        raise ValueError("series key must match every candle")


def _build_trace(
    candles: Sequence[Candle],
    *,
    name: str,
    visible: bool,
) -> go.Candlestick:
    return go.Candlestick(
        x=[candle.opened_at for candle in candles],
        open=[float(candle.open) for candle in candles],
        high=[float(candle.high) for candle in candles],
        low=[float(candle.low) for candle in candles],
        close=[float(candle.close) for candle in candles],
        name=name,
        visible=visible,
    )


def _apply_layout(
    figure: go.Figure,
    *,
    title: str,
) -> None:
    figure.update_layout(
        title=title,
        xaxis_title="Time (UTC)",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        hovermode="x",
    )


def _selection_key(symbol: str, timeframe: Timeframe) -> str:
    return f"{symbol}::{timeframe.value}"


def _option_html(*, value: str, selected: bool) -> str:
    selected_attribute = " selected" if selected else ""
    safe_value = escape(value, quote=True)
    return f'<option value="{safe_value}"{selected_attribute}>{safe_value}</option>'
