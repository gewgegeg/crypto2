from __future__ import annotations

import argparse
import logging
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
except Exception:
    Console = None  # type: ignore
    Table = None  # type: ignore

from arbitrage.config import get_settings
from arbitrage.models import Opportunity
from arbitrage.services import FeeService, Notifier
from arbitrage.strategies import find_cex_cex_opportunity, plan_multi_leg_path


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")


def render_order_book(table_title: str, bids, asks, limit: int = 5):
    if Console is None or Table is None:
        # Fallback simple text rendering
        lines = [f"== {table_title} =="]
        lines.append("ASKS:")
        for lvl in asks[:limit]:
            lines.append(f"  {lvl.price:.2f} x {lvl.amount:.4f}")
        lines.append("BIDS:")
        for lvl in bids[:limit]:
            lines.append(f"  {lvl.price:.2f} x {lvl.amount:.4f}")
        return "\n".join(lines)
    table = Table(title=table_title)
    table.add_column("Side")
    table.add_column("Price")
    table.add_column("Amount")

    for lvl in asks[:limit]:
        table.add_row("ASK", f"{lvl.price:.2f}", f"{lvl.amount:.4f}")
    for lvl in bids[:limit]:
        table.add_row("BID", f"{lvl.price:.2f}", f"{lvl.amount:.4f}")
    return table


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Arbitrage CLI")
    parser.add_argument("--symbol", default=None, help="Symbol (e.g., BTC/USDT)")
    parser.add_argument("--size", type=float, default=None, help="Trade size in USDT")
    parser.add_argument("--threshold", type=float, default=None, help="Min ROI %% to notify")
    parser.add_argument("--mock", action="store_true", help="Use mock data")
    parser.add_argument("--live", action="store_true", help="Use live APIs (overrides --mock)")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.symbol:
        settings.symbol = args.symbol
    if args.size is not None:
        settings.trade_size_usdt = args.size
    if args.threshold is not None:
        settings.spread_threshold_pct = args.threshold
    if args.live:
        settings.use_mock_data = False
    elif args.mock:
        settings.use_mock_data = True

    _setup_logging(settings.log_level)
    console = Console() if Console is not None else None

    base, quote = settings.symbol.split("/")

    notifier = Notifier()
    fee_service = FeeService()

    if settings.use_mock_data:
        from arbitrage.connectors.mock import MockDataClient  # lazy import

        mock = MockDataClient(settings.exchange_a, settings.exchange_b)
        book_a = mock.order_book_a(settings.symbol)
        book_b = mock.order_book_b(settings.symbol)
        fees_a = mock.trading_fees()
        fees_b = mock.trading_fees()

        ob_a = render_order_book(f"{book_a.exchange_id} {settings.symbol}", book_a.bids, book_a.asks)
        ob_b = render_order_book(f"{book_b.exchange_id} {settings.symbol}", book_b.bids, book_b.asks)
        if console:
            console.print(ob_a)
            console.print(ob_b)
        else:
            print(ob_a)
            print(ob_b)

        transfer_fee_in_base = 1.0 if base.upper() == "USDT" else 0.0
        opp: Optional[Opportunity] = find_cex_cex_opportunity(
            base_symbol=base,
            quote_symbol=quote,
            size_in_quote=settings.trade_size_usdt,
            book_a=book_a,
            book_b=book_b,
            fees_a=fees_a,
            fees_b=fees_b,
            threshold_pct=settings.spread_threshold_pct,
            transfer_fee_in_base=transfer_fee_in_base,
        )
        if opp:
            notifier.notify(f"[CEX_CEX] ROI {opp.expected_roi_pct:.2f}% | Profit ~{opp.expected_profit_usdt:.2f} {quote} | {opp.description}")

        # Multi-leg demo using mock P2P and b-side sell price
        p2p_buy = mock.p2p_buy_quotes(asset="USDT", fiat=settings.p2p_fiat)[0]
        sell_price_b = book_b.bids[0].price
        transfer_fee_asset = 1.0  # mock TRC20
        multi = plan_multi_leg_path(
            p2p_buy=p2p_buy,
            spot_buy_price=None,  # not used in this simplified USDT flow
            spot_buy_fees=fee_service.get_trading_fees(),
            transfer_fee_asset=transfer_fee_asset,
            spot_sell_price=sell_price_b,
            spot_sell_fees=fee_service.get_trading_fees(),
            size_in_fiat=settings.trade_size_usdt,
            fiat=settings.p2p_fiat,
            asset="USDT",
        )
        if multi and multi.expected_roi_pct >= settings.spread_threshold_pct:
            notifier.notify(f"[MULTI] ROI {multi.expected_roi_pct:.2f}% | Profit ~{multi.expected_profit_usdt:.2f} {settings.p2p_fiat} | {multi.description}")

    else:
        from arbitrage.connectors.cex import CcxtCexClient  # lazy import
        from arbitrage.connectors.p2p_binance import BinanceP2PClient  # lazy import

        cex_a = CcxtCexClient(settings.exchange_a)
        cex_b = CcxtCexClient(settings.exchange_b)
        p2p = BinanceP2PClient()

        book_a = cex_a.fetch_order_book(settings.symbol, limit=20)
        book_b = cex_b.fetch_order_book(settings.symbol, limit=20)
        fees_a = cex_a.fetch_trading_fees(settings.symbol)
        fees_b = cex_b.fetch_trading_fees(settings.symbol)

        ob_a = render_order_book(f"{book_a.exchange_id} {settings.symbol}", book_a.bids, book_a.asks)
        ob_b = render_order_book(f"{book_b.exchange_id} {settings.symbol}", book_b.bids, book_b.asks)
        if console:
            console.print(ob_a)
            console.print(ob_b)
        else:
            print(ob_a)
            print(ob_b)

        transfer_fee_in_base = 1.0 if base.upper() == "USDT" else 0.0
        opp = find_cex_cex_opportunity(
            base_symbol=base,
            quote_symbol=quote,
            size_in_quote=settings.trade_size_usdt,
            book_a=book_a,
            book_b=book_b,
            fees_a=fees_a,
            fees_b=fees_b,
            threshold_pct=settings.spread_threshold_pct,
            transfer_fee_in_base=transfer_fee_in_base,
        )
        if opp:
            notifier.notify(f"[CEX_CEX] ROI {opp.expected_roi_pct:.2f}% | Profit ~{opp.expected_profit_usdt:.2f} {quote} | {opp.description}")

        # Multi-leg demo in live mode: P2P buy USDT, transfer, sell on exchange B
        p2p_buy_quotes = p2p.fetch_quotes(asset="USDT", fiat=settings.p2p_fiat, trade_type="BUY", rows=5)
        p2p_buy = p2p_buy_quotes[0] if p2p_buy_quotes else None
        sell_price_b = book_b.bids[0].price if book_b.bids else None
        transfer_fee_asset = 1.0  # assume TRC20; replace with real fee service data per exchange/network
        multi = plan_multi_leg_path(
            p2p_buy=p2p_buy,
            spot_buy_price=None,
            spot_buy_fees=fee_service.get_trading_fees(fees_a),
            transfer_fee_asset=transfer_fee_asset,
            spot_sell_price=sell_price_b,
            spot_sell_fees=fee_service.get_trading_fees(fees_b),
            size_in_fiat=settings.trade_size_usdt,
            fiat=settings.p2p_fiat,
            asset="USDT",
        )
        if multi and multi.expected_roi_pct >= settings.spread_threshold_pct:
            notifier.notify(f"[MULTI] ROI {multi.expected_roi_pct:.2f}% | Profit ~{multi.expected_profit_usdt:.2f} {settings.p2p_fiat} | {multi.description}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())