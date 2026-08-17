from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from nds_bot.domain.market.candle import Candle
from nds_bot.domain.market.timeframe import Timeframe
from nds_bot.domain.market.trend import (
    CubicTrendFit,
    TrendNode,
    TrendNodeType,
    find_cubic_trend_nodes,
)
from nds_bot.domain.market.z import ZAnchor, ZCalculationWindow


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__PAGE_TITLE__</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0e11;
      --panel: #111418;
      --panel-hover: #1b2028;
      --border: #242831;
      --text: #d1d4dc;
      --muted: #787b86;
      --active: #2962ff;
      --positive: #26a69a;
    }

    * { box-sizing: border-box; }

    html,
    body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    button { font: inherit; }

    .app-shell {
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      width: 100vw;
      height: 100vh;
      background: var(--bg);
    }

    .sidebar {
      display: flex;
      min-height: 0;
      flex-direction: column;
      background: var(--panel);
      border-right: 1px solid var(--border);
    }

    .brand {
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
    }

    .brand-mark {
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
    }

    .sidebar-content {
      min-height: 0;
      flex: 1;
      overflow-y: auto;
      padding: 14px 10px 20px;
    }

    .sidebar-section + .sidebar-section { margin-top: 22px; }

    .section-title {
      margin: 0 8px 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .selector-list {
      display: grid;
      gap: 4px;
    }

    .selector-button {
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
    }

    .selector-button:hover { background: var(--panel-hover); }

    .selector-button.active {
      border-color: rgba(41, 98, 255, 0.48);
      background: rgba(41, 98, 255, 0.18);
      color: #fff;
    }

    .timeframe-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }

    .timeframe-list .selector-button {
      text-align: center;
      font-weight: 600;
    }

    .sidebar-footer {
      padding: 12px 16px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 11px;
    }

    .workspace {
      display: flex;
      min-width: 0;
      min-height: 0;
      flex-direction: column;
      background: var(--bg);
    }

    .topbar {
      display: flex;
      height: 52px;
      flex: 0 0 52px;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 16px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }

    .instrument-title {
      display: flex;
      align-items: baseline;
      gap: 9px;
      white-space: nowrap;
    }

    #active-symbol {
      color: #f0f3fa;
      font-size: 15px;
      font-weight: 700;
    }

    #active-timeframe {
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }

    .topbar-status {
      display: flex;
      min-width: 0;
      align-items: center;
      gap: 14px;
      color: var(--muted);
      font-size: 12px;
    }

    #z-window-status {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .source-status {
      display: flex;
      align-items: center;
      gap: 7px;
      white-space: nowrap;
    }

    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--positive);
      box-shadow: 0 0 0 3px rgba(38, 166, 154, 0.12);
    }

    .chart-container {
      min-width: 0;
      min-height: 0;
      flex: 1;
      position: relative;
    }

    #candlestick-chart,
    #candlestick-chart .plot-container,
    #candlestick-chart .svg-container {
      width: 100% !important;
      height: 100% !important;
    }

    @media (max-width: 720px) {
      .app-shell { grid-template-columns: 150px minmax(0, 1fr); }
      .brand { padding: 0 10px; }
      #z-window-status { display: none; }
      .source-status span:last-child { display: none; }
    }
  </style>
