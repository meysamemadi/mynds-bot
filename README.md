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

## Requirements

- Python 3.12
- Approved cTrader Open API application
- cTrader access token and account ID

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Create a local `.env` from `.env.example` and fill in the cTrader credentials. Never commit the real `.env` file.

## Run the chart

```powershell
python scripts/plot_ctrader_candles.py
```

The script authenticates with cTrader, requests EURUSD M1 trendbars, maps them to the domain `Candle` model, and opens an interactive Plotly candlestick chart in the browser.

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
