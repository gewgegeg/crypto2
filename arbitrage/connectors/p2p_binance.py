from __future__ import annotations

from typing import List
import requests

from arbitrage.models import P2PQuote


class BinanceP2PClient:
    """Minimal public P2P quotes via undocumented endpoint used by web.

    Notes: This endpoint is subject to change. For production use, add retries, headers, and error handling.
    """

    BASE_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; ArbitrageBot/1.0)",
        })

    def fetch_quotes(self, asset: str, fiat: str, trade_type: str = "BUY", rows: int = 10) -> List[P2PQuote]:
        payload = {
            "page": 1,
            "rows": rows,
            "payTypes": [],
            "asset": asset,
            "fiat": fiat,
            "tradeType": trade_type,
            "publisherType": None,
        }
        r = self.session.post(self.BASE_URL, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        result = []
        for item in data.get("data", []):
            adv = item.get("adv", {})
            price = float(adv.get("price"))
            available_amount = float(adv.get("tradableQuantity"))
            min_amount = float(adv.get("minSingleTransAmount", 0.0))
            advertiser = (item.get("advertiser") or {}).get("nickName")
            result.append(
                P2PQuote(
                    asset=asset,
                    fiat=fiat,
                    trade_type=trade_type,  # BUY means you buy crypto for fiat
                    price=price,
                    available_amount=available_amount,
                    min_amount=min_amount,
                    advertiser=advertiser,
                )
            )
        return result