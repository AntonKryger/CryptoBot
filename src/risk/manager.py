import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Coin categories for position sizing
MEMECOINS = {"DOGEUSD", "SHIBAUSD", "PEPEUSD", "FLOKIUSD"}
MAJORS = {"BTCUSD", "ETHUSD"}

# Everything else is an altcoin


class RiskManager:
    """Manages position sizing, stop-loss, take-profit, and kill switch."""

    def __init__(self, config):
        risk_cfg = config.get("risk", {})
        self.stop_loss_pct = risk_cfg.get("stop_loss", 4.0)
        self.take_profit_pct = risk_cfg.get("take_profit", 7.0)
        self.trailing_stop_trigger = risk_cfg.get("trailing_stop_trigger", 3.0)
        self.max_open_positions = risk_cfg.get("max_open_positions", 5)
        self.daily_loss_limit = risk_cfg.get("daily_loss_limit", 5.0)
        self.total_loss_limit = risk_cfg.get("total_loss_limit", 30.0)
        self.leverage = config.get("trading", {}).get("leverage", 2)

        # Capital allocation limits (% of total balance)
        alloc_cfg = risk_cfg.get("allocation", {})
        self.max_total_exposure_pct = alloc_cfg.get("max_total_exposure", 80)
        self.max_memecoin_pct = alloc_cfg.get("max_memecoin", 5)
        self.max_major_pct = alloc_cfg.get("max_major", 25)
        self.max_altcoin_pct = alloc_cfg.get("max_altcoin", 15)
        self.min_position_pct = alloc_cfg.get("min_position", 3)

        self.daily_start_balance = None
        self.initial_balance = None
        self.kill_switch_active = False
        self.daily_reset_date = None

    def initialize(self, balance):
        """Set initial balance for kill switch tracking."""
        self.initial_balance = balance
        self.daily_start_balance = balance
        self.daily_reset_date = datetime.now().date()
        self.kill_switch_active = False
        logger.info(f"Risk manager initialized. Balance: €{balance:.2f}")

    def check_kill_switch(self, current_balance):
        """Check if kill switch should activate."""
        today = datetime.now().date()
        if today != self.daily_reset_date:
            self.daily_start_balance = current_balance
            self.daily_reset_date = today

        # Daily loss check
        if self.daily_start_balance > 0:
            daily_loss = (self.daily_start_balance - current_balance) / self.daily_start_balance * 100
            if daily_loss >= self.daily_loss_limit:
                self.kill_switch_active = True
                logger.critical(f"KILL SWITCH: Daily loss limit hit ({daily_loss:.1f}%)")
                return True, f"Dagligt tab: {daily_loss:.1f}% (grænse: {self.daily_loss_limit}%)"

        # Total loss check
        if self.initial_balance and self.initial_balance > 0:
            total_loss = (self.initial_balance - current_balance) / self.initial_balance * 100
            if total_loss >= self.total_loss_limit:
                self.kill_switch_active = True
                logger.critical(f"KILL SWITCH: Total loss limit hit ({total_loss:.1f}%)")
                return True, f"Totalt tab: {total_loss:.1f}% (grænse: {self.total_loss_limit}%)"

        return False, None

    def get_coin_category(self, epic):
        """Get the category of a coin for allocation purposes."""
        if epic in MEMECOINS:
            return "memecoin"
        elif epic in MAJORS:
            return "major"
        return "altcoin"

    def get_max_allocation_pct(self, epic):
        """Get max allocation percentage for a coin based on its category."""
        cat = self.get_coin_category(epic)
        if cat == "memecoin":
            return self.max_memecoin_pct
        elif cat == "major":
            return self.max_major_pct
        return self.max_altcoin_pct

    def allocate_capital(self, signals, available_balance):
        """Allocate capital across multiple signals weighted by confidence.

        Args:
            signals: list of (epic, signal, confidence, details) tuples
            available_balance: EUR available for new positions

        Returns:
            list of (epic, signal, allocated_amount, details) tuples
        """
        if not signals:
            return []

        max_total = available_balance * (self.max_total_exposure_pct / 100)
        remaining = max_total

        # Sort by confidence (highest first)
        signals = sorted(signals, key=lambda s: s[2], reverse=True)

        # Calculate total confidence weight
        total_weight = sum(s[2] for s in signals)
        if total_weight == 0:
            return []

        allocations = []
        for epic, signal, confidence, details in signals:
            if remaining <= 0:
                break

            # Max for this coin's category
            max_for_coin = available_balance * (self.get_max_allocation_pct(epic) / 100)
            # Min position size
            min_amount = available_balance * (self.min_position_pct / 100)

            # Confidence-weighted share of remaining capital
            weight_share = confidence / total_weight
            ideal_amount = max_total * weight_share

            # Clamp to category max
            amount = min(ideal_amount, max_for_coin, remaining)

            # Skip if too small
            if amount < min_amount:
                logger.info(f"Allocation {epic}: skipped (€{amount:.0f} < min €{min_amount:.0f})")
                continue

            remaining -= amount
            allocations.append((epic, signal, amount, details))

            cat = self.get_coin_category(epic)
            logger.info(
                f"Allocation {epic} ({cat}): €{amount:.0f} "
                f"(conf={confidence}, max={self.get_max_allocation_pct(epic)}%)"
            )

        return allocations

    def calculate_position_size(self, allocated_amount, price):
        """Calculate position size from allocated EUR amount."""
        effective_amount = allocated_amount * self.leverage
        size = effective_amount / price
        return round(size, 4)

    def calculate_stop_loss(self, entry_price, direction):
        """Calculate stop-loss price."""
        if direction == "BUY":
            return round(entry_price * (1 - self.stop_loss_pct / 100), 2)
        else:  # SELL (short)
            return round(entry_price * (1 + self.stop_loss_pct / 100), 2)

    def calculate_take_profit(self, entry_price, direction):
        """Calculate take-profit price."""
        if direction == "BUY":
            return round(entry_price * (1 + self.take_profit_pct / 100), 2)
        else:  # SELL (short)
            return round(entry_price * (1 - self.take_profit_pct / 100), 2)

    def should_move_trailing_stop(self, entry_price, current_price, direction):
        """Check if trailing stop should be moved to break-even."""
        if direction == "BUY":
            gain_pct = (current_price - entry_price) / entry_price * 100
        else:
            gain_pct = (entry_price - current_price) / entry_price * 100

        return gain_pct >= self.trailing_stop_trigger

    def can_open_position(self, open_positions_count, balance, current_balance):
        """Check if a new position can be opened."""
        if self.kill_switch_active:
            return False, "Kill switch er aktiv"

        killed, reason = self.check_kill_switch(current_balance)
        if killed:
            return False, reason

        if open_positions_count >= self.max_open_positions:
            return False, f"Max positioner nået ({self.max_open_positions})"

        return True, None

    def update_config(self, config):
        """Update risk parameters from config (for runtime profile switching)."""
        risk_cfg = config.get("risk", {})
        self.stop_loss_pct = risk_cfg.get("stop_loss", self.stop_loss_pct)
        self.take_profit_pct = risk_cfg.get("take_profit", self.take_profit_pct)
        self.trailing_stop_trigger = risk_cfg.get("trailing_stop_trigger", self.trailing_stop_trigger)
        self.max_open_positions = risk_cfg.get("max_open_positions", self.max_open_positions)
        logger.info(f"Risk parameters updated: SL={self.stop_loss_pct}%, TP={self.take_profit_pct}%")
