import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Coin categories for position sizing
MEMECOINS = {"DOGEUSD", "SHIBAUSD", "PEPEUSD", "FLOKIUSD"}
MAJORS = {"BTCUSD", "ETHUSD"}

# Everything else is an altcoin

# Confidence multiplier lookup (confidence score -> sizing multiplier)
# Hard filters in AI/signals already gate entry quality, so sizing is less conservative
CONFIDENCE_MULTIPLIER = {
    1: 0.20, 2: 0.20, 3: 0.20, 4: 0.25, 5: 0.30,
    6: 0.50, 7: 0.70, 8: 0.85, 9: 1.00, 10: 1.00,
}

# Rule-bot score to confidence mapping
RULE_SCORE_TO_CONFIDENCE = {4: 6, 5: 7, 6: 8, 7: 9, 8: 9, 9: 9, 10: 9}


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

        # ATR-based stop loss params
        self.atr_sl_multiplier = risk_cfg.get("atr_sl_multiplier", 2.0)
        self.atr_sl_min_pct = risk_cfg.get("atr_sl_min_pct", 3.0)
        self.atr_sl_max_pct = risk_cfg.get("atr_sl_max_pct", 8.0)

        # Max hold time per category (hours)
        # Global override from trading.max_hold_hours (default 4h for ALL coins)
        global_max_hold = config.get("trading", {}).get("max_hold_hours", 4)
        hold_cfg = risk_cfg.get("max_hold_hours", {})
        self.max_hold_hours = {
            "major": min(hold_cfg.get("major", 24), global_max_hold),
            "altcoin": min(hold_cfg.get("altcoin", 8), global_max_hold),
            "memecoin": min(hold_cfg.get("memecoin", 4), global_max_hold),
        }
        logger.info(f"[RiskManager] Max hold hours: {self.max_hold_hours} (global cap: {global_max_hold}h)")

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
        logger.info(f"Risk manager initialized. Balance: EUR {balance:.2f}")

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
                return True, f"Dagligt tab: {daily_loss:.1f}% (graense: {self.daily_loss_limit}%)"

        # Total loss check
        if self.initial_balance and self.initial_balance > 0:
            total_loss = (self.initial_balance - current_balance) / self.initial_balance * 100
            if total_loss >= self.total_loss_limit:
                self.kill_switch_active = True
                logger.critical(f"KILL SWITCH: Total loss limit hit ({total_loss:.1f}%)")
                return True, f"Totalt tab: {total_loss:.1f}% (graense: {self.total_loss_limit}%)"

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

    def get_max_hold_hours(self, epic):
        """Get max hold time in hours based on coin category."""
        cat = self.get_coin_category(epic)
        return self.max_hold_hours.get(cat, 24)

    def get_confidence_multiplier(self, confidence):
        """Get position sizing multiplier based on confidence score."""
        return CONFIDENCE_MULTIPLIER.get(int(confidence), 0.25)

    def map_rule_score_to_confidence(self, rule_score):
        """Map rule-bot signal score to confidence level."""
        return RULE_SCORE_TO_CONFIDENCE.get(min(rule_score, 10), 6)

    def allocate_capital(self, signals, available_balance):
        """Allocate capital across multiple signals weighted by confidence.

        Each signal gets up to max_allocation_pct of available balance,
        scaled by confidence multiplier. Goal: use most of available capital.
        """
        if not signals:
            return []

        max_total = available_balance * (self.max_total_exposure_pct / 100)
        remaining = max_total

        signals = sorted(signals, key=lambda s: s[2], reverse=True)

        allocations = []
        for epic, signal, confidence, details in signals:
            if remaining <= 0:
                break

            max_for_coin = available_balance * (self.get_max_allocation_pct(epic) / 100)
            min_amount = available_balance * (self.min_position_pct / 100)

            # Confidence multiplier scales the max allocation, not a separate factor
            conf_mult = self.get_confidence_multiplier(confidence)
            amount = max_for_coin * conf_mult

            amount = min(amount, remaining)

            if amount < min_amount:
                logger.info(f"Allocation {epic}: skipped (EUR {amount:.0f} < min EUR {min_amount:.0f})")
                continue

            remaining -= amount
            allocations.append((epic, signal, amount, details))

            cat = self.get_coin_category(epic)
            logger.info(
                f"Allocation {epic} ({cat}): EUR {amount:.0f} "
                f"(conf={confidence}, mult={conf_mult:.0%}, max={self.get_max_allocation_pct(epic)}%)"
            )

        return allocations

    def calculate_position_size(self, allocated_amount, price):
        """Calculate position size from allocated EUR amount."""
        effective_amount = allocated_amount * self.leverage
        size = effective_amount / price
        return round(size, 4)

    def calculate_stop_loss(self, entry_price, direction):
        """Calculate fixed percentage stop-loss price (fallback for manual trades)."""
        if direction == "BUY":
            return round(entry_price * (1 - self.stop_loss_pct / 100), 2)
        else:
            return round(entry_price * (1 + self.stop_loss_pct / 100), 2)

    def calculate_atr_stop_loss(self, entry_price, direction, atr_pct):
        """Calculate ATR-based stop-loss price."""
        raw_sl_pct = atr_pct * self.atr_sl_multiplier
        sl_pct = max(self.atr_sl_min_pct, min(self.atr_sl_max_pct, raw_sl_pct))

        if direction == "BUY":
            sl = entry_price * (1 - sl_pct / 100)
        else:
            sl = entry_price * (1 + sl_pct / 100)

        logger.info(
            f"ATR SL: atr={atr_pct:.2f}% x {self.atr_sl_multiplier} = "
            f"{raw_sl_pct:.2f}% -> clamped to {sl_pct:.2f}% -> SL={sl:.4f}"
        )
        return round(sl, 5)

    def calculate_take_profit(self, entry_price, direction, atr_pct=0, sl_price=None):
        """Calculate take-profit price ensuring minimum R:R ratio.

        TP is always at least 1.5x the SL distance (R:R >= 1.5:1).
        Uses ATR×3.0 as base (up from 1.5), clamped [3%, 10%].
        Falls back to fixed TP if ATR not available.
        """
        min_rr_ratio = 1.5  # Minimum reward:risk ratio

        if atr_pct > 0:
            raw_tp_pct = atr_pct * 3.0
            tp_pct = max(3.0, min(10.0, raw_tp_pct))
            logger.info(
                f"ATR TP: atr={atr_pct:.2f}% x 3.0 = {raw_tp_pct:.2f}% -> "
                f"clamped to {tp_pct:.2f}%"
            )
        else:
            tp_pct = self.take_profit_pct

        # Enforce minimum R:R ratio relative to SL
        if sl_price is not None and entry_price > 0:
            sl_distance_pct = abs(entry_price - sl_price) / entry_price * 100
            min_tp_pct = sl_distance_pct * min_rr_ratio
            if tp_pct < min_tp_pct:
                logger.info(
                    f"R:R enforcement: TP {tp_pct:.2f}% < SL {sl_distance_pct:.2f}% x {min_rr_ratio} = {min_tp_pct:.2f}% -> adjusted to {min_tp_pct:.2f}%"
                )
                tp_pct = min_tp_pct

        if direction == "BUY":
            return round(entry_price * (1 + tp_pct / 100), 5)
        else:
            return round(entry_price * (1 - tp_pct / 100), 5)

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
            return False, f"Max positioner naaet ({self.max_open_positions})"

        return True, None

    def update_config(self, config):
        """Update risk parameters from config (for runtime profile switching)."""
        risk_cfg = config.get("risk", {})
        self.stop_loss_pct = risk_cfg.get("stop_loss", self.stop_loss_pct)
        self.take_profit_pct = risk_cfg.get("take_profit", self.take_profit_pct)
        self.trailing_stop_trigger = risk_cfg.get("trailing_stop_trigger", self.trailing_stop_trigger)
        self.max_open_positions = risk_cfg.get("max_open_positions", self.max_open_positions)
        logger.info(f"Risk parameters updated: SL={self.stop_loss_pct}%, TP={self.take_profit_pct}%")
