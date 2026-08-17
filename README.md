# MyNDS Bot

Python market-data pipeline focused on cTrader and Plotly.

## Current scope

```text
cTrader Open API
      ↓
Historical Trendbars
      ↓
Local History Cache
      ↓
Domain Candle
      ↓
Bull Z (NodeCounterv2 contract)
      ↓
Z Calculation Window (Z+1 ... Z+200)
      ↓
Plotly Candlestick Chart
```

REST APIs, WebSockets, and frontend work are intentionally out of scope for now.

## Chart controls

The generated Plotly page can switch between:

- Symbols: `GOLD`, `DOW`
- Timeframes: `M1`, `M3`, `M15`, `H1`

All eight symbol/timeframe combinations are loaded into one browser page, so switching in the chart does not make another API request.

## Bull Z contract

Bull Z is ported from `meysamemadi/NodeCounterv2` and intentionally follows its `FindBullZAnchor` behavior.
The reference implementation inspected for this port was NodeCounterv2 `main` tree commit `42efd985ee849d000f3e603feddb4f9db66d32e3`.

Rules:

1. Only closed candles participate in Z calculation.
2. The active reference is the highest High in the latest 200 closed candles.
3. Equal reference Highs use the newest candle.
4. Starting immediately before the reference, scan left for the nearest older High strictly greater than the reference High.
5. If that boundary exists, search for Z from `boundary + 1` through the reference candle. The boundary candle itself is excluded.
6. If no older High is strictly greater, use ATH mode and search from the beginning of the loaded history through the reference candle.
7. Z is the lowest Low in that search range.
8. Equal Lows use the newest candle.

The chart renders `Z` in gold below its candle. The visual offset mirrors NodeCounterv2: `max(35% of candle size, 15 points)`.

The domain also contains NodeCounterv2-compatible manual-time Z resolution, but the current chart uses automatic Bull Z selection.

Because the left-boundary search can scan to the beginning of loaded history, increasing historical depth can change an ATH-mode result if an older higher High becomes available.

## Z calculation window

Downstream calculations now use an explicit bounded window after Z.
The default is 200 closed candles after Z:

```text
Z | Z+1 ... Z+200
```

Z itself is not counted. This matches the range convention used by NodeCounterv2.
If fewer than 200 closed candles exist after Z, the window is marked incomplete and contains only the available candles.

The chart shows:

- the gold `Z` marker at the anchor;
- a `Z+200` end marker when the full window is available;
- or `Z+N` when only N post-Z candles are currently available.

The top bar also shows the current window status.

## Historical candle depth and cache

The default target is 5,000 candles for every symbol/timeframe combination.
Set the target in `.env`:

```dotenv
CTRADER_HISTORY_CANDLE_COUNT=5000
```

Historical data is downloaded in chunks of up to 1,000 candles.
The first run builds a local cache under:

```text
data/history/
```

Cache files are ignored by Git.

On later runs, each series is loaded from the local cache first and normally needs only one recent cTrader refresh chunk. If the cache is old enough that the new chunk does not overlap it, the downloader automatically walks backward until the gap is bridged before using the merged history.

This keeps the Z history continuous while making repeated runs much faster than downloading all 5,000 candles for all eight chart series every time.

Remember that all eight datasets are embedded in the generated Plotly HTML page. Very large history targets can therefore increase HTML size, memory usage, and browser rendering cost.

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

The script authenticates with cTrader, loads/refreshes historical candles, maps trendbars to the domain `Candle` model, calculates Bull Z on closed candles, builds the bounded post-Z calculation window, writes `artifacts/ctrader_candles.html`, and opens it in the browser.

Use the sidebar buttons to switch between symbols and timeframes.

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
src/nds_bot/infrastructure/market_data/history_cache.py
    ↓
src/nds_bot/domain/market/candle.py
    ↓
src/nds_bot/domain/market/z.py
    ↓
src/nds_bot/infrastructure/visualization/plotly_candles.py
```
