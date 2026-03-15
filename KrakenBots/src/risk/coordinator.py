"""
Bot Coordinator — Cross-bot regime handoff and coin locking.

Two bots on the same account hand off to each other based on market regime.
When regime shifts RANGING→TRENDING, Grid bot steps back, Trend bot takes over.
When regime shifts TRENDING→RANGING, Trend bot steps back, Grid bot takes over.

Uses shared JSON file for inter-container communication (Docker volume mount).
"""

import json
import logging
import os
import time
from datetime import datetime

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False  # Windows — no file locking (Docker runs Linux)
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_COORDINATOR_PATH = "/app/shared/coordinator.json"


class BotCoordinator:
    """Coordinates bot pairs on the same Kraken account.

    Pair concept: two bots complement each other for different regimes.
    - Grid + Trend: ranging ↔ trending handoff
    - MeanRev + Volatility: ranging ↔ extreme events handoff

    Only ONE bot in a pair is active per coin at any time.
    """

    # Priority levels (higher = can override lower)
    PRIORITIES = {
        "volatility": 10,   # Highest — crash events override everything
        "grid": 5,
        "trend": 5,
        "mean_reversion": 5,
    }

    # Exposure limits per strategy (% of total account)
    DEFAULT_EXPOSURE_LIMITS = {
        "grid": 30,
        "trend": 30,
        "mean_reversion": 20,
        "volatility": 10,
    }

    def __init__(self, config):
        coord_cfg = config.get("coordinator", {})
        self.bot_id = config.get("bot", {}).get("id", "UNKNOWN")
        self.strategy_type = config.get("strategy", {}).get("type", "unknown")
        self.partner_type = coord_cfg.get("partner_type")  # The complementary bot type
        self.shared_path = coord_cfg.get("shared_path", DEFAULT_COORDINATOR_PATH)
        self.exposure_limits = coord_cfg.get("exposure_limits", self.DEFAULT_EXPOSURE_LIMITS)

        # Per-coin exposure limit across ALL bots (% of total capital)
        self.max_per_coin_pct = coord_cfg.get("max_per_coin_pct", 25)

        # Global equity kill-switch: stop ALL trading if portfolio drawdown exceeds this
        self.global_max_drawdown_pct = coord_cfg.get("global_max_drawdown_pct", 10.0)

        # Ensure shared directory exists
        os.makedirs(os.path.dirname(self.shared_path), exist_ok=True)

        # Initialize shared state file if missing
        if not os.path.exists(self.shared_path):
            self._write_state({
                "locks": {},
                "exposure": {},
                "coin_exposure": {},  # {epic: total_pct} across all bots
                "regimes": {},
                "active_bot": {},
                "last_updated": datetime.now().isoformat(),
            })

    def _read_state(self) -> dict:
        """Read shared coordinator state with file locking."""
        try:
            with open(self.shared_path, "r") as f:
                if HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_SH)
                data = json.load(f)
                if HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            return {
                "locks": {},
                "exposure": {},
                "regimes": {},
                "active_bot": {},
                "last_updated": datetime.now().isoformat(),
            }

    def _write_state(self, state: dict):
        """Write shared coordinator state with file locking."""
        state["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.shared_path, "w") as f:
                if HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(state, f, indent=2)
                if HAS_FCNTL:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Coordinator write failed: {e}")

    def update_regime(self, epic: str, regime: str, adx: float):
        """Update the detected regime for a coin. Called by main scan loop."""
        state = self._read_state()
        state["regimes"][epic] = {
            "regime": regime,
            "adx": round(adx, 1),
            "detected_by": self.bot_id,
            "timestamp": datetime.now().isoformat(),
        }
        self._write_state(state)

    def can_trade(self, epic: str) -> tuple:
        """Check if this bot can trade the given coin.

        Returns: (allowed: bool, reason: str)

        Rules:
        1. Global kill-switch → blocked
        2. If coin is locked by partner with higher/equal priority → blocked
        3. If another bot has a pending request with higher priority → blocked
        4. If total exposure exceeds limit → blocked
        5. If per-coin exposure exceeds limit → blocked
        """
        state = self._read_state()

        # Rule 1: Global kill-switch
        if state.get("global_kill"):
            return False, "Global kill-switch active"

        # Rule 2: Check coin lock
        lock = state.get("locks", {}).get(epic)
        if lock and lock.get("bot") != self.bot_id:
            other_type = lock.get("strategy_type", "unknown")
            other_priority = self.PRIORITIES.get(other_type, 0)
            my_priority = self.PRIORITIES.get(self.strategy_type, 0)

            if my_priority <= other_priority:
                return False, f"Coin locked by {lock['bot']} ({other_type})"

            # Higher priority can override
            logger.info(f"[COORD] {self.bot_id} overriding {lock['bot']} on {epic} (priority {my_priority} > {other_priority})")

        # Rule 3: Check priority queue — is a higher-priority bot waiting?
        pending = state.get("pending_requests", {}).get(epic, [])
        my_priority = self.PRIORITIES.get(self.strategy_type, 0)
        for req in pending:
            if req.get("bot") != self.bot_id:
                req_priority = self.PRIORITIES.get(req.get("strategy_type", ""), 0)
                if req_priority > my_priority:
                    return False, f"Higher-priority request pending from {req['bot']} ({req.get('strategy_type')})"

        # Rule 4: Check exposure limit
        my_exposure = state.get("exposure", {}).get(self.bot_id, 0)
        limit = self.exposure_limits.get(self.strategy_type, 30)
        if my_exposure >= limit:
            return False, f"Exposure limit reached ({my_exposure:.0f}% >= {limit}%)"

        # Rule 5: Check per-coin exposure across ALL bots
        coin_exposure = state.get("coin_exposure", {}).get(epic, 0)
        if coin_exposure >= self.max_per_coin_pct:
            return False, f"Per-coin limit: {epic} at {coin_exposure:.0f}% >= {self.max_per_coin_pct}%"

        return True, "OK"

    def request_trade(self, epic: str):
        """Register intent to trade a coin (priority queue entry).

        Other bots check this to yield to higher-priority strategies.
        """
        state = self._read_state()
        if "pending_requests" not in state:
            state["pending_requests"] = {}
        if epic not in state["pending_requests"]:
            state["pending_requests"][epic] = []

        # Remove any stale request from this bot
        state["pending_requests"][epic] = [
            r for r in state["pending_requests"][epic] if r.get("bot") != self.bot_id
        ]

        state["pending_requests"][epic].append({
            "bot": self.bot_id,
            "strategy_type": self.strategy_type,
            "priority": self.PRIORITIES.get(self.strategy_type, 0),
            "timestamp": datetime.now().isoformat(),
        })
        self._write_state(state)

    def clear_trade_request(self, epic: str):
        """Remove this bot's pending trade request (after execution or skip)."""
        state = self._read_state()
        pending = state.get("pending_requests", {}).get(epic, [])
        state.setdefault("pending_requests", {})[epic] = [
            r for r in pending if r.get("bot") != self.bot_id
        ]
        self._write_state(state)

    def add_coin_exposure(self, epic: str, exposure_pct: float):
        """Add exposure for a coin without changing locks (for partial fill updates)."""
        if exposure_pct <= 0:
            return
        state = self._read_state()
        state["exposure"][self.bot_id] = state.get("exposure", {}).get(self.bot_id, 0) + exposure_pct
        if "coin_exposure" not in state:
            state["coin_exposure"] = {}
        state["coin_exposure"][epic] = state["coin_exposure"].get(epic, 0) + exposure_pct
        self._write_state(state)
        logger.debug(f"[COORD] {self.bot_id} added {exposure_pct:.1f}% exposure on {epic}")

    def lock_coin(self, epic: str, exposure_pct: float = 0):
        """Lock a coin for this bot (opening a position)."""
        state = self._read_state()
        state["locks"][epic] = {
            "bot": self.bot_id,
            "strategy_type": self.strategy_type,
            "since": datetime.now().isoformat(),
        }
        if exposure_pct > 0:
            state["exposure"][self.bot_id] = state.get("exposure", {}).get(self.bot_id, 0) + exposure_pct
            # Track per-coin exposure across all bots
            if "coin_exposure" not in state:
                state["coin_exposure"] = {}
            state["coin_exposure"][epic] = state["coin_exposure"].get(epic, 0) + exposure_pct
        state["active_bot"][epic] = self.bot_id
        self._write_state(state)
        logger.info(f"[COORD] {self.bot_id} locked {epic}")

    def unlock_coin(self, epic: str, exposure_pct: float = 0):
        """Unlock a coin (closing a position)."""
        state = self._read_state()
        lock = state.get("locks", {}).get(epic)
        if lock and lock.get("bot") == self.bot_id:
            del state["locks"][epic]
        if exposure_pct > 0:
            current = state.get("exposure", {}).get(self.bot_id, 0)
            state["exposure"][self.bot_id] = max(0, current - exposure_pct)
            # Reduce per-coin exposure
            if "coin_exposure" in state:
                current_coin = state["coin_exposure"].get(epic, 0)
                state["coin_exposure"][epic] = max(0, current_coin - exposure_pct)
        if state.get("active_bot", {}).get(epic) == self.bot_id:
            del state["active_bot"][epic]
        self._write_state(state)
        logger.info(f"[COORD] {self.bot_id} unlocked {epic}")

    def get_regime(self, epic: str) -> Optional[dict]:
        """Get the latest regime info for a coin (may have been set by partner bot)."""
        state = self._read_state()
        return state.get("regimes", {}).get(epic)

    def get_status(self) -> dict:
        """Get full coordinator status for monitoring."""
        state = self._read_state()
        return {
            "bot_id": self.bot_id,
            "strategy_type": self.strategy_type,
            "locks": state.get("locks", {}),
            "exposure": state.get("exposure", {}),
            "regimes": state.get("regimes", {}),
            "active_bots": state.get("active_bot", {}),
            "last_updated": state.get("last_updated", ""),
        }

    def announce_regime_shift(self, epic: str, old_regime: str, new_regime: str):
        """Announce a regime shift so partner bot can react."""
        state = self._read_state()

        # If regime shifts and we should hand off, unlock coin
        if self.strategy_type == "grid" and "TRENDING" in new_regime:
            logger.info(f"[COORD] {epic}: Regime shift {old_regime} → {new_regime}. Grid stepping back for Trend bot.")
            self.unlock_coin(epic)

        elif self.strategy_type == "trend" and new_regime == "RANGING":
            logger.info(f"[COORD] {epic}: Regime shift {old_regime} → {new_regime}. Trend stepping back for Grid bot.")
            self.unlock_coin(epic)

        self.update_regime(epic, new_regime, 0)

    def update_equity(self, balance: float, initial_balance: float = None):
        """Report this bot's equity to shared state for global kill-switch."""
        state = self._read_state()
        if "equity" not in state:
            state["equity"] = {}
        state["equity"][self.bot_id] = {
            "balance": round(balance, 2),
            "initial": round(initial_balance, 2) if initial_balance else state["equity"].get(self.bot_id, {}).get("initial", balance),
            "timestamp": datetime.now().isoformat(),
        }
        self._write_state(state)

    def check_global_kill_switch(self) -> tuple:
        """Check if total portfolio drawdown exceeds global limit.

        Returns: (killed: bool, reason: str)
        Aggregates equity from ALL bots in shared state.
        """
        state = self._read_state()

        # Check if already killed
        if state.get("global_kill"):
            return True, f"Global kill-switch active since {state['global_kill'].get('since', '?')}"

        equity_data = state.get("equity", {})
        if not equity_data:
            return False, "OK"

        total_current = sum(e.get("balance", 0) for e in equity_data.values())
        total_initial = sum(e.get("initial", 0) for e in equity_data.values())

        if total_initial <= 0:
            return False, "OK"

        drawdown_pct = (total_initial - total_current) / total_initial * 100
        if drawdown_pct >= self.global_max_drawdown_pct:
            # Set global kill flag so ALL bots see it
            state["global_kill"] = {
                "since": datetime.now().isoformat(),
                "triggered_by": self.bot_id,
                "drawdown_pct": round(drawdown_pct, 2),
                "total_current": round(total_current, 2),
                "total_initial": round(total_initial, 2),
            }
            self._write_state(state)
            return True, (f"Global drawdown {drawdown_pct:.1f}% >= {self.global_max_drawdown_pct}% "
                          f"(${total_current:.0f} / ${total_initial:.0f})")

        return False, "OK"

    def reset_global_kill(self):
        """Reset the global kill-switch (manual recovery after review)."""
        state = self._read_state()
        if "global_kill" in state:
            del state["global_kill"]
            self._write_state(state)
            logger.info("[COORD] Global kill-switch reset")

    def cleanup_stale_locks(self, max_age_seconds: int = 3600):
        """Remove locks older than max_age_seconds (dead bot cleanup)."""
        state = self._read_state()
        now = datetime.now()
        stale = []

        for epic, lock in state.get("locks", {}).items():
            try:
                lock_time = datetime.fromisoformat(lock["since"])
                if (now - lock_time).total_seconds() > max_age_seconds:
                    stale.append(epic)
            except (ValueError, KeyError):
                stale.append(epic)

        for epic in stale:
            del state["locks"][epic]
            logger.warning(f"[COORD] Cleaned stale lock on {epic}")

        if stale:
            self._write_state(state)
