"""
Platform sync client — sends bot data to the SaaS platform.
Called from main_kraken.py at startup, trades and heartbeat.
"""

import logging
import os
import requests
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# File to persist bot instance ID across restarts
BOT_ID_FILE = "data/platform_bot_id.txt"


class PlatformSync:
    """Sync bot state to the SaaS platform via /api/sync/* endpoints."""

    def __init__(self, config):
        platform_cfg = config.get("platform", {})
        self.enabled = platform_cfg.get("enabled", False)
        self.base_url = platform_cfg.get("url", "").rstrip("/")
        self.sync_secret = platform_cfg.get("sync_secret", "")
        self.user_id = platform_cfg.get("user_id", "")
        self.exchange = platform_cfg.get("exchange", "kraken")

        self.bot_id = config.get("bot", {}).get("id", "UNKNOWN")
        self.bot_name = config.get("bot", {}).get("name", self.bot_id)
        self.strategy_type = config.get("strategy", {}).get("type", "unknown")
        self.coins = config.get("trading", {}).get("coins", [])
        self.leverage = config.get("exchange", {}).get("leverage", 1)

        self.bot_instance_id = None
        self._scan_count = 0

        if not self.enabled:
            logger.info("Platform sync disabled")
            return

        if not self.base_url or not self.sync_secret or not self.user_id:
            logger.warning("Platform sync enabled but missing url/sync_secret/user_id — disabling")
            self.enabled = False

    def _headers(self):
        return {
            "X-Sync-Secret": self.sync_secret,
            "Content-Type": "application/json",
        }

    def _post(self, path, payload):
        """POST to platform API. Returns response dict or None on error."""
        try:
            resp = requests.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 429:
                logger.debug(f"Platform sync rate limited: {path}")
                return None
            if not resp.ok:
                logger.warning(f"Platform sync {path} failed: {resp.status_code} {resp.text[:200]}")
                return None
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Platform sync {path} error: {e}")
            return None

    def _get(self, path, params=None):
        """GET from platform API. Returns response dict or None on error."""
        try:
            resp = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self._headers(),
                timeout=10,
            )
            if not resp.ok:
                logger.warning(f"Platform sync GET {path} failed: {resp.status_code}")
                return None
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Platform sync GET {path} error: {e}")
            return None

    # ── 1. Register ────────────────────────────────────────────

    def register(self):
        """Register bot with platform. Returns bot_instance_id.
        Reads cached ID from file first to avoid re-registering on restart.
        """
        if not self.enabled:
            return None

        # Try cached ID first
        cached = self._read_cached_id()
        if cached:
            self.bot_instance_id = cached
            logger.info(f"Platform sync: using cached bot_instance_id {cached[:8]}...")
            return cached

        # Register with platform
        result = self._post("/api/sync/register", {
            "botId": self.bot_id,
            "userId": self.user_id,
            "exchange": self.exchange,
            "coins": self.coins,
            "leverage": self.leverage,
        })

        if result and result.get("botInstanceId"):
            self.bot_instance_id = result["botInstanceId"]
            already = result.get("alreadyExists", False)
            self._save_cached_id(self.bot_instance_id)
            logger.info(
                f"Platform sync: registered as {self.bot_instance_id[:8]}... "
                f"(existing={already})"
            )
            return self.bot_instance_id

        logger.warning("Platform sync: registration failed — will retry next cycle")
        return None

    def _read_cached_id(self):
        try:
            if os.path.exists(BOT_ID_FILE):
                with open(BOT_ID_FILE, "r") as f:
                    cached = f.read().strip()
                    if len(cached) > 10:
                        return cached
        except Exception:
            pass
        return None

    def _save_cached_id(self, bot_instance_id):
        try:
            os.makedirs(os.path.dirname(BOT_ID_FILE), exist_ok=True)
            with open(BOT_ID_FILE, "w") as f:
                f.write(bot_instance_id)
        except Exception as e:
            logger.warning(f"Could not save bot_instance_id to file: {e}")

    # ── 2. Heartbeat ───────────────────────────────────────────

    def send_heartbeat(self):
        """Send heartbeat to platform. Called every scan cycle."""
        if not self.enabled or not self.bot_instance_id:
            return

        self._post("/api/sync/heartbeat", {
            "botInstanceId": self.bot_instance_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ── 2b. Equity Snapshot ────────────────────────────────────

    def send_equity(self, equity):
        """Send equity snapshot for balance chart. Called every scan cycle."""
        if not self.enabled or not self.bot_instance_id or equity is None:
            return

        self._post("/api/sync/equity", {
            "userId": self.user_id,
            "botInstanceId": self.bot_instance_id,
            "equity": round(equity, 2),
            "exchange": self.exchange,
        })

    # ── 3. Bot Status ──────────────────────────────────────────

    def send_status(self, status, uptime_pct=None):
        """Update bot status on platform."""
        if not self.enabled or not self.bot_instance_id:
            return

        payload = {"botInstanceId": self.bot_instance_id, "status": status}
        if uptime_pct is not None:
            payload["uptimePercent"] = uptime_pct

        self._post("/api/sync/bot-status", payload)

    # ── 4. Trade Open ──────────────────────────────────────────

    def sync_trade_open(self, deal_id, epic, direction, size, entry_price,
                        stop_loss=None, take_profit=None,
                        signal_mode=None, signal_data=None):
        """Sync a new trade opening to platform."""
        if not self.enabled or not self.bot_instance_id:
            return

        self._post("/api/sync/trade", {
            "userId": self.user_id,
            "botInstanceId": self.bot_instance_id,
            "dealId": f"{self.bot_id}_{deal_id}",
            "epic": epic,
            "direction": direction,
            "size": size,
            "entryPrice": entry_price,
            "stopLoss": stop_loss,
            "takeProfit": take_profit,
            "signalMode": signal_mode or self.strategy_type,
            "signalData": signal_data,
            "exchangeProvider": "kraken",
        })

    # ── 5. Trade Close ─────────────────────────────────────────

    def sync_trade_close(self, deal_id, exit_price=None,
                         profit_loss=None, profit_loss_pct=None):
        """Sync a trade close to platform."""
        if not self.enabled or not self.bot_instance_id:
            return

        self._post("/api/sync/trade-close", {
            "dealId": f"{self.bot_id}_{deal_id}",
            "exitPrice": exit_price,
            "profitLoss": profit_loss,
            "profitLossPercent": profit_loss_pct,
        })

    # ── 6. Kill Switch Check ───────────────────────────────────

    def check_kill_switch(self):
        """Poll platform for kill switch status. Called every 5th scan cycle.
        Returns True if bot should stop.
        """
        if not self.enabled or not self.bot_instance_id:
            return False

        result = self._get("/api/sync/bot-config", {
            "botInstanceId": self.bot_instance_id,
        })

        if result and result.get("is_suspended"):
            reason = result.get("suspended_reason", "Platform kill switch")
            logger.critical(f"PLATFORM KILL SWITCH: {reason}")
            return True

        return False

    # ── Scan cycle hook ────────────────────────────────────────

    def on_scan_cycle(self, equity=None):
        """Called every scan cycle. Sends heartbeat + equity + checks kill switch every 5 cycles."""
        if not self.enabled:
            return False

        # Retry registration if not yet registered
        if not self.bot_instance_id:
            self.register()
            if not self.bot_instance_id:
                return False

        self.send_heartbeat()

        if equity is not None:
            self.send_equity(equity)

        self._scan_count += 1
        if self._scan_count % 5 == 0:
            return self.check_kill_switch()

        return False
