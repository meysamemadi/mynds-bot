from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.domain.market.z import ZAnchor


def build_candlestick_figure(
    candles: Sequence[Candle],
    *,
    title: str | None = None,
    z_anchor: ZAnchor | None = None,
) -> go.Figure:
    if not candles:
        raise ValueError("candles cannot be empty")

    first = candles[0]

    if any(
        candle.symbol != first.symbol or candle.timeframe is not first.timeframe
        for candle in candles
    ):
        raise ValueError("all candles must use the same symbol and timeframe")

    figure = go.Figure()
    figure.add_trace(
        _build_trace(
            candles,
            name=f"{first.symbol} {first.timeframe.value}",
            visible=True,
        )
    )

    if z_anchor is not None:
        figure.add_trace(
            _build_z_trace(
                z_anchor,
                visible=True,
            )
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
    z_anchors: Mapping[tuple[str, Timeframe], ZAnchor] | None = None,
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
        is_visible = (symbol, timeframe) == initial_key

        trace_keys.append(key)
        figure.add_trace(
            _build_trace(
                candles,
                name=f"{symbol} {timeframe.value}",
                visible=is_visible,
            )
        )

        if z_anchors is not None:
            z_anchor = z_anchors.get((symbol, timeframe))
            if z_anchor is not None:
                trace_keys.append(key)
                figure.add_trace(
                    _build_z_trace(
                        z_anchor,
                        visible=is_visible,
                    )
                )

    initial_title = f"{initial_symbol} — {initial_timeframe.value}"
    _apply_workspace_layout(figure)

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
            "scrollZoom": True,
        },
    )

    symbol_buttons = "".join(
        _selector_button_html(
            label=symbol,
            data_name="symbol",
            data_value=symbol,
            active=symbol == initial_symbol,
        )
        for symbol in symbols
    )

    timeframe_buttons = "".join(
        _selector_button_html(
            label=timeframe.value,
            data_name="timeframe",
            data_value=timeframe.value,
            active=timeframe is initial_timeframe,
        )
        for timeframe in timeframes
    )

    trace_keys_json = json.dumps(trace_keys)
    initial_symbol_json = json.dumps(initial_symbol)
    initial_timeframe_json = json.dumps(initial_timeframe.value)

    document = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{escape(initial_title)} — cTrader</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b0e11;
      --panel: #111418;
      --panel-hover: #1b2028;
      --border: #242831;
      --text: #d1d4dc;
      --muted: #787b86;
      --active: #2962ff;
      --active-hover: #1e53e5;
      --positive: #26a69a;
    }}

    * {{
      box-sizing: border-box;
    }}

    html,
    body {{
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
    }}

    button {{
      font: inherit;
    }}

    .app-shell {{
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      width: 100vw;
      height: 100vh;
      background: var(--bg);
    }}

    .sidebar {{
      display: flex;
      min-height: 0;
      flex-direction: column;
      background: var(--panel);
      border-right: 1px solid var(--border);
    }}

    .brand {{
      display: flex;
      height: 52px;
      flex: 0 0 52px;
      align-items: center;
      gap: 10px;
      padding: 0 16px;
      border-bottom: 1px solid var(--border);
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}

    .brand-mark {{
      display: inline-flex;
      width: 26px;
      height: 26px;
      align-items: center;
      justify-content: center;
      border-radius: 6px;
      background: var(--active);
      color: #fff;
      font-size: 11px;
      font-weight: 800;
    }}

    .sidebar-content {{
      min-height: 0;
      flex: 1;
      overflow-y: auto;
      padding: 14px 10px 20px;
    }}

    .sidebar-section + .sidebar-section {{
      margin-top: 22px;
    }}

    .section-title {{
      margin: 0 8px 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    .selector-list {{
      display: grid;
      gap: 4px;
    }}

    .selector-button {{
      width: 100%;
      min-height: 38px;
      padding: 0 10px;
      border: 1px solid transparent;
      border-radius: 6px;
      background: transparent;
      color: var(--text);
      cursor: pointer;
      text-align: left;
      transition: background 120ms ease, border-color 120ms ease;
    }}

    .selector-button:hover {{
      background: var(--panel-hover);
    }}

    .selector-button.active {{
      border-color: rgba(41, 98, 255, 0.48);
      background: rgba(41, 98, 255, 0.18);
      color: #fff;
    }}

    .timeframe-list {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}

    .timeframe-list .selector-button {{
      text-align: center;
      font-weight: 600;
    }}

    .sidebar-footer {{
      padding: 12px 16px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 11px;
    }}

    .workspace {{
      display: flex;
      min-width: 0;
      min-height: 0;
      flex-direction: column;
      background: var(--bg);
    }}

    .topbar {{
      display: flex;
      height: 52px;
      flex: 0 0 52px;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }}

    .instrument-title {{
      display: flex;
      align-items: baseline;
      gap: 9px;
      white-space: nowrap;
    }}

    #active-symbol {{
      color: #f0f3fa;
      font-size: 15px;
      font-weight: 700;
    }}

    #active-timeframe {{
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }}

    .source-status {{
      display: flex;
      align-items: center;
      gap: 7px;
      color: var(--muted);
      font-size: 12px;
    }}

    .status-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--positive);
      box-shadow: 0 0 0 3px rgba(38, 166, 154, 0.12);
    }}

    .chart-container {{
      min-width: 0;
      min-height: 0;
      flex: 1;
      position: relative;
    }}

    #candlestick-chart {{
      width: 100% !important;
      height: 100% !important;
    }}

    #candlestick-chart .plot-container,
    #candlestick-chart .svg-container {{
      width: 100% !important;
      height: 100% !important;
    }}

    @media (max-width: 720px) {{
      .app-shell {{
        grid-template-columns: 150px minmax(0, 1fr);
      }}

      .brand {{
        padding: 0 10px;
      }}

      .source-status span:last-child {{
        display: none;
      }}
    }}
  </style>
