from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from arbitrage.connectors.cex import CcxtCexClient
from arbitrage.models import OrderBook
from arbitrage.services.universe import get_cmc_top_bases


STABLES: Set[str] = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI"}


@dataclass
class MarketLimits:
    min_amount: float = 0.0
    min_cost: float = 0.0


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


def fetch_exchange_volumes(client: CcxtCexClient, symbols: List[str]) -> Dict[str, float]:
    volumes: Dict[str, float] = {}
    try:
        tickers = None
        try:
            tickers = client.client.fetch_tickers(symbols)
        except Exception:
            tickers = client.client.fetch_tickers()
        for sym in symbols:
            t = tickers.get(sym) if isinstance(tickers, dict) else None
            if not t:
                continue
            qv = t.get("quoteVolume") or (t.get("info", {}) or {}).get("quoteVolume")
            if qv is not None:
                try:
                    volumes[sym] = float(qv)
                except Exception:
                    pass
    except Exception:
        pass
    return volumes


def get_market_limits(client: CcxtCexClient, symbol: str) -> MarketLimits:
    try:
        markets = client.client.load_markets()
        m = markets.get(symbol)
        if not m:
            return MarketLimits()
        limits = m.get("limits", {}) or {}
        amount = (limits.get("amount", {}) or {}).get("min") or 0.0
        cost = (limits.get("cost", {}) or {}).get("min") or 0.0
        return MarketLimits(
            min_amount=float(amount) if amount else 0.0,
            min_cost=float(cost) if cost else 0.0,
        )
    except Exception:
        return MarketLimits()


def get_bases_from_preset(preset: str) -> Set[str]:
    if preset.startswith("CMC_TOP"):
        try:
            topn = int(preset.replace("CMC_TOP", ""))
        except Exception:
            topn = 100
        return set(get_cmc_top_bases(limit=topn))
    return set()


def scan_symbols_once(
    clients: Dict[str, CcxtCexClient],
    ex_symbols: Dict[str, Set[str]],
    symbols: List[str],
    size: float,
    threshold: float,
    workers: int,
    min_volume: float,
    enforce_lots: bool,
) -> List[Tuple[str, str, float, str, float, float, float]]:
    rows: List[Tuple[str, str, float, str, float, float, float]] = []

    # Pre-fetch volumes and market limits per exchange for provided symbols
    ex_vols: Dict[str, Dict[str, float]] = {}
    ex_limits: Dict[str, Dict[str, MarketLimits]] = {}

    for ex_id, client in clients.items():
        ex_vols[ex_id] = fetch_exchange_volumes(client, symbols)
        ex_limits[ex_id] = {}
        for sym in symbols:
            ex_limits[ex_id][sym] = get_market_limits(client, sym)

    for sym in symbols:
        futures = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
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

        # Volume filters on the chosen exchanges
        if min_volume > 0:
            va = ex_vols.get(best_ask_ex or "", {}).get(sym, 0.0)
            vb = ex_vols.get(best_bid_ex or "", {}).get(sym, 0.0)
            if va < min_volume or vb < min_volume:
                continue

        # Lot/cost filters
        if enforce_lots:
            base_amount = size / best_ask_val
            la = ex_limits.get(best_ask_ex or "", {}).get(sym, MarketLimits())
            lb = ex_limits.get(best_bid_ex or "", {}).get(sym, MarketLimits())
            # Check buy side on ask exchange
            if la.min_amount and base_amount < la.min_amount:
                continue
            if la.min_cost and size < la.min_cost:
                continue
            # Check sell side on bid exchange
            if lb.min_amount and base_amount < lb.min_amount:
                continue

        # ROI and profit
        cost = size
        base_amount = size / best_ask_val
        proceeds = best_bid_val * base_amount
        profit = proceeds - cost
        roi = 100.0 * profit / cost if cost > 0 else 0.0
        if roi >= threshold:
            rows.append((sym, best_ask_ex or "?", best_ask_val, best_bid_ex or "?", best_bid_val, roi, profit))

    return rows