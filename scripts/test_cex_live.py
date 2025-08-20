from __future__ import annotations

import sys
from typing import List, Optional

import ccxt  # type: ignore


EXCHANGES: List[str] = [
    "okx",
    "kraken",
    "kucoin",
    # "bybit",  # region may block
    "gate",
    "bitget",
    "mexc",
    # "binance",  # region may block; uncomment to try
]

BASE_CANDIDATES = ["BTC", "ETH"]
QUOTE_CANDIDATES = ["USDT", "USD", "USDC"]
LIMIT_MAP = {
    "default": 10,
    "kucoin": 20,  # KuCoin requires 20 or 100
}


def find_spot_symbol(exchange: ccxt.Exchange, base_candidates: List[str], quote_candidates: List[str]) -> Optional[str]:
    markets = exchange.load_markets()
    # prefer spot markets
    for base in base_candidates:
        for quote in quote_candidates:
            sym = f"{base}/{quote}"
            market = markets.get(sym)
            if market and market.get("spot"):
                return sym
    # fallback to any available market matching candidates
    for base in base_candidates:
        for quote in quote_candidates:
            sym = f"{base}/{quote}"
            if sym in markets:
                return sym
    return None


def print_top_of_book(exchange_id: str, symbol: str, ob) -> None:
    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    print(f"{exchange_id:8} {symbol:11} bid={best_bid} ask={best_ask}")


def main() -> int:
    for ex_id in EXCHANGES:
        try:
            ex_class = getattr(ccxt, ex_id)
            ex = ex_class({"enableRateLimit": True})
            sym = find_spot_symbol(ex, BASE_CANDIDATES, QUOTE_CANDIDATES)
            if not sym:
                print(f"{ex_id:8} no suitable symbol found")
                continue
            limit = LIMIT_MAP.get(ex_id, LIMIT_MAP["default"])
            ob = ex.fetch_order_book(sym, limit=limit)
            print_top_of_book(ex_id, sym, ob)
        except Exception as e:
            print(f"{ex_id:8} error: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())