from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from arbitrage.connectors.cex import CcxtCexClient
from arbitrage.strategies import find_cex_cex_opportunity
from arbitrage.models import OrderBook
from arbitrage.services.mega_core import (
    build_exchanges,
    load_spot_symbols,
    filter_symbols,
    get_bases_from_preset,
    scan_symbols_once,
)

app = FastAPI(title="Arbitrage Web")


@app.get("/api/orderbook")
def api_orderbook(ex: str, symbol: str, limit: int = 20):
    cex = CcxtCexClient(ex)
    ob: OrderBook = cex.fetch_order_book(symbol, limit=limit)
    return {
        "exchange": ex,
        "symbol": symbol,
        "bids": [{"price": l.price, "amount": l.amount} for l in ob.bids],
        "asks": [{"price": l.price, "amount": l.amount} for l in ob.asks],
    }


@app.get("/api/opportunity")
def api_opportunity(ex_a: str, ex_b: str, symbol: str, size: float = 1000.0, threshold: float = 0.5, transfer_fee: float = 0.0):
    cex_a = CcxtCexClient(ex_a)
    cex_b = CcxtCexClient(ex_b)
    ob_a: OrderBook = cex_a.fetch_order_book(symbol, limit=20)
    ob_b: OrderBook = cex_b.fetch_order_book(symbol, limit=20)
    base, quote = symbol.split("/")
    opp = find_cex_cex_opportunity(
        base_symbol=base,
        quote_symbol=quote,
        size_in_quote=size,
        book_a=ob_a,
        book_b=ob_b,
        fees_a=cex_a.fetch_trading_fees(symbol),
        fees_b=cex_b.fetch_trading_fees(symbol),
        threshold_pct=threshold,
        transfer_fee_in_base=transfer_fee,
    )
    if not opp:
        return JSONResponse({"ok": True, "opportunity": None})
    return {
        "ok": True,
        "opportunity": {
            "kind": opp.kind,
            "description": opp.description,
            "expected_profit_usdt": opp.expected_profit_usdt,
            "expected_roi_pct": opp.expected_roi_pct,
            "legs": opp.legs,
        },
    }


@app.get("/api/mega_scan")
def api_mega_scan(
    ex_list: str = Query(
        "okx,kraken,kucoin,gate,bitget,mexc,coinex,poloniex,bitfinex,bitstamp,bitvavo",
        description="Comma-separated exchange ids",
    ),
    exclude: str = Query("bybit,binance", description="Comma-separated exchanges to exclude"),
    quotes: str = Query("USDT", description="Comma-separated quotes or ANY"),
    bases: str = Query("", description="Comma-separated bases; if empty use preset"),
    preset: str = Query("CMC_TOP100", description="CMC_TOPN or NONE"),
    limit_symbols: int = 200,
    size: float = 1000.0,
    threshold: float = 0.5,
    min_volume: float = 0.0,
    top: int = 50,
    workers: int = 24,
    skip_stables: bool = True,
    enforce_lots: bool = True,
):
    ex_ids = [e.strip() for e in ex_list.split(",") if e.strip()]
    exclude_set = {e.strip() for e in exclude.split(",") if e.strip()}
    quotes_set = {q.strip().upper() for q in quotes.split(",")} if quotes else {"USDT"}
    bases_allow = {b.strip().upper() for b in bases.split(",") if b.strip()} if bases else get_bases_from_preset(preset)

    clients = build_exchanges(ex_ids, exclude_set)
    if not clients:
        return {"ok": True, "rows": []}

    ex_symbols = {}
    for ex_id, client in clients.items():
        ex_symbols[ex_id] = filter_symbols(load_spot_symbols(client), quotes_set, bases_allow, skip_stables)

    # Build symbol universe: present on at least two exchanges
    symbol_counts = {}
    for syms in ex_symbols.values():
        for s in syms:
            symbol_counts[s] = symbol_counts.get(s, 0) + 1
    symbols = [s for s, c in symbol_counts.items() if c >= 2]
    symbols.sort()
    symbols = symbols[: limit_symbols]

    rows = scan_symbols_once(
        clients=clients,
        ex_symbols=ex_symbols,
        symbols=symbols,
        size=size,
        threshold=threshold,
        workers=workers,
        min_volume=min_volume,
        enforce_lots=enforce_lots,
    )
    rows.sort(key=lambda r: r[5], reverse=True)
    rows = rows[: top]
    # jsonify
    out = [
        {
            "symbol": sym,
            "ask_exchange": ex_ask,
            "ask": ask,
            "bid_exchange": ex_bid,
            "bid": bid,
            "roi_pct": roi,
            "profit": profit,
        }
        for sym, ex_ask, ask, ex_bid, bid, roi, profit in rows
    ]
    return {"ok": True, "rows": out}


INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Arbitrage Web</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 16px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 12px; flex: 1; min-width: 320px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #eee; padding: 4px 8px; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    .controls { margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
    input, select, button { padding: 6px 8px; }
    .profit { color: #0a7a0a; font-weight: 600; }
    .loss { color: #b30000; font-weight: 600; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; }
  </style>
</head>
<body>
  <h2>Arbitrage Dashboard</h2>
  <div class="controls">
    <label>Ex A <input id="exA" value="okx"/></label>
    <label>Ex B <input id="exB" value="kraken"/></label>
    <label>Symbol <input id="symbol" value="BTC/USDT"/></label>
    <label>Size <input id="size" type="number" value="1000"/></label>
    <label>Threshold % <input id="threshold" type="number" value="0.5" step="0.1"/></label>
    <label>Transfer fee (base) <input id="transfer" type="number" value="0" step="0.0001"/></label>
    <button onclick="refreshAll()">Refresh</button>
  </div>
  <div class="row">
    <div class="card">
      <h3 id="titleA">Order Book A</h3>
      <table id="bookA"><thead><tr><th>Side</th><th>Price</th><th>Amount</th></tr></thead><tbody></tbody></table>
    </div>
    <div class="card">
      <h3 id="titleB">Order Book B</h3>
      <table id="bookB"><thead><tr><th>Side</th><th>Price</th><th>Amount</th></tr></thead><tbody></tbody></table>
    </div>
  </div>
  <div class="card" style="margin-top:12px;">
    <h3>Opportunity</h3>
    <div id="opp"></div>
  </div>

  <h2 style="margin-top:20px;">Multi-Exchange Scanner</h2>
  <div class="controls grid">
    <label>Exchanges <input id="exList" size="80" value="okx,kraken,kucoin,gate,bitget,mexc,coinex,poloniex,bitfinex,bitstamp,bitvavo"/></label>
    <label>Exclude <input id="exclude" value="bybit,binance"/></label>
    <label>Quotes <input id="quotes" value="USDT"/></label>
    <label>Bases <input id="bases" placeholder="e.g. BTC,ETH (leave empty for preset)"/></label>
    <label>Preset <input id="preset" value="CMC_TOP100"/></label>
    <label>Limit symbols <input id="limitSymbols" type="number" value="200"/></label>
    <label>Size <input id="megaSize" type="number" value="1000"/></label>
    <label>Threshold % <input id="megaThreshold" type="number" value="0.5" step="0.1"/></label>
    <label>Min volume <input id="minVolume" type="number" value="0"/></label>
    <label>Top N <input id="topN" type="number" value="50"/></label>
    <label>Workers <input id="workers" type="number" value="24"/></label>
    <label><input id="skipStables" type="checkbox" checked/> Skip pure stables</label>
    <label><input id="enforceLots" type="checkbox" checked/> Enforce lots</label>
    <button onclick="refreshMega()">Scan once</button>
  </div>
  <div class="card">
    <h3>Top Opportunities</h3>
    <table id="mega"><thead><tr><th>Symbol</th><th>AskEx</th><th>Ask</th><th>BidEx</th><th>Bid</th><th>ROI%</th><th>Profit</th></tr></thead><tbody></tbody></table>
  </div>

  <script>
    async function fetchJson(url) {
      const r = await fetch(url);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    }
    function fmt(n, d=4) { return Number(n).toLocaleString(undefined, {minimumFractionDigits:d, maximumFractionDigits:d}); }
    function row(side, p, a) { return `<tr><td>${side}</td><td>${fmt(p,2)}</td><td>${fmt(a,4)}</td></tr>`; }

    async function refreshAll() {
      const exA = document.getElementById('exA').value;
      const exB = document.getElementById('exB').value;
      const symbol = document.getElementById('symbol').value;
      const size = parseFloat(document.getElementById('size').value);
      const threshold = parseFloat(document.getElementById('threshold').value.replace(',', '.'));
      const transfer = parseFloat(document.getElementById('transfer').value);

      document.getElementById('titleA').innerText = `${exA} ${symbol}`;
      document.getElementById('titleB').innerText = `${exB} ${symbol}`;

      const [oba, obb, opp] = await Promise.all([
        fetchJson(`/api/orderbook?ex=${encodeURIComponent(exA)}&symbol=${encodeURIComponent(symbol)}`),
        fetchJson(`/api/orderbook?ex=${encodeURIComponent(exB)}&symbol=${encodeURIComponent(symbol)}`),
        fetchJson(`/api/opportunity?ex_a=${encodeURIComponent(exA)}&ex_b=${encodeURIComponent(exB)}&symbol=${encodeURIComponent(symbol)}&size=${size}&threshold=${threshold}&transfer_fee=${transfer}`)
      ]);

      const tbodyA = document.querySelector('#bookA tbody');
      const tbodyB = document.querySelector('#bookB tbody');
      tbodyA.innerHTML = '';
      tbodyB.innerHTML = '';
      (oba.asks || []).slice(0, 10).forEach(l => tbodyA.innerHTML += row('ASK', l.price, l.amount));
      (oba.bids || []).slice(0, 10).forEach(l => tbodyA.innerHTML += row('BID', l.price, l.amount));
      (obb.asks || []).slice(0, 10).forEach(l => tbodyB.innerHTML += row('ASK', l.price, l.amount));
      (obb.bids || []).slice(0, 10).forEach(l => tbodyB.innerHTML += row('BID', l.price, l.amount));

      const oppDiv = document.getElementById('opp');
      if (opp && opp.opportunity) {
        const o = opp.opportunity;
        oppDiv.innerHTML = `<div class="profit">ROI ${fmt(o.expected_roi_pct,2)}% | Profit ~${fmt(o.expected_profit_usdt,2)}</div><div>${o.description}</div><ul>${o.legs.map(l=>`<li>${l}</li>`).join('')}</ul>`
      } else {
        oppDiv.innerHTML = `<div class="loss">No opportunity above threshold</div>`
      }
    }

    async function refreshMega() {
      const exList = document.getElementById('exList').value;
      const exclude = document.getElementById('exclude').value;
      const quotes = document.getElementById('quotes').value;
      const bases = document.getElementById('bases').value;
      const preset = document.getElementById('preset').value;
      const limitSymbols = parseInt(document.getElementById('limitSymbols').value, 10);
      const size = parseFloat(document.getElementById('megaSize').value);
      const threshold = parseFloat(document.getElementById('megaThreshold').value.replace(',', '.'));
      const minVolume = parseFloat(document.getElementById('minVolume').value);
      const topN = parseInt(document.getElementById('topN').value, 10);
      const workers = parseInt(document.getElementById('workers').value, 10);
      const skipStables = document.getElementById('skipStables').checked;
      const enforceLots = document.getElementById('enforceLots').checked;

      const url = `/api/mega_scan?ex_list=${encodeURIComponent(exList)}&exclude=${encodeURIComponent(exclude)}&quotes=${encodeURIComponent(quotes)}&bases=${encodeURIComponent(bases)}&preset=${encodeURIComponent(preset)}&limit_symbols=${limitSymbols}&size=${size}&threshold=${threshold}&min_volume=${minVolume}&top=${topN}&workers=${workers}&skip_stables=${skipStables}&enforce_lots=${enforceLots}`;
      const data = await fetchJson(url);
      const tbody = document.querySelector('#mega tbody');
      tbody.innerHTML = '';
      (data.rows || []).forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.symbol}</td><td>${r.ask_exchange}</td><td>${fmt(r.ask,4)}</td><td>${r.bid_exchange}</td><td>${fmt(r.bid,4)}</td><td>${fmt(r.roi_pct,2)}</td><td>${fmt(r.profit,2)}</td>`;
        tbody.appendChild(tr);
      });
    }

    refreshAll();
    setInterval(refreshAll, 5000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)