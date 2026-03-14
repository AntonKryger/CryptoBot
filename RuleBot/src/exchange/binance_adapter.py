"""
Binance exchange adapter — stub for future implementation.
"""

from typing import Optional
from .base_adapter import BaseExchangeAdapter


class BinanceAdapter(BaseExchangeAdapter):
    """Binance Futures exchange adapter (not yet implemented)."""

    def __init__(self, config):
        exchange_cfg = config.get("exchange", {})
        self.api_key = exchange_cfg.get("api_key")
        self.api_secret = exchange_cfg.get("api_secret")
        self.demo = exchange_cfg.get("demo", True)

    def start_session(self) -> bool:
        raise NotImplementedError("Binance adapter not yet implemented")

    def ping(self) -> bool:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_account_balance(self) -> Optional[dict]:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_accounts(self) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_market_info(self, epic: str) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def is_market_open(self, epic: str) -> tuple:
        raise NotImplementedError("Binance adapter not yet implemented")

    def are_crypto_markets_open(self) -> tuple:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_prices(self, epic: str, resolution: str = "MINUTE_15", max_count: int = 200) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def search_markets(self, search_term: str, limit: int = 10) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_spread(self, epic: str) -> float:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_positions(self) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def create_position(self, epic: str, direction: str, size: float,
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def close_position(self, position_id: str, direction: Optional[str] = None,
                       size: Optional[float] = None) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def update_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_orders(self) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def create_order(self, epic: str, direction: str, size: float, level: float,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_deal_confirmation(self, deal_reference: str) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_activity_history(self, from_date: Optional[str] = None,
                             to_date: Optional[str] = None) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")

    def get_transaction_history(self, from_date: Optional[str] = None,
                                to_date: Optional[str] = None) -> dict:
        raise NotImplementedError("Binance adapter not yet implemented")
