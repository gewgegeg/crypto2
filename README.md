## Arbitrage App (No Card P2P/CEX)

Minimal Python template for inter-exchange arbitrage without bank cards, inspired by P2P.Army and P2P Surfer.

### Features
- Connectors: ccxt for CEX (e.g., Binance, Kraken), custom Binance P2P client
- Live or mock data mode
- Simple two-exchange spread check with fees and transfer costs
- Skeleton for multi-leg (P2P → spot → transfer → sell)
- CLI with basic real-time snapshot (order books, opportunities)
- Web UI (FastAPI) with order books, one-pair opportunity, and multi-exchange scanner

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

### Web UI
- Start server:
```bash
python -m uvicorn arbitrage.web.app:app --host 127.0.0.1 --port 8000
```
- Open http://127.0.0.1:8000
- Controls:
  - Order books + one-pair opportunity (pick Ex A, Ex B, symbol, size, threshold, transfer fee)
  - Multi-Exchange Scanner: choose exchanges, quotes (ANY for all), bases or CMC preset, size/threshold, top-N

### CLI (live)
```bash
python -m arbitrage.ui.cli --symbol BTC/USDT --size 1000 --threshold 0.5 --live --ex-a okx --ex-b kraken
```

### Multi-exchange scanner (CLI)
```bash
python -m arbitrage.ui.mega_scan \
  --ex-list okx,kraken,kucoin,gate,bitget,mexc,coinex,poloniex,lbank,xt,whitebit,bitmart,phemex,btse,ascendex,probit,digifinex,bittrex,hitbtc,huobi,bitstamp,bitvavo,bitrue,bkex,deepcoin,zb,coinone,korbit,bitfinex,indodax,wazirx,okcoin,coincheck,coinsph,tidex,paribu \
  --exclude bybit,binance \
  --quotes ANY \
  --preset CMC_TOP200 \
  --limit-symbols 800 \
  --size 1000 \
  --threshold 0.2 \
  --top 80 \
  --interval 4 \
  --workers 48 \
  --skip-stables \
  --enforce-lots \
  --export snapshot.csv
```

### Disclaimer
This is a template for research and education. Real trading requires thorough testing, risk management, and compliance with local regulations.
