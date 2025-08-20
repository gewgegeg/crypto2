from __future__ import annotations

from typing import Dict, List, Optional

from arbitrage.models import Opportunity, P2PQuote, TradingFees


class Leg:
    def __init__(self, name: str, detail: str) -> None:
        self.name = name
        self.detail = detail

    def __repr__(self) -> str:
        return f"{self.name}: {self.detail}"


def plan_multi_leg_path(
    p2p_buy: Optional[P2PQuote],
    spot_buy_price: Optional[float],
    spot_buy_fees: TradingFees,
    transfer_fee_asset: float,
    spot_sell_price: Optional[float],
    spot_sell_fees: TradingFees,
    size_in_fiat: float,
    fiat: str,
    asset: str = "USDT",
) -> Optional[Opportunity]:
    # Multi-leg path (3-4 steps):
    # 1) P2P BUY asset with fiat (get USDT amount)
    # 2) SPOT TRADE (optional: convert to another coin if needed)
    # 3) TRANSFER asset to other CEX (network fee)
    # 4) SELL asset for fiat or quote asset on destination CEX
    if p2p_buy is None or spot_buy_price is None or spot_sell_price is None:
        return None

    # Step 1: P2P buy amount of asset for given fiat size
    asset_amount_after_p2p = size_in_fiat / p2p_buy.price

    # Step 2: Spot buy may be used when we P2P buy fiat->fiat stable and then acquire target; here we assume already asset=USDT
    # So we keep asset amount; apply taker fee on later sell only.

    # Step 3: Transfer fee (deduct fixed units of asset)
    asset_amount_after_transfer = max(asset_amount_after_p2p - transfer_fee_asset, 0.0)
    if asset_amount_after_transfer <= 0:
        return None

    # Step 4: Sell on destination at spot_sell_price with taker fee
    sell_unit_after_fee = spot_sell_price * (1 - spot_sell_fees.taker_rate)
    proceeds_fiat = sell_unit_after_fee * asset_amount_after_transfer

    cost_fiat = size_in_fiat  # what we paid in fiat on P2P
    profit_fiat = proceeds_fiat - cost_fiat
    roi_pct = 100.0 * (profit_fiat / cost_fiat) if cost_fiat > 0 else 0.0

    if roi_pct <= 0:
        return None

    legs: List[str] = [
        f"P2P BUY {asset} with {fiat} at {p2p_buy.price:.4f}",
        "SPOT (optional conversion or hold)",
        f"TRANSFER {asset} (-{transfer_fee_asset} fee)",
        f"SELL {asset} at {sell_unit_after_fee:.4f} net",
    ]
    return Opportunity(
        kind="Multi_Leg",
        description=(
            f"P2P→SPOT→TRANSFER→SELL: pay {cost_fiat:.2f} {fiat}, get {proceeds_fiat:.2f} {fiat}; "
            f"profit {profit_fiat:.2f} {fiat}, ROI {roi_pct:.2f}%"
        ),
        expected_profit_usdt=profit_fiat,  # treat fiat≈USDT for template
        expected_roi_pct=roi_pct,
        legs=legs,
    )