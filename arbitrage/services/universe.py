from __future__ import annotations

import os
from typing import List, Optional

import requests

# Conservative static fallback of large-cap bases
DEFAULT_TOP_BASES: List[str] = [
    "BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "DOGE", "TRX", "TON",
    "DOT", "MATIC", "AVAX", "SHIB", "LINK", "LTC", "BCH", "UNI",
    "XLM", "ATOM", "ETC", "APT", "ARB", "OP", "NEAR", "FIL", "INJ",
    "SUI", "TAO", "HBAR", "RNDR", "AAVE", "MKR", "ALGO", "FTM",
    "EGLD", "KAS", "XMR", "GRT", "BTT", "TIA", "JTO", "IMX", "SEI",
    "RUNE", "FLOW", "VET", "PEPE", "DYDX", "PYTH",
]


def get_cmc_top_bases(limit: int = 50, convert: str = "USD", api_key: Optional[str] = None) -> List[str]:
    key = api_key or os.getenv("CMC_API_KEY")
    if not key:
        return DEFAULT_TOP_BASES[:limit]
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
        params = {"limit": limit, "convert": convert}
        headers = {"X-CMC_PRO_API_KEY": key}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        bases: List[str] = []
        for item in data.get("data", [])[:limit]:
            sym = item.get("symbol")
            if isinstance(sym, str):
                bases.append(sym.upper())
        # Filter out common stablecoins to avoid noise if present
        stables = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI"}
        bases = [b for b in bases if b not in stables]
        return bases
    except Exception:
        return DEFAULT_TOP_BASES[:limit]