</head>
<body>
  <main class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">NDS</span>
        <span>Market Chart</span>
      </div>

      <div class="sidebar-content">
        <section class="sidebar-section">
          <h2 class="section-title">Symbols</h2>
          <div class="selector-list" id="symbol-list">__SYMBOL_BUTTONS__</div>
        </section>

        <section class="sidebar-section">
          <h2 class="section-title">Timeframes</h2>
          <div class="selector-list timeframe-list" id="timeframe-list">
            __TIMEFRAME_BUTTONS__
          </div>
        </section>
      </div>

      <div class="sidebar-footer">cTrader historical trendbars</div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div class="instrument-title">
          <span id="active-symbol">__INITIAL_SYMBOL_TEXT__</span>
          <span id="active-timeframe">__INITIAL_TIMEFRAME_TEXT__</span>
        </div>
        <div class="topbar-status">
          <span id="z-window-status"></span>
          <span class="source-status">
            <span class="status-dot"></span>
            <span>cTrader data</span>
          </span>
        </div>
      </header>

      <div class="chart-container">__CHART_DIV__</div>
    </section>
  </main>

  <script>
    const chartId = "candlestick-chart";
    const traceKeys = __TRACE_KEYS_JSON__;
    const windowMeta = __WINDOW_META_JSON__;
    let selectedSymbol = __INITIAL_SYMBOL_JSON__;
    let selectedTimeframe = __INITIAL_TIMEFRAME_JSON__;

    const activeSymbol = document.getElementById("active-symbol");
    const activeTimeframe = document.getElementById("active-timeframe");
    const zWindowStatus = document.getElementById("z-window-status");
    const symbolButtons = Array.from(document.querySelectorAll("[data-symbol]"));
    const timeframeButtons = Array.from(
      document.querySelectorAll("[data-timeframe]")
    );

    function setActiveButton(buttons, selectedValue, dataName) {
      for (const button of buttons) {
        button.classList.toggle(
          "active",
          button.dataset[dataName] === selectedValue
        );
      }
    }

    function updateChart() {
      const selectedKey = `${selectedSymbol}::${selectedTimeframe}`;
      const updates = traceKeys.map((key, index) =>
        Plotly.restyle(chartId, {visible: key === selectedKey}, [index])
      );

      setActiveButton(symbolButtons, selectedSymbol, "symbol");
      setActiveButton(timeframeButtons, selectedTimeframe, "timeframe");
      activeSymbol.textContent = selectedSymbol;
      activeTimeframe.textContent = selectedTimeframe;

      const meta = windowMeta[selectedKey];
      zWindowStatus.textContent = meta ? meta.label : "Z window unavailable";
      document.title = `${selectedSymbol} — ${selectedTimeframe} — cTrader`;

      Promise.all(updates).then(() => {
        Plotly.relayout(chartId, {
          "xaxis.autorange": true,
          "yaxis.autorange": true
        });
        Plotly.Plots.resize(document.getElementById(chartId));
      });
    }

    for (const button of symbolButtons) {
      button.addEventListener("click", () => {
        selectedSymbol = button.dataset.symbol;
        updateChart();
      });
    }

    for (const button of timeframeButtons) {
      button.addEventListener("click", () => {
        selectedTimeframe = button.dataset.timeframe;
        updateChart();
      });
    }

    window.addEventListener("resize", () => {
      Plotly.Plots.resize(document.getElementById(chartId));
    });
    updateChart();
  </script>
