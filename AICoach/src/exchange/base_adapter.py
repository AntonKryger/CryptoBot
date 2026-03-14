"""
Abstract base class for exchange adapters.

All exchange communication MUST go through this interface.
Bots never call exchange APIs directly — they use an adapter.
"""

from abc import ABC, abstractmethod
from typing import Optional


class BaseExchangeAdapter(ABC):
    """Interface that every exchange adapter must implement."""

    # ── Session management ────────────────────────────────────────

    @abstractmethod
    def start_session(self) -> bool:
        """Authenticate and establish a session with the exchange.
        Returns True on success.
        """

    @abstractmethod
    def ping(self) -> bool:
        """Check if session is alive. Returns True if healthy."""

    # ── Account info ──────────────────────────────────────────────

    @abstractmethod
    def get_account_balance(self) -> Optional[dict]:
        """Get current account balance.
        Returns: {"balance": float, "deposit": float, "profit_loss": float, "available": float}
        """

    @abstractmethod
    def get_accounts(self) -> dict:
        """Get all accounts/sub-accounts."""

    # ── Market data ───────────────────────────────────────────────

    @abstractmethod
    def get_market_info(self, epic: str) -> dict:
        """Get market details for an instrument (spread, status, etc)."""

    @abstractmethod
    def is_market_open(self, epic: str) -> tuple:
        """Check if a market is currently tradeable.
        Returns: (is_open: bool, status_string: str)
        """

    @abstractmethod
    def are_crypto_markets_open(self) -> tuple:
        """Quick check if crypto markets are open.
        Returns: (is_open: bool, status_string: str)
        """

    @abstractmethod
    def get_prices(self, epic: str, resolution: str = "MINUTE_15", max_count: int = 200) -> dict:
        """Get historical price candles.
        Returns exchange-native candle format.
        """

    @abstractmethod
    def search_markets(self, search_term: str, limit: int = 10) -> dict:
        """Search for markets by name or symbol."""

    @abstractmethod
    def get_spread(self, epic: str) -> float:
        """Get current bid-ask spread for an instrument."""

    # ── Trading ───────────────────────────────────────────────────

    @abstractmethod
    def get_positions(self) -> dict:
        """Get all open positions."""

    @abstractmethod
    def create_position(self, epic: str, direction: str, size: float,
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        """Open a new position.
        direction: 'BUY' or 'SELL'
        Returns: deal reference / order response.
        """

    @abstractmethod
    def close_position(self, position_id: str, direction: Optional[str] = None,
                       size: Optional[float] = None) -> dict:
        """Close an open position."""

    @abstractmethod
    def update_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        """Update stop-loss and/or take-profit on an existing position.
        IMPORTANT: Some exchanges clear the missing value — always send both if set.
        """

    # ── Orders ────────────────────────────────────────────────────

    @abstractmethod
    def get_orders(self) -> dict:
        """Get all working/open orders."""

    @abstractmethod
    def create_order(self, epic: str, direction: str, size: float, level: float,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None) -> dict:
        """Create a limit/stop order."""

    # ── Deal confirmation ─────────────────────────────────────────

    @abstractmethod
    def get_deal_confirmation(self, deal_reference: str) -> dict:
        """Get deal confirmation. Maps dealReference → dealId on exchanges that need it."""

    # ── History ───────────────────────────────────────────────────

    @abstractmethod
    def get_activity_history(self, from_date: Optional[str] = None,
                             to_date: Optional[str] = None) -> dict:
        """Get trading activity history."""

    @abstractmethod
    def get_transaction_history(self, from_date: Optional[str] = None,
                                to_date: Optional[str] = None) -> dict:
        """Get transaction/fill history."""