</head>
<body>
  <main class=\"app-shell\">
    <aside class=\"sidebar\">
      <div class=\"brand\">
        <span class=\"brand-mark\">NDS</span>
        <span>Market Chart</span>
      </div>

      <div class=\"sidebar-content\">
        <section class=\"sidebar-section\">
          <h2 class=\"section-title\">Symbols</h2>
          <div class=\"selector-list\" id=\"symbol-list\">
            {symbol_buttons}
          </div>
        </section>

        <section class=\"sidebar-section\">
          <h2 class=\"section-title\">Timeframes</h2>
          <div class=\"selector-list timeframe-list\" id=\"timeframe-list\">
            {timeframe_buttons}
          </div>
        </section>
      </div>

      <div class=\"sidebar-footer\">cTrader historical trendbars</div>
    </aside>

    <section class=\"workspace\">
      <header class=\"topbar\">
        <div class=\"instrument-title\">
          <span id=\"active-symbol\">{escape(initial_symbol)}</span>
          <span id=\"active-timeframe\">{escape(initial_timeframe.value)}</span>
        </div>
        <div class=\"source-status\">
          <span class=\"status-dot\"></span>
          <span>cTrader data</span>
        </div>
      </header>

      <div class=\"chart-container\">
        {chart_div}
      </div>
    </section>
  </main>

  <script>
    const chartId = "candlestick-chart";
    const traceKeys = {trace_keys_json};
    let selectedSymbol = {initial_symbol_json};
    let selectedTimeframe = {initial_timeframe_json};

    const activeSymbol = document.getElementById("active-symbol");
    const activeTimeframe = document.getElementById("active-timeframe");
    const symbolButtons = Array.from(document.querySelectorAll("[data-symbol]"));
    const timeframeButtons = Array.from(
      document.querySelectorAll("[data-timeframe]")
    );

    function setActiveButton(buttons, selectedValue, dataName) {{
      for (const button of buttons) {{
        button.classList.toggle(
          "active",
          button.dataset[dataName] === selectedValue
        );
      }}
    }}

    function updateChart() {{
      const selectedKey = `${{selectedSymbol}}::${{selectedTimeframe}}`;
      const updates = traceKeys.map((key, index) =>
        Plotly.restyle(chartId, {{visible: key === selectedKey}}, [index])
      );

      setActiveButton(symbolButtons, selectedSymbol, "symbol");
      setActiveButton(timeframeButtons, selectedTimeframe, "timeframe");
      activeSymbol.textContent = selectedSymbol;
      activeTimeframe.textContent = selectedTimeframe;
      document.title = `${{selectedSymbol}} — ${{selectedTimeframe}} — cTrader`;

      Promise.all(updates).then(() => {{
        Plotly.relayout(chartId, {{
          "xaxis.autorange": true,
          "yaxis.autorange": true
        }});
        Plotly.Plots.resize(document.getElementById(chartId));
      }});
    }}

    for (const button of symbolButtons) {{
      button.addEventListener("click", () => {{
        selectedSymbol = button.dataset.symbol;
        updateChart();
      }});
    }}

    for (const button of timeframeButtons) {{
      button.addEventListener("click", () => {{
        selectedTimeframe = button.dataset.timeframe;
        updateChart();
      }});
    }}

    window.addEventListener("resize", () => {{
      Plotly.Plots.resize(document.getElementById(chartId));
    }});
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
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a",
        decreasing_fillcolor="#ef5350",
    )


def _build_z_trace(
    z_anchor: ZAnchor,
    *,
    visible: bool,
) -> go.Scatter:
    mode = "ATH" if z_anchor.all_time_high_mode else "bounded"
    boundary = (
        "none"
        if z_anchor.left_boundary_index is None
        else str(z_anchor.left_boundary_index)
    )
    hover_text = (
        f"Z<br>Price: {z_anchor.price}"
        f"<br>Reference High: {z_anchor.reference_high}"
        f"<br>Mode: {mode}"
        f"<br>Left boundary index: {boundary}"
    )

    return go.Scatter(
        x=[z_anchor.time],
        y=[float(z_anchor.price)],
        mode="text",
        text=["Z"],
        textposition="bottom center",
        textfont={"color": "#ffd700", "size": 14},
        hovertext=[hover_text],
        hoverinfo="text",
        name="Z",
        visible=visible,
        showlegend=False,
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


def _apply_workspace_layout(figure: go.Figure) -> None:
    figure.update_layout(
        autosize=True,
        showlegend=False,
        template="plotly_dark",
        paper_bgcolor="#0b0e11",
        plot_bgcolor="#0b0e11",
        margin={"l": 10, "r": 58, "t": 12, "b": 24},
        hovermode="x",
        xaxis={
            "rangeslider": {"visible": False},
            "showgrid": True,
            "gridcolor": "#1f232b",
            "zeroline": False,
            "showline": False,
            "title": None,
        },
        yaxis={
            "side": "right",
            "showgrid": True,
            "gridcolor": "#1f232b",
            "zeroline": False,
            "showline": False,
            "title": None,
            "fixedrange": False,
        },
    )


def _selection_key(symbol: str, timeframe: Timeframe) -> str:
    return f"{symbol}::{timeframe.value}"


def _selector_button_html(
    *,
    label: str,
    data_name: str,
    data_value: str,
    active: bool,
) -> str:
    safe_label = escape(label)
    safe_value = escape(data_value, quote=True)
    active_class = " active" if active else ""
    return (
        f'<button class="selector-button{active_class}" type="button" '
        f'data-{data_name}="{safe_value}">{safe_label}</button>'
    )
