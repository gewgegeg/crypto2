## Arbitrage App (No Card P2P/CEX)

Minimal Python template for inter-exchange arbitrage without bank cards, inspired by P2P.Army and P2P Surfer.

### Features
- Connectors: ccxt for CEX (e.g., Binance, Kraken), custom Binance P2P client
- Live or mock data mode
- Simple two-exchange spread check with fees and transfer costs
- Skeleton for multi-leg (P2P → spot → transfer → sell)
- CLI with basic real-time snapshot (order books, opportunities)

### Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m arbitrage.ui.cli --symbol BTC/USDT --size 1000 --threshold 0.5 --mock
```

Use `--live` to fetch real data (internet required).

Environment variables (optional):
- `ARB_EXCHANGE_A` (default: binance)
- `ARB_EXCHANGE_B` (default: kraken)
- `ARB_P2P_FIAT` (default: USD)
- `ARB_NETWORK_PREF` (default: TRC20)
- `ARB_SPREAD_THRESHOLD_PCT` (default: 0.5)
- `ARB_TRADE_SIZE_USDT` (default: 1000)

### Disclaimer
This is a template for research and education. Real trading requires thorough testing, risk management, and compliance with local regulations.
