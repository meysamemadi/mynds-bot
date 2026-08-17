# MyNDS Bot

Python market-data pipeline focused on cTrader and Plotly.

## Current scope

```text
cTrader Open API
      ↓
Historical Trendbars
      ↓
Domain Candle
      ↓
Plotly Candlestick Chart
```

REST APIs, WebSockets, and frontend work are intentionally out of scope for now.

## Chart controls

The generated Plotly page can switch between:

- Symbols: `GOLD`, `DOW`
- Timeframes: `M1`, `M3`, `M15`, `H1`

All eight symbol/timeframe combinations are fetched from cTrader first and then loaded into one browser page, so switching in the chart does not make another API request.

## Requirements

- Python 3.12
- Approved cTrader Open API application
- cTrader access token and account ID
- Broker-specific cTrader symbol IDs for Gold and Dow Jones

cTrader symbol IDs are server/broker specific, so do not copy IDs from another broker.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Create a local `.env` from `.env.example` and fill in the cTrader credentials. Never commit the real `.env` file.

## Discover Gold and Dow symbol IDs

Run:

```powershell
python scripts/discover_ctrader_chart_symbols.py
```

The script prints likely Gold and Dow Jones candidates from the symbols available to the authenticated account. Put the selected IDs in `.env`:

```dotenv
CTRADER_GOLD_SYMBOL_ID=<gold-id>
CTRADER_DOW_SYMBOL_ID=<dow-id>
```

Common broker names may look like `XAUUSD` for Gold and `US30`/`DJ30` for Dow Jones, but the actual name and ID depend on the broker.

## Run the switchable chart

```powershell
python scripts/plot_ctrader_candles.py
```

The script authenticates with cTrader, loads metadata for Gold and Dow, requests 200 candles for each of `M1`, `M3`, `M15`, and `H1`, maps every trendbar to the domain `Candle` model, writes `artifacts/ctrader_candles.html`, and opens it in the browser.

Use the Symbol and Timeframe selectors above the Plotly chart to switch between datasets.

## Quality checks

```powershell
python -m pytest
python -m ruff check .
python -m mypy src
```

## Main code path

```text
scripts/plot_ctrader_candles.py
    ↓
src/nds_bot/infrastructure/market_data/ctrader/trendbar_mapper.py
    ↓
src/nds_bot/domain/market/candle.py
    ↓
src/nds_bot/infrastructure/visualization/plotly_candles.py
```
