# MyNDS Bot

Event-driven trading engine built with Python and cTrader Open API.

## Responsibilities

The Python application is responsible for:

- Receiving market data from cTrader Open API
- Validating and processing candles
- Running NDS calculations
- Managing signals and risk
- Providing REST and WebSocket APIs for a Next.js frontend

The Next.js application is responsible for visualization and user interfaces.

## Requirements

- Python 3.12
- Approved cTrader Open API application

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"