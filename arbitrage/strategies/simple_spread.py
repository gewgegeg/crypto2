from __future__ import annotations

from typing import Optional

from arbitrage.models import OrderBook, Opportunity, TradingFees


def _executable_price(order_book: OrderBook, side: str, size: float) -> Optional[float]:
    remaining = size
    cost = 0.0
    if side == "buy":
        for level in order_book.asks:
            take = min(level.amount, remaining)
            cost += take * level.price
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            return None
        return cost / size
    else:
        # sell side uses bids
        proceeds = 0.0
        for level in order_book.bids:
            take = min(level.amount, remaining)
            proceeds += take * level.price
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            return None
        return proceeds / size


def _apply_taker_fee(unit_price: float, size: float, fees: TradingFees, side: str) -> float:
    if side == "buy":
        return unit_price * (1 + fees.taker_rate)
    else:
        return unit_price * (1 - fees.taker_rate)


def find_cex_cex_opportunity(
    base_symbol: str,
    quote_symbol: str,
    size_in_quote: float,
    book_a: OrderBook,
    book_b: OrderBook,
    fees_a: TradingFees,
    fees_b: TradingFees,
    threshold_pct: float = 0.5,
    transfer_fee_in_base: float = 0.0,
) -> Optional[Opportunity]:
    # Buy base on A with quote, transfer base, and sell on B back to quote
    # Estimate base size from quote notional and top of book ask, then refine via average buy price
    approx_base_size = size_in_quote / max(book_a.asks[0].price, 1e-9)
    buy_avg_price_a = _executable_price(book_a, side="buy", size=approx_base_size)
    if buy_avg_price_a is None:
        return None

    base_amount = size_in_quote / buy_avg_price_a
    buy_unit_cost_with_fee = _apply_taker_fee(buy_avg_price_a, base_amount, fees_a, side="buy")

    # Deduct transfer fee in base units
    base_after_transfer = max(base_amount - transfer_fee_in_base, 0.0)
    if base_after_transfer <= 0:
        return None

    sell_avg_price_b = _executable_price(book_b, side="sell", size=base_after_transfer)
    if sell_avg_price_b is None:
        return None
    sell_unit_price_with_fee = _apply_taker_fee(sell_avg_price_b, base_after_transfer, fees_b, side="sell")

    # Net result in quote: proceeds - cost
    cost_quote = buy_unit_cost_with_fee * base_amount
    proceeds_quote = sell_unit_price_with_fee * base_after_transfer

    profit = proceeds_quote - cost_quote
    roi_pct = 100.0 * (profit / cost_quote) if cost_quote > 0 else 0.0

    if roi_pct >= threshold_pct:
        description = (
            f"Buy {base_symbol} on {book_a.exchange_id} at ~{buy_avg_price_a:.2f}, "
            f"transfer (-{transfer_fee_in_base} {base_symbol}), sell on {book_b.exchange_id} at ~{sell_avg_price_b:.2f}; "
            f"size {base_after_transfer:.6f} {base_symbol}"
        )
        return Opportunity(
            kind="CEX_CEX",
            description=description,
            expected_profit_usdt=profit,
            expected_roi_pct=roi_pct,
            legs=[
                f"BUY {base_symbol} with {quote_symbol} on {book_a.exchange_id}",
                f"TRANSFER {base_symbol} (-{transfer_fee_in_base} fee)",
                f"SELL {base_symbol} for {quote_symbol} on {book_b.exchange_id}",
            ],
        )
    return None