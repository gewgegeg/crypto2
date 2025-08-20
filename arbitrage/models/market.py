from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional


@dataclass
class PriceLevel:
    price: float
    amount: float


@dataclass
class OrderBook:
    symbol: str
    bids: List[PriceLevel]  # sorted desc by price
    asks: List[PriceLevel]  # sorted asc by price
    exchange_id: str


@dataclass
class Ticker:
    symbol: str
    best_bid: float
    best_ask: float
    exchange_id: str


@dataclass
class TradingFees:
    maker_rate: float  # e.g., 0.001 for 0.1%
    taker_rate: float  # e.g., 0.001 for 0.1%


@dataclass
class TransferFee:
    asset: str
    network: str
    fee_amount: float  # in asset units


@dataclass
class P2PQuote:
    asset: str  # e.g., USDT
    fiat: str   # e.g., USD
    trade_type: Literal["BUY", "SELL"]
    price: float  # fiat per asset
    available_amount: float
    min_amount: float
    advertiser: Optional[str] = None


@dataclass
class Opportunity:
    kind: Literal[
        "CEX_CEX",
        "P2P_CEX",
        "CEX_Triangular",
        "Multi_Leg",
    ]
    description: str
    expected_profit_usdt: float
    expected_roi_pct: float
    legs: List[str]