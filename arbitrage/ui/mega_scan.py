from __future__ import annotations

import argparse
import csv
import time
from typing import Dict, List, Optional, Set

from rich.console import Console
from rich.live import Live

from arbitrage.services.mega_core import (
    build_exchanges,
    load_spot_symbols,
    filter_symbols,
    get_bases_from_preset,
    scan_symbols_once,
)


DEFAULT_EXCHANGES: List[str] = [
    "okx", "kraken", "kucoin", "gate", "bitget", "mexc", "coinex", "poloniex",
    "lbank", "xt", "whitebit", "bitmart", "phemex", "btse", "ascendex", "probit",
    "digifinex", "bittrex", "hitbtc", "huobi", "bitstamp", "bitvavo", "bitrue", "bkex",
    "deepcoin", "zb", "coinone", "korbit", "bitfinex", "indodax", "wazirx", "okcoin",
    "coincheck", "coinsph", "tidex", "paribu",
]


def build_table(rows):
    from rich.table import Table
    table = Table(title="Multi-Exchange Arbitrage Scanner")
    table.add_column("Symbol")
    table.add_column("Best Ask Ex")
    table.add_column("Best Ask", justify="right")
    table.add_column("Best Bid Ex")
    table.add_column("Best Bid", justify="right")
    table.add_column("ROI %", justify="right")
    table.add_column("Profit", justify="right")
    for sym, ex_ask, ask, ex_bid, bid, roi, profit in rows:
        table.add_row(sym, ex_ask, f"{ask:.4f}", ex_bid, f"{bid:.4f}", f"{roi:.2f}", f"{profit:.2f}")
    return table


def maybe_export_csv(path: Optional[str], rows) -> None:
    if not path:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "ask_exchange", "ask", "bid_exchange", "bid", "roi_pct", "profit"])
        for r in rows:
            w.writerow(r)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scan arbitrage across many exchanges and symbols")
    parser.add_argument("--ex-list", default=",".join(DEFAULT_EXCHANGES), help="Comma-separated exchange ids (ccxt)")
    parser.add_argument("--exclude", default="bybit,binance", help="Comma-separated exchanges to exclude (region blocks)")
    parser.add_argument("--quotes", default="USDT", help="Comma-separated quotes or ANY")
    parser.add_argument("--bases", default="", help="Comma-separated bases to include; empty uses preset")
    parser.add_argument("--preset", default="CMC_TOP100", help="CMC_TOPN or NONE")
    parser.add_argument("--limit-symbols", type=int, default=500, help="Limit number of symbols to scan")
    parser.add_argument("--size", type=float, default=1000.0, help="Quote size to simulate profit")
    parser.add_argument("--threshold", type=float, default=0.5, help="Min ROI percent to display")
    parser.add_argument("--min-volume", type=float, default=0.0, help="Min 24h quote volume on both exchanges")
    parser.add_argument("--interval", type=float, default=4.0, help="Refresh seconds")
    parser.add_argument("--top", type=int, default=50, help="Top rows by ROI")
    parser.add_argument("--workers", type=int, default=32, help="Max parallel requests")
    parser.add_argument("--skip-stables", action="store_true", help="Skip pure stable-stable pairs")
    parser.add_argument("--export", default="", help="Export last snapshot to CSV path")
    parser.add_argument("--enforce-lots", action="store_true", help="Respect min lot and min cost per exchange")

    args = parser.parse_args(argv)
    console = Console()

    ex_list = [e.strip() for e in args.ex_list.split(",") if e.strip()]
    exclude = {e.strip() for e in args.exclude.split(",") if e.strip()}
    quotes = {q.strip().upper() for q in args.quotes.split(",")} if args.quotes else {"USDT"}

    bases_allow: Optional[Set[str]] = None
    if args.bases:
        bases_allow = {b.strip().upper() for b in args.bases.split(",") if b.strip()}
    else:
        bases_allow = get_bases_from_preset(args.preset)

    console.print(f"Building {len(ex_list)} exchanges (excluding: {', '.join(sorted(exclude)) or 'none'})...")
    clients = build_exchanges(ex_list, exclude)
    if not clients:
        console.print("No exchanges available")
        return 1

    ex_symbols: Dict[str, Set[str]] = {}
    for ex_id, client in clients.items():
        ex_symbols[ex_id] = filter_symbols(load_spot_symbols(client), quotes, bases_allow, args.skip_stables)

    symbol_counts: Dict[str, int] = {}
    for syms in ex_symbols.values():
        for s in syms:
            symbol_counts[s] = symbol_counts.get(s, 0) + 1
    symbols = [s for s, c in symbol_counts.items() if c >= 2]
    symbols.sort()
    symbols = symbols[: args.limit_symbols]

    console.print(f"Scanning {len(symbols)} symbols across {len(clients)} exchanges...")

    last_rows = []
    with Live(build_table([]), refresh_per_second=4, console=console) as live:
        while True:
            rows = scan_symbols_once(
                clients=clients,
                ex_symbols=ex_symbols,
                symbols=symbols,
                size=args.size,
                threshold=args.threshold,
                workers=args.workers,
                min_volume=args.min_volume,
                enforce_lots=args.enforce_lots,
            )
            rows.sort(key=lambda r: r[5], reverse=True)
            last_rows = rows[: args.top]
            live.update(build_table(last_rows))
            if args.export:
                maybe_export_csv(args.export, last_rows)
            time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())