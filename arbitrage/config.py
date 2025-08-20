from __future__ import annotations

import os

try:
    from pydantic import BaseSettings, Field  # type: ignore
    _PYDANTIC = True
except Exception:
    BaseSettings = object  # type: ignore
    Field = None  # type: ignore
    _PYDANTIC = False


if _PYDANTIC:
    class Settings(BaseSettings):
        """Application settings loaded from environment.

        Prefixed with ARB_. E.g., ARB_EXCHANGE_A=binance
        """

        exchange_a: str = Field("binance", description="Primary CEX id (ccxt id)")
        exchange_b: str = Field("kraken", description="Secondary CEX id (ccxt id)")

        symbol: str = Field("BTC/USDT", description="Trading pair to analyze")
        trade_size_usdt: float = Field(1000.0, description="Notional size in USDT")

        spread_threshold_pct: float = Field(
            0.5, description="Minimum net spread percent to notify (e.g., 0.5)"
        )

        p2p_fiat: str = Field("USD", description="Binance P2P fiat currency code")
        network_pref: str = Field(
            "TRC20", description="Preferred network for transfers (USDT/TRC20 default)"
        )

        use_mock_data: bool = Field(
            True, description="Use deterministic mock data instead of live APIs"
        )

        log_level: str = Field("INFO", description="Logging level")

        class Config:
            env_prefix = "ARB_"
            env_file = ".env"
            extra = "ignore"
else:
    class Settings:  # type: ignore[no-redef]
        def __init__(self) -> None:
            prefix = "ARB_"
            self.exchange_a = os.getenv(prefix + "EXCHANGE_A", "binance")
            self.exchange_b = os.getenv(prefix + "EXCHANGE_B", "kraken")

            self.symbol = os.getenv(prefix + "SYMBOL", "BTC/USDT")
            self.trade_size_usdt = float(os.getenv(prefix + "TRADE_SIZE_USDT", "1000"))

            self.spread_threshold_pct = float(os.getenv(prefix + "SPREAD_THRESHOLD_PCT", "0.5"))

            self.p2p_fiat = os.getenv(prefix + "P2P_FIAT", "USD")
            self.network_pref = os.getenv(prefix + "NETWORK_PREF", "TRC20")

            self.use_mock_data = os.getenv(prefix + "USE_MOCK_DATA", "true").lower() in {"1", "true", "yes"}

            self.log_level = os.getenv(prefix + "LOG_LEVEL", "INFO")


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]