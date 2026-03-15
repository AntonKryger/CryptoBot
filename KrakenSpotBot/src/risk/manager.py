"""
Risk Manager for KrakenBots — adapted for spot trading (no leverage).

Key differences from RuleBot's RiskManager:
- No leverage (spot = 1:1, unless futures mode)
- Position sizing in coin units (not EUR-leveraged)
- USD-based (not EUR)
- Exposure tracking works with coordinator
- Graduated kill switch (ChatGPT-tuned: 3%→reduce, 4%→stop, 5%→kill)
- Strategy decay detection (Sharpe < 0.5 for 60 days → disable)
"""

import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)

# Coin categories for position sizing
MAJORS = {"BTC/USD", "BTCUSD", "ETH/USD", "ETHUSD"}
ALTCOINS = {"SOL/USD", "SOLUSD", "AVAX/USD", "AVAXUSD", "LINK/USD", "LINKUSD", "LTC/USD", "LTCUSD"}

# Confidence multiplier lookup
CONFIDENCE_MULTIPLIER = {
    1: 0.20, 2: 0.20, 3: 0.20, 4: 0.25, 5: 0.30,
    6: 0.50, 7: 0.70, 8: 0.85, 9: 1.00, 10: 1.00,
}


class SpotRiskManager:
    """Manages position sizing, stop-loss, take-profit for spot trading."""

    def __init__(self, config):
        risk_cfg = config.get("risk", {})
        self.stop_loss_pct = risk_cfg.get("stop_loss", 4.0)
        self.take_profit_pct = risk_cfg.get("take_profit", 7.0)
        self.max_open_positions = risk_cfg.get("max_open_positions", 5)
        self.daily_loss_limit = risk_cfg.get("daily_loss_limit", 5.0)
        self.total_loss_limit = risk_cfg.get("total_loss_limit", 30.0)

        # Spot: leverage = 1 unless futures mode
        trading_cfg = config.get("trading", {})
        exchange_cfg = config.get("exchange", {})
        mode = exchange_cfg.get("mode", "spot")
        self.leverage = trading_cfg.get("leverage", 1) if mode == "futures" else 1

        # ATR-based stop loss
        self.atr_sl_multiplier = risk_cfg.get("atr_sl_multiplier", 2.0)
        self.atr_sl_min_pct = risk_cfg.get("atr_sl_min_pct", 2.0)
        self.atr_sl_max_pct = risk_cfg.get("atr_sl_max_pct", 6.0)

        # Capital allocation
        alloc_cfg = risk_cfg.get("allocation", {})
        self.max_total_exposure_pct = alloc_cfg.get("max_total_exposure", 80)
        self.max_major_pct = alloc_cfg.get("max_major", 25)
        self.max_altcoin_pct = alloc_cfg.get("max_altcoin", 15)
        self.min_position_pct = alloc_cfg.get("min_position", 3)

        # Max hold time
        global_max_hold = trading_cfg.get("max_hold_hours", 24)
        hold_cfg = risk_cfg.get("max_hold_hours", {})
        self.max_hold_hours = {
            "major": min(hold_cfg.get("major", 24), global_max_hold),
            "altcoin": min(hold_cfg.get("altcoin", 8), global_max_hold),
        }

        # Graduated kill switch thresholds (ChatGPT-tuned)
        self.graduated_thresholds = risk_cfg.get("graduated_thresholds", {
            "reduce_pct": 3.0,       # 3% daily loss → reduce position sizes 50%
            "stop_new_pct": 4.0,     # 4% daily loss → stop opening new trades
            "close_all_pct": 5.0,    # 5% daily loss → close everything
        })

        self.daily_start_balance = None
        self.initial_balance = None
        self.kill_switch_active = False
        self.risk_level = "normal"  # normal | reduced | stopped | killed
        self.daily_reset_date = None

    def initialize(self, balance):
        self.initial_balance = balance
        self.daily_start_balance = balance
        self.daily_reset_date = datetime.now().date()
        self.kill_switch_active = False
        logger.info(f"Risk manager initialized. Balance: ${balance:.2f}")

    def check_kill_switch(self, current_balance):
        """Graduated kill switch (ChatGPT-tuned):
        - 3% daily loss → reduce position sizes 50%
        - 4% daily loss → stop opening new trades
        - 5% daily loss → close everything (full kill)
        """
        today = datetime.now().date()
        if today != self.daily_reset_date:
            self.daily_start_balance = current_balance
            self.daily_reset_date = today
            self.risk_level = "normal"
            self.kill_switch_active = False

        daily_loss = 0
        if self.daily_start_balance and self.daily_start_balance > 0:
            daily_loss = (self.daily_start_balance - current_balance) / self.daily_start_balance * 100

        total_loss = 0
        if self.initial_balance and self.initial_balance > 0:
            total_loss = (self.initial_balance - current_balance) / self.initial_balance * 100

        # Total loss limit (hard kill)
        if total_loss >= self.total_loss_limit:
            self.kill_switch_active = True
            self.risk_level = "killed"
            return True, f"Total loss: {total_loss:.1f}% (limit: {self.total_loss_limit}%)"

        # Graduated daily loss
        thresholds = self.graduated_thresholds
        if daily_loss >= thresholds["close_all_pct"]:
            self.kill_switch_active = True
            self.risk_level = "killed"
            return True, f"Daily loss: {daily_loss:.1f}% — CLOSE ALL (limit: {thresholds['close_all_pct']}%)"
        elif daily_loss >= thresholds["stop_new_pct"]:
            self.risk_level = "stopped"
            logger.warning(f"Risk level: STOPPED — daily loss {daily_loss:.1f}% >= {thresholds['stop_new_pct']}%")
            return False, None
        elif daily_loss >= thresholds["reduce_pct"]:
            self.risk_level = "reduced"
            logger.warning(f"Risk level: REDUCED — daily loss {daily_loss:.1f}% >= {thresholds['reduce_pct']}%")
            return False, None
        else:
            self.risk_level = "normal"

        return False, None

    def get_coin_category(self, epic):
        normalized = epic.replace("/", "")
        if normalized in {"BTCUSD", "ETHUSD"}:
            return "major"
        return "altcoin"

    def get_max_allocation_pct(self, epic):
        cat = self.get_coin_category(epic)
        if cat == "major":
            return self.max_major_pct
        return self.max_altcoin_pct

    def get_max_hold_hours(self, epic):
        cat = self.get_coin_category(epic)
        return self.max_hold_hours.get(cat, 24)

    def can_open_position(self, open_count, balance, current_balance):
        if self.kill_switch_active:
            return False, "Kill switch active"
        killed, reason = self.check_kill_switch(current_balance)
        if killed:
            return False, reason
        # Graduated: "stopped" level blocks new trades
        if self.risk_level == "stopped":
            return False, "Risk level STOPPED — no new trades (daily loss >= 4%)"
        if open_count >= self.max_open_positions:
            return False, f"Max positions reached ({self.max_open_positions})"
        return True, None

    def calculate_position_size(self, allocated_amount, price):
        """Calculate position size in coin units for spot.
        Applies 50% reduction when risk_level == 'reduced' (graduated kill switch).
        """
        effective_amount = allocated_amount * self.leverage
        # Graduated risk: reduce size by 50% when daily loss >= 3%
        if self.risk_level == "reduced":
            effective_amount *= 0.5
            logger.info(f"Position size reduced 50% (risk level: {self.risk_level})")
        size = effective_amount / price
        # Round to appropriate precision based on coin price
        if price > 10000:
            return round(size, 6)  # BTC
        elif price > 100:
            return round(size, 4)  # ETH
        else:
            return round(size, 2)  # ALT

    def calculate_stop_loss(self, entry_price, direction):
        if direction == "BUY":
            return round(entry_price * (1 - self.stop_loss_pct / 100), 2)
        else:
            return round(entry_price * (1 + self.stop_loss_pct / 100), 2)

    def calculate_atr_stop_loss(self, entry_price, direction, atr_pct):
        raw_sl_pct = atr_pct * self.atr_sl_multiplier
        sl_pct = max(self.atr_sl_min_pct, min(self.atr_sl_max_pct, raw_sl_pct))

        if direction == "BUY":
            sl = entry_price * (1 - sl_pct / 100)
        else:
            sl = entry_price * (1 + sl_pct / 100)

        logger.info(f"ATR SL: atr={atr_pct:.2f}% x {self.atr_sl_multiplier} = {raw_sl_pct:.2f}% -> {sl_pct:.2f}%")
        return round(sl, 2)

    def calculate_take_profit(self, entry_price, direction, atr_pct=0, sl_price=None):
        min_rr_ratio = 2.0

        if atr_pct > 0:
            raw_tp_pct = atr_pct * 3.0
            tp_pct = max(3.0, min(10.0, raw_tp_pct))
        else:
            tp_pct = self.take_profit_pct

        if sl_price is not None and entry_price > 0:
            sl_distance_pct = abs(entry_price - sl_price) / entry_price * 100
            min_tp_pct = sl_distance_pct * min_rr_ratio
            if tp_pct < min_tp_pct:
                tp_pct = min_tp_pct

        if direction == "BUY":
            return round(entry_price * (1 + tp_pct / 100), 2)
        else:
            return round(entry_price * (1 - tp_pct / 100), 2)

    def allocate_capital(self, signals, available_balance):
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
            conf_mult = CONFIDENCE_MULTIPLIER.get(int(confidence), 0.25)
            amount = max_for_coin * conf_mult
            amount = min(amount, remaining)

            if amount < min_amount:
                continue

            remaining -= amount
            allocations.append((epic, signal, amount, details))
            logger.info(f"Allocation {epic}: ${amount:.0f} (conf={confidence}, mult={conf_mult:.0%})")

        return allocations

    def check_strategy_decay(self, trade_history: list, window_days: int = 60) -> dict:
        """Strategy decay detection (ChatGPT): disable bot if Sharpe < 0.5 for 60 days.

        Args:
            trade_history: List of closed trades with 'profit_loss' and 'exit_timestamp'
            window_days: Rolling window in days

        Returns: {"decayed": bool, "sharpe": float, "trade_count": int, "recommendation": str}
        """
        now = datetime.now()
        recent_pls = []
        for trade in trade_history:
            if trade.get("status") != "CLOSED" or trade.get("profit_loss") is None:
                continue
            try:
                exit_time = datetime.fromisoformat(trade["exit_timestamp"])
                if (now - exit_time).days <= window_days:
                    recent_pls.append(trade["profit_loss"])
            except (ValueError, KeyError, TypeError):
                continue

        if len(recent_pls) < 50:
            return {"decayed": False, "sharpe": 0, "trade_count": len(recent_pls),
                    "recommendation": f"Insufficient data ({len(recent_pls)} trades, need 50+)"}

        avg_pl = sum(recent_pls) / len(recent_pls)
        variance = sum((pl - avg_pl) ** 2 for pl in recent_pls) / len(recent_pls)
        std_pl = math.sqrt(variance) if variance > 0 else 0.001
        sharpe = (avg_pl / std_pl) * math.sqrt(252) if std_pl > 0 else 0  # Annualized

        decayed = sharpe < 0.5
        if decayed:
            recommendation = f"STRATEGY DECAY: Sharpe {sharpe:.2f} < 0.5 over {window_days} days. Consider disabling bot."
        else:
            recommendation = f"Strategy healthy: Sharpe {sharpe:.2f} over {window_days} days"

        return {
            "decayed": decayed,
            "sharpe": round(sharpe, 2),
            "trade_count": len(recent_pls),
            "avg_pl": round(avg_pl, 2),
            "recommendation": recommendation,
        }
