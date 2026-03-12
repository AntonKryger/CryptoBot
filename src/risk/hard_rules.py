"""
Hard Rules - Python-level trading guards that cannot be overridden by AI.
Circuit breaker state survives restart via SQLite.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Copenhagen")


class HardRules:
    """Non-overrideable trading guards enforced at Python level."""

    def __init__(self, config, notifier):
        self.notifier = notifier
        self.db_path = config.get("database", {}).get("path", "data_ai/trades.db")

        # Hard limits
        self.max_risk_pct = 1.5           # Max 1.5% of account per trade
        self.max_open_positions = 3       # Hard cap
        self.max_consecutive_losses = 3   # Before forced pause
        self.loss_pause_minutes = 20      # Pause after 3 losses
        self.no_trade_before_hour = 8     # CET
        self.no_trade_after_hour = 22     # CET
        self.min_trade_interval_minutes = 15

        self._init_db()
        self._state = self._load_state()

    def _init_db(self):
        """Create circuit breaker table if not exists."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS circuit_breaker (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[HardRules] DB init error: {e}")

    def _load_state(self):
        """Load circuit breaker state from DB."""
        state = {
            "consecutive_losses": 0,
            "pause_until": None,
            "last_trade_time": None,
        }
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("SELECT key, value FROM circuit_breaker").fetchall()
            conn.close()
            for key, value in rows:
                if key == "consecutive_losses":
                    state["consecutive_losses"] = int(value)
                elif key == "pause_until" and value != "None":
                    state["pause_until"] = datetime.fromisoformat(value)
                elif key == "last_trade_time" and value != "None":
                    state["last_trade_time"] = datetime.fromisoformat(value)
        except Exception as e:
            logger.error(f"[HardRules] State load error: {e}")
        logger.info(
            f"[HardRules] Loaded: {state['consecutive_losses']} consecutive losses, "
            f"pause_until={state['pause_until']}, last_trade={state['last_trade_time']}"
        )
        return state

    def _save_state(self, key, value):
        """Persist a single state key to SQLite."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO circuit_breaker (key, value, updated_at) VALUES (?, ?, ?)",
                (key, str(value), datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[HardRules] State save error: {e}")

    def can_trade(self, account_balance, risk_eur, open_positions_count):
        """Check all hard rules. Returns (allowed: bool, reason: str)."""

        # Rule 1: Trading hours (CET)
        now_cet = datetime.now(CET)
        hour = now_cet.hour
        if hour < self.no_trade_before_hour or hour >= self.no_trade_after_hour:
            reason = f"TIDSREGEL: Ingen handler {self.no_trade_after_hour}:00-{self.no_trade_before_hour}:00 CET (nu: {hour:02d}:{now_cet.minute:02d})"
            self._notify_blocked(reason)
            return False, reason

        # Rule 2: Max open positions
        if open_positions_count >= self.max_open_positions:
            reason = f"MAX POSITIONER: {open_positions_count}/{self.max_open_positions} åbne"
            self._notify_blocked(reason)
            return False, reason

        # Rule 3: Max risk per trade
        max_risk = account_balance * (self.max_risk_pct / 100)
        if risk_eur > max_risk:
            reason = f"MAX RISIKO: EUR {risk_eur:.2f} > {self.max_risk_pct}% af konto (EUR {max_risk:.2f})"
            self._notify_blocked(reason)
            return False, reason

        # Rule 4: Consecutive loss pause
        if self._state["pause_until"] and datetime.now() < self._state["pause_until"]:
            remaining = (self._state["pause_until"] - datetime.now()).total_seconds() / 60
            reason = f"TABSPAUSE: {self._state['consecutive_losses']} tab i træk, pause {remaining:.0f} min"
            self._notify_blocked(reason)
            return False, reason

        # Rule 5: Minimum interval between trades
        if self._state["last_trade_time"]:
            elapsed = (datetime.now() - self._state["last_trade_time"]).total_seconds() / 60
            if elapsed < self.min_trade_interval_minutes:
                remaining = self.min_trade_interval_minutes - elapsed
                reason = f"MIN INTERVAL: {remaining:.0f} min til næste trade (kræver {self.min_trade_interval_minutes} min)"
                self._notify_blocked(reason)
                return False, reason

        return True, "OK"

    def calculate_risk_eur(self, entry_price, stop_loss, size):
        """Calculate risk in EUR for a trade."""
        return abs(entry_price - stop_loss) * size

    def record_trade_opened(self):
        """Record that a trade was opened (for interval tracking)."""
        self._state["last_trade_time"] = datetime.now()
        self._save_state("last_trade_time", datetime.now().isoformat())

    def record_trade_result(self, profit_loss):
        """Record trade result for consecutive loss tracking."""
        if profit_loss is None:
            return

        if profit_loss < 0:
            self._state["consecutive_losses"] += 1
            self._save_state("consecutive_losses", self._state["consecutive_losses"])

            if self._state["consecutive_losses"] >= self.max_consecutive_losses:
                pause_until = datetime.now() + timedelta(minutes=self.loss_pause_minutes)
                self._state["pause_until"] = pause_until
                self._save_state("pause_until", pause_until.isoformat())

                msg = (
                    f"⛔ <b>TABSPAUSE AKTIVERET</b>\n"
                    f"{self._state['consecutive_losses']} tab i træk!\n"
                    f"Pause til: {pause_until.strftime('%H:%M')}\n"
                    f"({self.loss_pause_minutes} min tvungen pause)"
                )
                self.notifier.send(msg)
                logger.warning(f"[HardRules] Loss pause activated: {self._state['consecutive_losses']} losses")
        else:
            # Win resets the counter
            if self._state["consecutive_losses"] > 0:
                logger.info(f"[HardRules] Win resets loss counter (was {self._state['consecutive_losses']})")
            self._state["consecutive_losses"] = 0
            self._save_state("consecutive_losses", 0)
            # Clear any pause
            self._state["pause_until"] = None
            self._save_state("pause_until", "None")

    def get_status(self):
        """Get current hard rules state for debug/status."""
        now_cet = datetime.now(CET)
        return {
            "consecutive_losses": self._state["consecutive_losses"],
            "pause_until": self._state["pause_until"].isoformat() if self._state["pause_until"] else None,
            "last_trade_time": self._state["last_trade_time"].isoformat() if self._state["last_trade_time"] else None,
            "trading_hours": f"{self.no_trade_before_hour:02d}:00-{self.no_trade_after_hour:02d}:00 CET",
            "current_cet": now_cet.strftime("%H:%M"),
            "in_trading_hours": self.no_trade_before_hour <= now_cet.hour < self.no_trade_after_hour,
        }

    def _notify_blocked(self, reason):
        """Send Telegram notification when a rule blocks a trade."""
        self.notifier.send(f"🚫 <b>HARD RULE BLOKERET</b>\n{reason}")
        logger.warning(f"[HardRules] Blocked: {reason}")
