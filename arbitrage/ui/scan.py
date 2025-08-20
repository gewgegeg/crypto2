from __future__ import annotations

import argparse
import time
from typing import Dict, List, Optional, Tuple

from rich.live import Live
from rich.table import Table
from rich.console import Console

from arbitrage.connectors.cex import CcxtCexClient
from arbitrage.strategies import find_cex_cex_opportunity
from arbitrage.models import OrderBook


def find_common_symbols(ex_a: CcxtCexClient, ex_b: CcxtCexClient, quote: Optional[str]) -> List[str]:
    a_markets = ex_a.client.load_markets()
    b_markets = ex_b.client.load_markets()
    a_syms = {s for s, m in a_markets.items() if m.get("spot")}
    b_syms = {s for s, m in b_markets.items() if m.get("spot")}
    common = a_syms & b_syms
    if quote and quote.upper() not in {"ANY", "*"}:
        common = {s for s in common if s.endswith(f"/{quote}")}
    return sorted(common)


def fetch_quote_volumes(exchange: CcxtCexClient, symbols: List[str]) -> Dict[str, float]:
    volumes: Dict[str, float] = {}
    try:
        # Try batched fetch_tickers if supported
        tickers = None
        try:
            tickers = exchange.client.fetch_tickers(symbols)
        except Exception:
            tickers = exchange.client.fetch_tickers()
        for sym in symbols:
            t = tickers.get(sym) if isinstance(tickers, dict) else None
            if t:
                qv = t.get("quoteVolume") or (t.get("info", {}) or {}).get("quoteVolume")
                if qv is not None:
                    try:
                        volumes[sym] = float(qv)
                    except Exception:
                        pass
    except Exception:
        pass
    return volumes


def build_table(rows: List[Tuple[str, float, float, float, float]]) -> Table:
    table = Table(title="Live Arbitrage Scanner")
    table.add_column("Symbol")
    table.add_column("ExA Ask", justify="right")
    table.add_column("ExB Bid", justify="right")
    table.add_column("ROI %", justify="right")
    table.add_column("Profit", justify="right")
    for sym, ask_a, bid_b, roi, profit in rows:
        table.add_row(sym, f"{ask_a:.4f}", f"{bid_b:.4f}", f"{roi:.2f}", f"{profit:.2f}")
    return table


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-symbol live arbitrage scanner")
    parser.add_argument("--ex-a", required=True, help="Primary CEX id (ccxt id), e.g., okx")
    parser.add_argument("--ex-b", required=True, help="Secondary CEX id (ccxt id), e.g., kraken")
    parser.add_argument("--quote", default="USDT", help="Quote currency to filter symbols (e.g., USDT). Use ANY for all")
    parser.add_argument("--limit", type=int, default=50, help="Max number of symbols to scan")
    parser.add_argument("--size", type=float, default=1000.0, help="Trade size in quote to simulate profit")
    parser.add_argument("--threshold", type=float, default=0.5, help="Min ROI percent to display")
    parser.add_argument("--interval", type=float, default=3.0, help="Refresh interval seconds")
    parser.add_argument("--transfer-fee", type=float, default=0.0, help="Transfer fee in base units")
    parser.add_argument("--min-volume", type=float, default=0.0, help="Min 24h quote volume to include (per exchange)")
    parser.add_argument("--top", type=int, default=30, help="Show top-N rows by ROI")

    args = parser.parse_args(argv)

    console = Console()
    ex_a = CcxtCexClient(args.ex_a)
    ex_b = CcxtCexClient(args.ex_b)

    console.print(f"Loading markets for {args.ex_a} and {args.ex_b}...")
    symbols = find_common_symbols(ex_a, ex_b, args.quote)
    if not symbols:
        console.print("No common symbols found")
        return 1

    # Volume filter
    if args.min_volume > 0:
        vols_a = fetch_quote_volumes(ex_a, symbols)
        vols_b = fetch_quote_volumes(ex_b, symbols)
        filtered = []
        for s in symbols:
            va = vols_a.get(s, 0.0)
            vb = vols_b.get(s, 0.0)
            if va >= args.min_volume and vb >= args.min_volume:
                filtered.append(s)
        symbols = filtered or symbols

    symbols = symbols[: args.limit]

    with Live(build_table([]), refresh_per_second=4, console=console) as live:
        while True:
            rows: List[Tuple[str, float, float, float, float]] = []
            for sym in symbols:
                try:
                    book_a: OrderBook = ex_a.fetch_order_book(sym, limit=20)
                    book_b: OrderBook = ex_b.fetch_order_book(sym, limit=20)
                    if not book_a.asks or not book_b.bids:
                        continue
                    base, quote = sym.split("/")
                    opp = find_cex_cex_opportunity(
                        base_symbol=base,
                        quote_symbol=quote,
                        size_in_quote=args.size,
                        book_a=book_a,
                        book_b=book_b,
                        fees_a=ex_a.fetch_trading_fees(sym),
                        fees_b=ex_b.fetch_trading_fees(sym),
                        threshold_pct=args.threshold,
                        transfer_fee_in_base=args.transfer_fee,
                    )
                    ask_a = book_a.asks[0].price
                    bid_b = book_b.bids[0].price
                    roi = opp.expected_roi_pct if opp else 0.0
                    profit = opp.expected_profit_usdt if opp else 0.0
                    if roi >= args.threshold:
                        rows.append((sym, ask_a, bid_b, roi, profit))
                except Exception:
                    continue
            rows.sort(key=lambda r: r[3], reverse=True)
            rows = rows[: args.top]
            live.update(build_table(rows))
            time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())