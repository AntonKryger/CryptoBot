import requests
import logging
import time
import json
import websocket
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

DEMO_URL = "https://demo-api-capital.backend-capital.com"
LIVE_URL = "https://api-capital.backend-capital.com"


class CapitalClient:
    """Client for Capital.com REST and WebSocket API."""

    def __init__(self, config):
        self.email = config["capital"]["email"]
        self.password = config["capital"]["password"]
        self.api_key = config["capital"]["api_key"]
        self.demo = config["capital"].get("demo", True)
        self.base_url = DEMO_URL if self.demo else LIVE_URL

        self.cst = None
        self.security_token = None
        self.session_active = False
        self._last_request_time = 0

    # ── Session management ──────────────────────────────────────────

    def start_session(self):
        """Authenticate and get session tokens."""
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
        return True

    def _ensure_session(self):
        """Refresh session if needed."""
        if not self.session_active:
            self.start_session()

    def _headers(self):
        """Get authenticated headers."""
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.security_token,
            "Content-Type": "application/json",
        }

    def _rate_limit(self):
        """Enforce rate limiting: max 10 requests/second."""
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

        # Session expired - refresh and retry once
        if resp.status_code == 401:
            logger.warning("Session expired, refreshing...")
            self.session_active = False
            self._ensure_session()
            resp = requests.request(method, url, headers=self._headers(), **kwargs)

        resp.raise_for_status()
        return resp.json() if resp.content else None

    # ── Account info ────────────────────────────────────────────────

    def get_accounts(self):
        """Get all accounts."""
        return self._request("GET", "/api/v1/accounts")

    def get_account_balance(self):
        """Get current account balance and P/L."""
        data = self.get_accounts()
        if data and "accounts" in data:
            account = data["accounts"][0]
            return {
                "balance": account["balance"]["balance"],
                "deposit": account["balance"]["deposit"],
                "profit_loss": account["balance"]["profitLoss"],
                "available": account["balance"]["available"],
            }
        return None

    # ── Market data ─────────────────────────────────────────────────

    def get_market_info(self, epic):
        """Get market details for an instrument."""
        return self._request("GET", f"/api/v1/markets/{epic}")

    def search_markets(self, search_term, limit=10):
        """Search for markets by name or epic."""
        return self._request("GET", "/api/v1/markets", params={
            "searchTerm": search_term,
            "limit": limit,
        })

    def get_prices(self, epic, resolution="MINUTE_15", max_count=200):
        """Get historical price candles."""
        return self._request("GET", f"/api/v1/prices/{epic}", params={
            "resolution": resolution,
            "max": max_count,
        })

    # ── Trading ─────────────────────────────────────────────────────

    def get_positions(self):
        """Get all open positions."""
        return self._request("GET", "/api/v1/positions")

    def create_position(self, epic, direction, size, stop_loss=None, take_profit=None):
        """
        Open a new position.
        direction: 'BUY' (long) or 'SELL' (short)
        """
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

    def close_position(self, deal_id, direction=None, size=None):
        """Close an open position by deal ID.
        Capital.com requires the opposite direction and size in the DELETE body.
        """
        logger.info(f"Closing position: {deal_id}")
        # Capital.com API requires direction (opposite) and size to close
        if direction and size:
            close_direction = "SELL" if direction == "BUY" else "BUY"
            body = {
                "direction": close_direction,
                "size": size,
            }
            return self._request("DELETE", f"/api/v1/positions/{deal_id}", json=body)
        return self._request("DELETE", f"/api/v1/positions/{deal_id}")

    def update_position(self, deal_id, stop_loss=None, take_profit=None):
        """Update stop-loss or take-profit on an existing position."""
        body = {}
        if stop_loss is not None:
            body["stopLevel"] = stop_loss
        if take_profit is not None:
            body["profitLevel"] = take_profit

        return self._request("PUT", f"/api/v1/positions/{deal_id}", json=body)

    # ── Orders ──────────────────────────────────────────────────────

    def get_orders(self):
        """Get all working orders."""
        return self._request("GET", "/api/v1/workingorders")

    def create_order(self, epic, direction, size, level, stop_loss=None, take_profit=None):
        """Create a limit/stop order."""
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

    # ── Activity / History ──────────────────────────────────────────

    def get_activity_history(self, from_date=None, to_date=None):
        """Get trading activity history."""
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._request("GET", "/api/v1/history/activity", params=params)

    def get_transaction_history(self, from_date=None, to_date=None):
        """Get transaction history."""
        params = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self._request("GET", "/api/v1/history/transactions", params=params)

    # ── Ping / health ───────────────────────────────────────────────

    def ping(self):
        """Check if session is alive."""
        try:
            self._request("GET", "/api/v1/ping")
            return True
        except Exception:
            return False
