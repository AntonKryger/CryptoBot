import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages position sizing, stop-loss, take-profit, and kill switch."""

    def __init__(self, config):
        risk_cfg = config.get("risk", {})
        self.stop_loss_pct = risk_cfg.get("stop_loss", 4.0)
        self.take_profit_pct = risk_cfg.get("take_profit", 7.0)
        self.trailing_stop_trigger = risk_cfg.get("trailing_stop_trigger", 3.0)
        self.max_position_pct = risk_cfg.get("max_position_pct", 20)
        self.max_open_positions = risk_cfg.get("max_open_positions", 5)
        self.daily_loss_limit = risk_cfg.get("daily_loss_limit", 5.0)
        self.total_loss_limit = risk_cfg.get("total_loss_limit", 30.0)
        self.leverage = config.get("trading", {}).get("leverage", 2)

        self.daily_start_balance = None
        self.initial_balance = None
        self.kill_switch_active = False
        self.daily_reset_date = None

    def initialize(self, balance):
        """Set initial balance for kill switch tracking."""
        self.initial_balance = balance
        self.daily_start_balance = balance
        self.daily_reset_date = datetime.now().date()
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

    def calculate_position_size(self, balance, price):
        """Calculate position size based on max position percentage and leverage."""
        max_amount = balance * (self.max_position_pct / 100)
        # With leverage, we can control a larger position
        effective_amount = max_amount * self.leverage
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
        self.max_position_pct = risk_cfg.get("max_position_pct", self.max_position_pct)
        self.max_open_positions = risk_cfg.get("max_open_positions", self.max_open_positions)
        logger.info(f"Risk parameters updated: SL={self.stop_loss_pct}%, TP={self.take_profit_pct}%")
