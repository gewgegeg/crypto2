from __future__ import annotations

from typing import List

from arbitrage.models import OrderBook, PriceLevel, Ticker, P2PQuote, TradingFees


class MockDataClient:
    def __init__(self, exchange_a: str = "binance", exchange_b: str = "kraken") -> None:
        self.exchange_a = exchange_a
        self.exchange_b = exchange_b

    def order_book_a(self, symbol: str) -> OrderBook:
        # Simple book with tight spread
        bids = [PriceLevel(price=9990.0, amount=5.0), PriceLevel(price=9980.0, amount=10.0)]
        asks = [PriceLevel(price=10010.0, amount=5.0), PriceLevel(price=10020.0, amount=10.0)]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, exchange_id=self.exchange_a)

    def order_book_b(self, symbol: str) -> OrderBook:
        # Higher price to allow arbitrage (>0.5% after fees)
        bids = [PriceLevel(price=10120.0, amount=5.0), PriceLevel(price=10110.0, amount=10.0)]
        asks = [PriceLevel(price=10130.0, amount=5.0), PriceLevel(price=10140.0, amount=10.0)]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, exchange_id=self.exchange_b)

    def ticker_a(self, symbol: str) -> Ticker:
        return Ticker(symbol=symbol, best_bid=9990.0, best_ask=10010.0, exchange_id=self.exchange_a)

    def ticker_b(self, symbol: str) -> Ticker:
        return Ticker(symbol=symbol, best_bid=10120.0, best_ask=10130.0, exchange_id=self.exchange_b)

    def trading_fees(self) -> TradingFees:
        return TradingFees(maker_rate=0.001, taker_rate=0.001)

    def p2p_buy_quotes(self, asset: str = "USDT", fiat: str = "USD") -> List[P2PQuote]:
        # Price is fiat per asset; BUY means we buy USDT with fiat
        return [
            P2PQuote(asset=asset, fiat=fiat, trade_type="BUY", price=1.01, available_amount=5000.0, min_amount=10.0),
            P2PQuote(asset=asset, fiat=fiat, trade_type="BUY", price=1.02, available_amount=10000.0, min_amount=10.0),
        ]

    def p2p_sell_quotes(self, asset: str = "USDT", fiat: str = "USD") -> List[P2PQuote]:
        # SELL means we sell USDT for fiat
        return [
            P2PQuote(asset=asset, fiat=fiat, trade_type="SELL", price=1.03, available_amount=5000.0, min_amount=10.0),
            P2PQuote(asset=asset, fiat=fiat, trade_type="SELL", price=1.02, available_amount=10000.0, min_amount=10.0),
        ]