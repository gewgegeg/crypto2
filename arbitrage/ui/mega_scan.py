from __future__ import annotations

import argparse
import time
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.live import Live
from rich.table import Table

from arbitrage.connectors.cex import CcxtCexClient
from arbitrage.models import OrderBook
from arbitrage.services.universe import get_cmc_top_bases


DEFAULT_EXCHANGES: List[str] = [
    "okx", "kraken", "kucoin", "gate", "bitget", "mexc", "coinex", "poloniex",
    "lbank", "xt", "whitebit", "bitmart", "phemex", "btse", "ascendex", "probit",
    "digifinex", "bittrex", "hitbtc", "huobi", "bitstamp", "bitvavo", "upbit",
    "bitrue", "bkex", "bybit", "binance", "bingx", "deepcoin", "xts", "zb",
    "coinone", "korbit", "bitfinex", "indodax", "wazirx", "okcoin", "coincheck",
    "coinsph", "tidex", "paribu",
]
# Some may be region-blocked or not available; scanner skips on errors

STABLES: Set[str] = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI"}


def build_exchanges(ids: List[str], exclude: Set[str]) -> Dict[str, CcxtCexClient]:
    clients: Dict[str, CcxtCexClient] = {}
    for ex_id in ids:
        if ex_id in exclude:
            continue
        try:
            clients[ex_id] = CcxtCexClient(ex_id)
        except Exception:
            continue
    return clients


def load_spot_symbols(client: CcxtCexClient) -> Set[str]:
    try:
        markets = client.client.load_markets()
        return {s for s, m in markets.items() if m.get("spot")}
    except Exception:
        return set()


def filter_symbols(
    symbols: Set[str],
    quotes: Optional[Set[str]],
    bases_allow: Optional[Set[str]],
    skip_pure_stables: bool,
) -> Set[str]:
    out: Set[str] = set()
    for s in symbols:
        try:
            base, quote = s.split("/")
        except Exception:
            continue
        if skip_pure_stables and base in STABLES and quote in STABLES:
            continue
        if quotes and (quotes != {"ANY"} and quotes != {"*"}) and quote not in quotes:
            continue
        if bases_allow and base not in bases_allow:
            continue
        out.add(s)
    return out


def fetch_best_levels(client: CcxtCexClient, symbol: str) -> Tuple[Optional[float], Optional[float]]:
    try:
        ob: OrderBook = client.fetch_order_book(symbol, limit=10)
        best_ask = ob.asks[0].price if ob.asks else None
        best_bid = ob.bids[0].price if ob.bids else None
        return best_ask, best_bid
    except Exception:
        return None, None


def build_table(rows: List[Tuple[str, str, float, str, float, float, float]]) -> Table:
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
    parser.add_argument("--min-volume", type=float, default=0.0, help="Reserved for future per-ex volume filter")
    parser.add_argument("--interval", type=float, default=4.0, help="Refresh seconds")
    parser.add_argument("--top", type=int, default=50, help="Top rows by ROI")
    parser.add_argument("--workers", type=int, default=32, help="Max parallel requests")
    parser.add_argument("--skip-stables", action="store_true", help="Skip pure stable-stable pairs")

    args = parser.parse_args(argv)
    console = Console()

    ex_list = [e.strip() for e in args.ex_list.split(",") if e.strip()]
    exclude = {e.strip() for e in args.exclude.split(",") if e.strip()}
    quotes = {q.strip().upper() for q in args.quotes.split(",")} if args.quotes else {"USDT"}

    bases_allow: Optional[Set[str]] = None
    if args.bases:
        bases_allow = {b.strip().upper() for b in args.bases.split(",") if b.strip()}
    elif args.preset.startswith("CMC_TOP"):
        try:
            topn = int(args.preset.replace("CMC_TOP", ""))
        except Exception:
            topn = 100
        bases_allow = set(get_cmc_top_bases(limit=topn))

    console.print(f"Building {len(ex_list)} exchanges (excluding: {', '.join(sorted(exclude)) or 'none'})...")
    clients = build_exchanges(ex_list, exclude)
    if not clients:
        console.print("No exchanges available")
        return 1

    # Load symbols per exchange
    ex_symbols: Dict[str, Set[str]] = {}
    for ex_id, client in clients.items():
        ex_symbols[ex_id] = filter_symbols(load_spot_symbols(client), quotes, bases_allow, args.skip_stables)

    # Candidate symbols: present on >= 2 exchanges
    symbol_counts: Dict[str, int] = {}
    for syms in ex_symbols.values():
        for s in syms:
            symbol_counts[s] = symbol_counts.get(s, 0) + 1
    symbols = [s for s, c in symbol_counts.items() if c >= 2]
    symbols.sort()
    symbols = symbols[: args.limit_symbols]

    console.print(f"Scanning {len(symbols)} symbols across {len(clients)} exchanges...")

    with Live(build_table([]), refresh_per_second=4, console=console) as live:
        while True:
            rows: List[Tuple[str, str, float, str, float, float, float]] = []
            for sym in symbols:
                # fetch best levels across exchanges in parallel
                futures = {}
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    for ex_id, client in clients.items():
                        if sym not in ex_symbols.get(ex_id, set()):
                            continue
                        futures[pool.submit(fetch_best_levels, client, sym)] = ex_id
                    best_ask_val: Optional[float] = None
                    best_ask_ex: Optional[str] = None
                    best_bid_val: Optional[float] = None
                    best_bid_ex: Optional[str] = None
                    for fut in as_completed(futures):
                        ex_id = futures[fut]
                        ask, bid = fut.result()
                        if ask is not None and (best_ask_val is None or ask < best_ask_val):
                            best_ask_val = ask
                            best_ask_ex = ex_id
                        if bid is not None and (best_bid_val is None or bid > best_bid_val):
                            best_bid_val = bid
                            best_bid_ex = ex_id
                if best_ask_val is None or best_bid_val is None:
                    continue
                if best_ask_ex == best_bid_ex:
                    continue
                # ROI and profit
                cost = args.size
                base_amount = cost / best_ask_val
                proceeds = best_bid_val * base_amount
                profit = proceeds - cost
                roi = 100.0 * profit / cost if cost > 0 else 0.0
                if roi >= args.threshold:
                    rows.append((sym, best_ask_ex or "?", best_ask_val, best_bid_ex or "?", best_bid_val, roi, profit))
            rows.sort(key=lambda r: r[5], reverse=True)
            rows = rows[: args.top]
            live.update(build_table(rows))
            time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())