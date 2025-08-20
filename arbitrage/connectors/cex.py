from __future__ import annotations

from typing import Dict, Optional

import ccxt  # type: ignore

from arbitrage.models import OrderBook, PriceLevel, Ticker, TradingFees


class CcxtCexClient:
    def __init__(self, exchange_id: str, enable_rate_limit: bool = True) -> None:
        self.exchange_id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        self.client = exchange_class({
            "enableRateLimit": enable_rate_limit,
        })

    async def close(self) -> None:
        # ccxt sync client - nothing to close, placeholder for future async
        return None

    def fetch_ticker(self, symbol: str) -> Ticker:
        t = self.client.fetch_ticker(symbol)
        best_bid = float(t.get("bid") or t["info"].get("bidPrice") or 0.0)
        best_ask = float(t.get("ask") or t["info"].get("askPrice") or 0.0)
        return Ticker(symbol=symbol, best_bid=best_bid, best_ask=best_ask, exchange_id=self.exchange_id)

    def fetch_order_book(self, symbol: str, limit: int = 20) -> OrderBook:
        ob = self.client.fetch_order_book(symbol, limit=limit)
        bids = [PriceLevel(price=float(p), amount=float(a)) for p, a in ob.get("bids", [])]
        asks = [PriceLevel(price=float(p), amount=float(a)) for p, a in ob.get("asks", [])]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, exchange_id=self.exchange_id)

    def fetch_trading_fees(self, symbol: Optional[str] = None) -> TradingFees:
        # Try modern ccxt fee API, fallback to defaults if not supported
        maker = 0.001
        taker = 0.001
        try:
            fees: Dict = self.client.fetch_trading_fees()
            if symbol and symbol in fees:
                entry = fees[symbol]
                maker = float(entry.get("maker", maker))
                taker = float(entry.get("taker", taker))
            else:
                # Take average across markets if available
                if fees:
                    makers = [float(v.get("maker", maker)) for v in fees.values() if isinstance(v, dict)]
                    takers = [float(v.get("taker", taker)) for v in fees.values() if isinstance(v, dict)]
                    if makers:
                        maker = sum(makers) / len(makers)
                    if takers:
                        taker = sum(takers) / len(takers)
        except Exception:
            pass
        return TradingFees(maker_rate=maker, taker_rate=taker)