</body>
</html>
"""


def build_candlestick_figure(
    candles: Sequence[Candle],
    *,
    title: str | None = None,
    z_anchor: ZAnchor | None = None,
    z_window: ZCalculationWindow | None = None,
    trend_fit: CubicTrendFit | None = None,
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
        figure.add_trace(_build_z_trace(candles, z_anchor, visible=True))

    if z_window is not None and z_window.candles:
        figure.add_trace(_build_z_window_end_trace(z_window, visible=True))

    if trend_fit is not None:
        figure.add_trace(_build_cubic_trend_trace(trend_fit, visible=True))
        nodes = find_cubic_trend_nodes(trend_fit)
        if nodes:
            figure.add_trace(_build_trend_nodes_trace(nodes, visible=True))

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
    z_windows: Mapping[tuple[str, Timeframe], ZCalculationWindow] | None = None,
    trend_fits: Mapping[tuple[str, Timeframe], CubicTrendFit] | None = None,
) -> Path:
    if not series:
        raise ValueError("series cannot be empty")

    initial_key = (initial_symbol, initial_timeframe)
    if initial_key not in series:
        raise ValueError("initial symbol/timeframe combination is not available")

    figure = go.Figure()
    trace_keys: list[str] = []
    node_counts: dict[tuple[str, Timeframe], int] = {}

    for (symbol, timeframe), candles in series.items():
        _validate_series(symbol=symbol, timeframe=timeframe, candles=candles)
        selection_key = _selection_key(symbol, timeframe)
        is_visible = (symbol, timeframe) == initial_key

        trace_keys.append(selection_key)
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
                trace_keys.append(selection_key)
                figure.add_trace(
                    _build_z_trace(candles, z_anchor, visible=is_visible)
                )

        if z_windows is not None:
            z_window = z_windows.get((symbol, timeframe))
            if z_window is not None and z_window.candles:
                trace_keys.append(selection_key)
                figure.add_trace(
                    _build_z_window_end_trace(z_window, visible=is_visible)
                )

        if trend_fits is not None:
            trend_fit = trend_fits.get((symbol, timeframe))
            if trend_fit is not None:
                trace_keys.append(selection_key)
                figure.add_trace(
                    _build_cubic_trend_trace(trend_fit, visible=is_visible)
                )

                nodes = find_cubic_trend_nodes(trend_fit)
                node_counts[(symbol, timeframe)] = len(nodes)
                if nodes:
                    trace_keys.append(selection_key)
                    figure.add_trace(
                        _build_trend_nodes_trace(nodes, visible=is_visible)
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

    window_meta = _window_metadata(
        series,
        z_windows,
        trend_fits,
        node_counts,
    )
    document = _HTML_TEMPLATE
    replacements = {
        "__PAGE_TITLE__": escape(f"{initial_title} — cTrader"),
        "__SYMBOL_BUTTONS__": symbol_buttons,
        "__TIMEFRAME_BUTTONS__": timeframe_buttons,
        "__INITIAL_SYMBOL_TEXT__": escape(initial_symbol),
        "__INITIAL_TIMEFRAME_TEXT__": escape(initial_timeframe.value),
        "__CHART_DIV__": chart_div,
        "__TRACE_KEYS_JSON__": json.dumps(trace_keys),
        "__WINDOW_META_JSON__": json.dumps(window_meta),
        "__INITIAL_SYMBOL_JSON__": json.dumps(initial_symbol),
        "__INITIAL_TIMEFRAME_JSON__": json.dumps(initial_timeframe.value),
    }
    for placeholder, value in replacements.items():
        document = document.replace(placeholder, value)

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
    candles: Sequence[Candle],
    z_anchor: ZAnchor,
    *,
    visible: bool,
) -> go.Scatter:
    z_candle = next(
        (candle for candle in candles if candle.opened_at == z_anchor.time),
        None,
    )
    if z_candle is None:
        raise ValueError("Z anchor candle is not present in chart candles")

    candle_size = z_candle.high - z_candle.low
    point = _decimal_point(z_anchor.price)
    offset = max(
        candle_size * Decimal("0.35"),
        Decimal(15) * point,
    )
    draw_price = z_anchor.price - offset

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
        y=[float(draw_price)],
        mode="text",
        text=["Z"],
        textposition="middle center",
        textfont={"color": "#ffd700", "size": 14},
        hovertext=[hover_text],
        hoverinfo="text",
        name="Z",
        visible=visible,
        showlegend=False,
    )


def _build_z_window_end_trace(
    z_window: ZCalculationWindow,
    *,
    visible: bool,
) -> go.Scatter:
    if not z_window.candles:
        raise ValueError("Z calculation window cannot be empty")

    end_candle = z_window.candles[-1]
    candle_size = end_candle.high - end_candle.low
    point = _decimal_point(end_candle.high)
    offset = max(
        candle_size * Decimal("0.25"),
        Decimal(10) * point,
    )
    draw_price = end_candle.high + offset
    label = f"Z+{z_window.available_bars}"
    status = "complete" if z_window.complete else "incomplete"

    return go.Scatter(
        x=[end_candle.opened_at],
        y=[float(draw_price)],
        mode="markers+text",
        marker={
            "symbol": "diamond-open",
            "size": 8,
            "color": "#ffd700",
        },
        text=[label],
        textposition="top center",
        textfont={"color": "#c8a900", "size": 10},
        hovertext=[
            f"{label}<br>Z calculation window: {status}"
            f"<br>Available bars: {z_window.available_bars}"
            f"<br>Requested bars: {z_window.requested_bars_after_z}"
        ],
        hoverinfo="text",
        name="Z window end",
        visible=visible,
        showlegend=False,
    )


def _build_cubic_trend_trace(
    trend_fit: CubicTrendFit,
    *,
    visible: bool,
) -> go.Scatter:
    residuals = [
        observed - fitted
        for observed, fitted in zip(
            trend_fit.midpoint_prices,
            trend_fit.fitted_prices,
            strict=True,
        )
    ]
    customdata = [
        [float(midpoint), float(fitted), float(residual), index]
        for index, (midpoint, fitted, residual) in enumerate(
            zip(
                trend_fit.midpoint_prices,
                trend_fit.fitted_prices,
                residuals,
                strict=True,
            )
        )
    ]

    return go.Scatter(
        x=list(trend_fit.times),
        y=[float(price) for price in trend_fit.fitted_prices],
        mode="lines",
        line={"color": "#42a5f5", "width": 2},
        customdata=customdata,
        hovertemplate=(
            "Cubic trend"
            "<br>x=%{customdata[3]}"
            "<br>Midpoint=%{customdata[0]:.5f}"
            "<br>Fitted=%{customdata[1]:.5f}"
            "<br>Residual=%{customdata[2]:.5f}"
            "<extra></extra>"
        ),
        name="Cubic midpoint trend",
        visible=visible,
        showlegend=False,
    )


def _build_trend_nodes_trace(
    nodes: Sequence[TrendNode],
    *,
    visible: bool,
) -> go.Scatter:
    labels = [
        f"N{index} {node.node_type.value}"
        for index, node in enumerate(nodes, start=1)
    ]
    marker_symbols = [_node_marker_symbol(node.node_type) for node in nodes]
    marker_colors = [_node_marker_color(node.node_type) for node in nodes]
    customdata = [
        [
            float(node.x),
            float(node.first_derivative),
            float(node.second_derivative),
            node.node_type.value,
        ]
        for node in nodes
    ]

    return go.Scatter(
        x=[node.time for node in nodes],
        y=[float(node.price) for node in nodes],
        mode="markers+text",
        marker={
            "symbol": marker_symbols,
            "size": 12,
            "color": marker_colors,
            "line": {"width": 1, "color": "#0b0e11"},
        },
        text=labels,
        textposition="top center",
        textfont={"size": 11},
        customdata=customdata,
        hovertemplate=(
            "%{text}"
            "<br>x=%{customdata[0]:.6f}"
            "<br>Trend price=%{y:.5f}"
            "<br>T'(x)=%{customdata[1]:.8g}"
            "<br>T''(x)=%{customdata[2]:.8g}"
            "<extra></extra>"
        ),
        name="Trend nodes",
        visible=visible,
        showlegend=False,
    )


def _node_marker_symbol(node_type: TrendNodeType) -> str:
    if node_type is TrendNodeType.MAXIMUM:
        return "triangle-down"
    if node_type is TrendNodeType.MINIMUM:
        return "triangle-up"
    return "diamond"


def _node_marker_color(node_type: TrendNodeType) -> str:
    if node_type is TrendNodeType.MAXIMUM:
        return "#ef5350"
    if node_type is TrendNodeType.MINIMUM:
        return "#26a69a"
    return "#ffd700"


def _decimal_point(value: Decimal) -> Decimal:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError("price must be finite")
    return Decimal(1).scaleb(exponent)


def _window_metadata(
    series: Mapping[tuple[str, Timeframe], Sequence[Candle]],
    z_windows: Mapping[tuple[str, Timeframe], ZCalculationWindow] | None,
    trend_fits: Mapping[tuple[str, Timeframe], CubicTrendFit] | None,
    node_counts: Mapping[tuple[str, Timeframe], int],
) -> dict[str, dict[str, str | int | bool]]:
    result: dict[str, dict[str, str | int | bool]] = {}
    if z_windows is None:
        return result

    for symbol, timeframe in series:
        key = (symbol, timeframe)
        window = z_windows.get(key)
        if window is None:
            continue

        status = "complete" if window.complete else "incomplete"
        fit = None if trend_fits is None else trend_fits.get(key)
        fit_label = ""
        if fit is not None:
            fit_label = f" · cubic points: {fit.point_count}"

        node_label = ""
        if fit is not None:
            node_label = f" · nodes: {node_counts.get(key, 0)}"

        result[_selection_key(symbol, timeframe)] = {
            "available": window.available_bars,
            "requested": window.requested_bars_after_z,
            "complete": window.complete,
            "label": (
                f"Z window: {window.available_bars}/"
                f"{window.requested_bars_after_z} bars ({status})"
                f"{fit_label}{node_label}"
            ),
        }

    return result


def _apply_layout(figure: go.Figure, *, title: str) -> None:
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
