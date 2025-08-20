from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from arbitrage.connectors.cex import CcxtCexClient
from arbitrage.strategies import find_cex_cex_opportunity
from arbitrage.models import OrderBook

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
      const threshold = parseFloat(document.getElementById('threshold').value);
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
    refreshAll();
    setInterval(refreshAll, 5000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)