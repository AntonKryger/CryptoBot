"""
Capital.com exchange adapter.

Wraps the existing CapitalClient to conform to the BaseExchangeAdapter interface.
All Capital.com-specific logic lives here — bots only see the adapter interface.
"""

import logging
import requests
import time
from typing import Optional

from .base_adapter import BaseExchangeAdapter

logger = logging.getLogger(__name__)

DEMO_URL = "https://demo-api-capital.backend-capital.com"
LIVE_URL = "https://api-capital.backend-capital.com"


class CapitalAdapter(BaseExchangeAdapter):
    """Capital.com CFD exchange adapter."""

    def __init__(self, config):
        # Support both new exchange config format and legacy capital format
        exchange_cfg = config.get("exchange", {})
        capital_cfg = config.get("capital", {})

        self.email = exchange_cfg.get("email") or capital_cfg.get("email")
        self.password = exchange_cfg.get("password") or capital_cfg.get("password")
        self.api_key = exchange_cfg.get("api_key") or capital_cfg.get("api_key")
        self.demo = exchange_cfg.get("demo", capital_cfg.get("demo", True))
        self.base_url = DEMO_URL if self.demo else LIVE_URL
        self.account_name = exchange_cfg.get("account_name") or capital_cfg.get("account_name")

        self.cst = None
        self.security_token = None
        self.session_active = False
        self._last_request_time = 0

    # ── Internal helpers (Capital.com specific) ───────────────────

    def _ensure_session(self):
        if not self.session_active:
            self.start_session()

    def _headers(self):
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.security_token,
            "Content-Type": "application/json",
        }

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self._last_request_time = time.time()

    def _request(self, method, endpoint, **kwargs):
        """Make an authenticated API request with rate limiting and session refresh."""
        self._ensure_session()
        self._rate_limit()

        url = f"{self.base_url}{endpoint}"
        resp = requests.request(method, url, headers=self._headers(), **kwargs)

        # Session expired — refresh and retry once
        if resp.status_code == 401:
            logger.warning("Session expired, refreshing...")
            self.session_active = False
            self._ensure_session()
            resp = requests.request(method, url, headers=self._headers(), **kwargs)

        resp.raise_for_status()
        return resp.json() if resp.content else None

    def _switch_account(self, account_name):
        """Switch to a specific account by name. FATAL if account not found."""
        data = self._request("GET", "/api/v1/accounts")
        available_names = []
        for account in data.get("accounts", []):
            name = account.get("accountName", "")
            available_names.append(name)
            if name.lower() == account_name.lower():
                account_id = account["accountId"]
                try:
                    self._request("PUT", "/api/v1/session", json={"accountId": account_id})
                except requests.exceptions.HTTPError as e:
                    if "400" in str(e):
                        logger.info(f"Already on account: {account_name} (ID: {account_id})")
                        return
                    raise
                logger.info(f"Switched to account: {account_name} (ID: {account_id})")
                return
        raise RuntimeError(
            f"FATAL: Account '{account_name}' not found! "
            f"Available accounts: {available_names}. "
            f"Bot STOPPED to prevent trading on wrong account."
        )

    # ── BaseExchangeAdapter implementation ────────────────────────

    def start_session(self) -> bool:
        url = f"{self.base_url}/api/v1/session"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        body = {
            "identifier": self.email,
            "password": self.password,
            "encryptedPassword": False,
        }

        resp = requests.post(url, json=body, headers=headers)
        resp.raise_for_status()

        self.cst = resp.headers.get("CST")
        self.security_token = resp.headers.get("X-SECURITY-TOKEN")
        self.session_active = True
        logger.info("Capital.com session started successfully")

        if self.account_name:
            self._switch_account(self.account_name)

        return True

    def ping(self) -> bool:
        try:
            self._request("GET", "/api/v1/ping")
            return True
        except Exception:
            return False

    def get_account_balance(self) -> Optional[dict]:
        data = self.get_accounts()
        if data and "accounts" in data:
            account = data["accounts"][0]
            if self.account_name:
                for acc in data["accounts"]:
                    if acc.get("accountName", "").lower() == self.account_name.lower():
                        account = acc
                        break
            return {
                "balance": account["balance"]["balance"],
                "deposit": account["balance"]["deposit"],
                "profit_loss": account["balance"]["profitLoss"],
                "available": account["balance"]["available"],
            }
        return None

    def get_accounts(self) -> dict:
        return self._request("GET", "/api/v1/accounts")

    def get_market_info(self, epic: str) -> dict:
        return self._request("GET", f"/api/v1/markets/{epic}")

    def is_market_open(self, epic: str) -> tuple:
        try:
            info = self.get_market_info(epic)
            status = info.get("snapshot", {}).get("marketStatus", "UNKNOWN")
            return status == "TRADEABLE", status
        except Exception as e:
            logger.warning(f"Could not check market status for {epic}: {e}")
            return False, f"ERROR: {e}"

    def are_crypto_markets_open(self) -> tuple:
        return self.is_market_open("BTCUSD")

    def get_prices(self, epic: str, resolution: str = "MINUTE_15", max_count: int = 200) -> dict:
        return self._request("GET", f"/api/v1/prices/{epic}", params={
            "resolution": resolution,
            "max": max_count,
        })

    def search_markets(self, search_term: str, limit: int = 10) -> dict:
        return self._request("GET", "/api/v1/markets", params={
            "searchTerm": search_term,
            "limit": limit,
        })

    def get_spread(self, epic: str) -> float:
        try:
            info = self.get_market_info(epic)
            snapshot = info.get("snapshot", {})
            bid = snapshot.get("bid", 0)
            offer = snapshot.get("offer", 0)
            return round(offer - bid, 6) if bid and offer else 0.0
        except Exception as e:
            logger.warning(f"Could not get spread for {epic}: {e}")
            return 0.0

    def get_positions(self) -> dict:
        return self._request("GET", "/api/v1/positions")

    def create_position(self, epic: str, direction: str, size: float,
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        body = {
            "epic": epic,
            "direction": direction,
            "size": size,
        }
        if stop_loss is not None:
            body["stopLevel"] = stop_loss
        if take_profit is not None:
            body["profitLevel"] = take_profit

        logger.info(f"Opening {direction} position: {epic} x{size}")
        return self._request("POST", "/api/v1/positions", json=body)

    def close_position(self, position_id: str, direction: Optional[str] = None,
                       size: Optional[float] = None) -> dict:
        logger.info(f"Closing position: {position_id}")
        if direction and size:
            close_direction = "SELL" if direction == "BUY" else "BUY"
            body = {
                "direction": close_direction,
                "size": size,
            }
            return self._request("DELETE", f"/api/v1/positions/{position_id}", json=body)
        return self._request("DELETE", f"/api/v1/positions/{position_id}")

    def update_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        body = {}
        if stop_loss is not None:
            body["stopLevel"] = stop_loss
        if take_profit is not None:
            body["profitLevel"] = take_profit
        return self._request("PUT", f"/api/v1/positions/{position_id}", json=body)

    def get_orders(self) -> dict:
        return self._request("GET", "/api/v1/workingorders")

    def create_order(self, epic: str, direction: str, size: float, level: float,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None) -> dict:
        body = {
            "epic": epic,
            "direction": direction,
            "size": size,
            "level": level,
            "type": "LIMIT",
        }
        if stop_loss is not None:
            body["stopLevel"] = stop_loss
        if take_profit is not None:
            body["profitLevel"] = take_profit
        return self._request("POST", "/api/v1/workingorders", json=body)

    def get_deal_confirmation(self, deal_reference: str) -> dict:
        return self._request("GET", f"/api/v1/confirms/{deal_reference}")

    def get_activity_history(self, from_date: Optional[str] = None,
                             to_date: Optional[str] = None) -> dict:
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._request("GET", "/api/v1/history/activity", params=params)

    def get_transaction_history(self, from_date: Optional[str] = None,
                                to_date: Optional[str] = None) -> dict:
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._request("GET", "/api/v1/history/transactions", params=params)
