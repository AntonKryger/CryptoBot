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

        # Read from config with safe defaults — these are HARD limits
        trading_cfg = config.get("trading", {})
        self.min_adx = trading_cfg.get("min_adx", 20)
        self.min_rr_ratio = trading_cfg.get("min_rr_ratio", 2.0)
        self.max_risk_pct = trading_cfg.get("max_risk_pct", 1.5)
        self.max_open_positions = trading_cfg.get("max_positions", 3)
        self.max_consecutive_losses = trading_cfg.get("circuit_breaker_losses", 3)
        self.loss_pause_minutes = trading_cfg.get("circuit_breaker_pause_minutes", 20)
        self.no_trade_before_hour = trading_cfg.get("trading_hours_start", 8)
        self.no_trade_after_hour = trading_cfg.get("trading_hours_end", 22)
        self.min_trade_interval_minutes = trading_cfg.get("min_interval_minutes", 15)
        self.max_hold_hours = trading_cfg.get("max_hold_hours", 4)

        # Telegram spam guard: max 1 notification per gate type per 30 min
        self._last_notify = {}  # {reason_prefix: datetime}

        self._init_db()
        self._state = self._load_state()

        logger.info(
            f"[HardRules] Config: ADX>={self.min_adx} | R:R>={self.min_rr_ratio} | "
            f"MaxPos={self.max_open_positions} | Hours={self.no_trade_before_hour}-{self.no_trade_after_hour} CET | "
            f"CircuitBreaker={self.max_consecutive_losses}losses/{self.loss_pause_minutes}min | "
            f"MinInterval={self.min_trade_interval_minutes}min | MaxHold={self.max_hold_hours}h"
        )

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

    # ── Standalone gate checks (usable from any code path) ──

    def check_adx_gate(self, epic, adx):
        """ADX hard gate. Returns True if ADX is high enough to trade."""
        if adx < self.min_adx:
            reason = f"ADX GATE: {epic} blokeret (ADX {adx:.1f} < {self.min_adx})"
            self._notify_blocked(reason)
            return False
        return True

    def check_rr_gate(self, entry, sl, tp, direction):
        """R:R hard gate. Returns (allowed, rr_ratio)."""
        if direction == "BUY":
            risk = entry - sl
            reward = tp - entry
        else:
            risk = sl - entry
            reward = entry - tp

        if risk <= 0:
            logger.warning(f"[R:R GATE] Invalid risk={risk:.4f}, trade afvist")
            return False, 0.0

        rr = reward / risk
        if rr < self.min_rr_ratio:
            reason = f"RR GATE: Blokeret (RR {rr:.2f}:1 < {self.min_rr_ratio}:1 minimum)"
            self._notify_blocked(reason)
            return False, rr

        return True, rr

    def is_trading_hours(self):
        """Check if we are in allowed trading hours (CET)."""
        now_cet = datetime.now(CET)
        return self.no_trade_before_hour <= now_cet.hour < self.no_trade_after_hour

    def is_circuit_breaker_active(self):
        """Check if circuit breaker pause is active."""
        if self._state["pause_until"] and datetime.now() < self._state["pause_until"]:
            return True
        return False

    def can_open_new_trade(self):
        """Check min interval since last trade. Returns True if enough time passed."""
        if self._state["last_trade_time"]:
            elapsed = (datetime.now() - self._state["last_trade_time"]).total_seconds() / 60
            if elapsed < self.min_trade_interval_minutes:
                return False
        return True

    def pre_trade_gates(self, epic, adx, open_positions_count):
        """All pre-AI gates in one call. Returns (allowed, reason)."""
        # 1. Trading hours
        if not self.is_trading_hours():
            now_cet = datetime.now(CET)
            reason = f"TIDSREGEL: Udenfor handelstid (nu: {now_cet.hour:02d}:{now_cet.minute:02d} CET)"
            self._notify_blocked(reason)
            return False, reason

        # 2. Circuit breaker
        if self.is_circuit_breaker_active():
            remaining = (self._state["pause_until"] - datetime.now()).total_seconds() / 60
            reason = f"TABSPAUSE: {self._state['consecutive_losses']} tab i træk, pause {remaining:.0f} min"
            self._notify_blocked(reason)
            return False, reason

        # 3. Max positions
        if open_positions_count >= self.max_open_positions:
            reason = f"MAX POSITIONER: {open_positions_count}/{self.max_open_positions} åbne"
            self._notify_blocked(reason)
            return False, reason

        # 4. Min interval
        if not self.can_open_new_trade():
            elapsed = (datetime.now() - self._state["last_trade_time"]).total_seconds() / 60
            remaining = self.min_trade_interval_minutes - elapsed
            reason = f"MIN INTERVAL: {remaining:.0f} min til næste trade"
            self._notify_blocked(reason)
            return False, reason

        # 5. ADX
        if not self.check_adx_gate(epic, adx):
            return False, f"ADX GATE: {epic} ADX {adx:.1f} < {self.min_adx}"

        return True, "OK"

    def _notify_blocked(self, reason):
        """Send Telegram notification when a rule blocks a trade. Max 1 per type per 30 min."""
        # Extract gate type prefix for spam control
        prefix = reason.split(":")[0] if ":" in reason else reason[:20]
        now = datetime.now()
        last = self._last_notify.get(prefix)
        if last and (now - last).total_seconds() < 1800:
            # Already notified recently, just log
            logger.warning(f"[HardRules] Blocked (silent): {reason}")
            return

        self._last_notify[prefix] = now
        self.notifier.send(f"🚫 <b>HARD RULE BLOKERET</b>\n{reason}")
        logger.warning(f"[HardRules] Blocked: {reason}")
