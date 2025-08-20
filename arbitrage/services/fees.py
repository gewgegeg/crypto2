from __future__ import annotations

from typing import Optional

from arbitrage.models import TradingFees, TransferFee


class FeeService:
    def __init__(self, default_trading_fees: Optional[TradingFees] = None) -> None:
        self.default_trading_fees = default_trading_fees or TradingFees(maker_rate=0.001, taker_rate=0.001)

    def get_trading_fees(self, exchange_default: Optional[TradingFees] = None) -> TradingFees:
        if exchange_default is not None:
            return exchange_default
        return self.default_trading_fees

    def get_transfer_fee(self, asset: str, network: str) -> TransferFee:
        # Simplified static fee schedule; in production, fetch from exchange API
        fee_map = {
            ("USDT", "TRC20"): 1.0,
            ("USDT", "ERC20"): 10.0,
            ("USDT", "BEP20"): 0.8,
        }
        fee_amount = fee_map.get((asset, network), 1.0)
        return TransferFee(asset=asset, network=network, fee_amount=fee_amount)