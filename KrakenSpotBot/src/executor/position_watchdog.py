"""
Position Watchdog for KrakenBots — simplified for spot trading.

Monitors open positions every 12 seconds:
1. Max hold time enforcement
2. Break-even stop at profit threshold
3. Trailing stop (ATR-based)
4. Partial profit-taking
5. Profit pullback close

Lighter than RuleBot watchdog — no chart analysis, no sentiment,
no scale-in, no cycle trading. Pure price-based protection.
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionWatchdog:
    """Fast position monitor for KrakenBots."""

    def __init__(self, client, risk_manager, notifier, config, executor=None):
        self.client = client
        self.risk = risk_manager
        self.notifier = notifier
        self.executor = executor

        watchdog_cfg = config.get("watchdog", {})
        self.check_interval = watchdog_cfg.get("check_interval", 12)
        self.breakeven_trigger_pct = watchdog_cfg.get("breakeven_trigger_pct", 2.5)
        self.progressive_sl_trigger_pct = watchdog_cfg.get("progressive_sl_trigger_pct", 3.0)
        self.trailing_atr_mult = watchdog_cfg.get("trailing_atr_mult", 1.5)
        self.partial_profit_pct = watchdog_cfg.get("partial_profit_pct", 6.0)
        self.partial_close_ratio = watchdog_cfg.get("partial_close_ratio", 0.3)
        self.pullback_peak_trigger_pct = watchdog_cfg.get("pullback_peak_trigger_pct", 4.0)
        self.pullback_min_profit_pct = watchdog_cfg.get("pullback_min_profit_pct", 1.5)

        # Internal state
        self._running = False
        self._thread = None
        self._atr_cache = {}         # {epic: atr_value}
        self._entry_times = {}       # {deal_id: datetime}
        self._peak_profits = {}      # {deal_id: max_profit_pct}
        self._breakeven_set = set()  # deal_ids where break-even was set
        self._partial_taken = set()  # deal_ids where partial was taken

        # Adaptive trailing stop metadata (from trend follower)
        # {deal_id: {"initial_risk": float, "trailing_levels": dict, ...}}
        self._adaptive_meta = {}

        # Strategy reference (set externally)
        self.strategy = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"Position watchdog started (interval: {self.check_interval}s)")

    def stop(self):
        self._running = False

    def update_atr(self, epic: str, atr_value: float):
        self._atr_cache[epic] = atr_value
        # Track ATR history for volatility guard (keep last 20 values)
        if not hasattr(self, '_atr_history'):
            self._atr_history = {}
        if epic not in self._atr_history:
            self._atr_history[epic] = []
        self._atr_history[epic].append(atr_value)
        if len(self._atr_history[epic]) > 20:
            self._atr_history[epic] = self._atr_history[epic][-20:]

    def track_entry(self, deal_id: str, epic: str, signal_details: dict = None):
        self._entry_times[deal_id] = datetime.now()
        # Store adaptive trailing metadata if present (from trend follower)
        if signal_details and signal_details.get("adaptive_trailing"):
            self._adaptive_meta[deal_id] = {
                "initial_risk": signal_details.get("initial_risk", 0),
                "trailing_levels": signal_details.get("trailing_levels", {}),
                "partial_exit_r": signal_details.get("partial_exit_r", 2.0),
                "partial_exit_ratio": signal_details.get("partial_exit_ratio", 0.5),
            }
            logger.info(f"[WATCHDOG] {epic}: Adaptive trailing enabled (1R = ${self._adaptive_meta[deal_id]['initial_risk']:.2f})")

    def _watch_loop(self):
        while self._running:
            try:
                self._check_positions()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            time.sleep(self.check_interval)

    def _check_positions(self):
        positions = self.client.get_positions()
        pos_list = positions.get("positions", [])

        if not pos_list:
            return

        # Clean up tracking for closed positions
        active_ids = {p["position"]["dealId"] for p in pos_list}
        closed = set(self._entry_times.keys()) - active_ids
        for deal_id in closed:
            self._entry_times.pop(deal_id, None)
            self._peak_profits.pop(deal_id, None)
            self._breakeven_set.discard(deal_id)
            self._partial_taken.discard(deal_id)

        for pos in pos_list:
            self._check_single_position(pos)

    def _check_single_position(self, pos):
        deal_id = pos["position"]["dealId"]
        epic = pos["position"]["epic"]
        direction = pos["position"]["direction"]
        entry_price = pos["position"]["level"]
        size = pos["position"]["size"]
        current_bid = pos["market"].get("bid", entry_price)
        current_offer = pos["market"].get("offer", entry_price)

        # Current price based on direction
        if direction == "BUY":
            current_price = current_bid
            profit_pct = (current_price - entry_price) / entry_price * 100
        else:
            current_price = current_offer
            profit_pct = (entry_price - current_price) / entry_price * 100

        # Track peak profit
        peak = self._peak_profits.get(deal_id, profit_pct)
        if profit_pct > peak:
            peak = profit_pct
            self._peak_profits[deal_id] = peak

        # Rule 1: Max hold time
        if self._check_max_hold(deal_id, epic, profit_pct, direction, size):
            return

        # Check if this position uses adaptive trailing (trend follower)
        adaptive = self._adaptive_meta.get(deal_id)
        if adaptive and adaptive["initial_risk"] > 0:
            self._handle_adaptive_trailing(deal_id, epic, entry_price, current_price, direction, size, profit_pct, adaptive)
        else:
            # Standard watchdog rules for non-trend strategies
            # Rule 2: Break-even stop
            if deal_id not in self._breakeven_set and profit_pct >= self.breakeven_trigger_pct:
                self._set_breakeven(deal_id, epic, entry_price, direction)

            # Rule 3: Progressive trailing stop
            if profit_pct >= self.progressive_sl_trigger_pct:
                self._update_trailing_stop(deal_id, epic, entry_price, current_price, direction, profit_pct)

            # Rule 4: Partial profit-taking
            if deal_id not in self._partial_taken and profit_pct >= self.partial_profit_pct:
                self._take_partial_profit(deal_id, epic, direction, size, current_price, profit_pct)

        # Rule 5: Profit pullback close
        if peak >= self.pullback_peak_trigger_pct and profit_pct >= self.pullback_min_profit_pct:
            pullback = peak - profit_pct
            if pullback >= 1.5:  # Gave back 1.5%+ from peak
                self._close_position(deal_id, epic, direction, size, current_price,
                                     f"Pullback close: peak {peak:.1f}% → {profit_pct:.1f}%")

    def _handle_adaptive_trailing(self, deal_id, epic, entry_price, current_price, direction, size, profit_pct, adaptive):
        """Adaptive trailing stop for trend follower (ChatGPT-tuned).

        Levels:
        - Profit >= 1R: Move SL to breakeven (entry price)
        - Profit >= 2R: Tighten SL to ATR × 2.0 from current price + partial exit 50%
        - Profit >= 3R: Tighten SL to ATR × 1.5 from current price
        """
        initial_risk = adaptive["initial_risk"]  # 1R in USD
        levels = adaptive["trailing_levels"]
        atr = self._atr_cache.get(epic, 0)

        # Calculate current profit in R-multiples
        if direction == "BUY":
            profit_usd = current_price - entry_price
        else:
            profit_usd = entry_price - current_price
        r_multiple = profit_usd / initial_risk if initial_risk > 0 else 0

        # Volatility guard (ChatGPT): widen trailing in explosive trends
        # If ATR is expanding rapidly, don't tighten stop too much
        atr_bonus = 0.0
        if hasattr(self, '_atr_history') and epic in self._atr_history:
            avg_atr = sum(self._atr_history[epic]) / len(self._atr_history[epic])
            if avg_atr > 0 and atr > avg_atr * 1.8:
                atr_bonus = 0.5
                logger.debug(f"[WATCHDOG] {epic}: Volatility guard active — widening trail by +{atr_bonus}")

        # Level 3: >= 3R → trail at ATR × 1.5 (+ volatility bonus)
        if r_multiple >= levels.get("tight_2_r", 3.0) and atr > 0:
            trail_mult = levels.get("tight_2_atr", 1.5) + atr_bonus
            trail_dist = atr * trail_mult
            if direction == "BUY":
                new_sl = current_price - trail_dist
                if new_sl > entry_price:
                    self._try_update_sl(deal_id, epic, new_sl, f"Adaptive trail {r_multiple:.1f}R → ATR×{trail_mult}")
            else:
                new_sl = current_price + trail_dist
                if new_sl < entry_price:
                    self._try_update_sl(deal_id, epic, new_sl, f"Adaptive trail {r_multiple:.1f}R → ATR×{trail_mult}")

        # Level 2: >= 2R → trail at ATR × 2.0 + partial exit (+ volatility bonus)
        elif r_multiple >= levels.get("tight_1_r", 2.0) and atr > 0:
            trail_mult = levels.get("tight_1_atr", 2.0) + atr_bonus
            trail_dist = atr * trail_mult
            if direction == "BUY":
                new_sl = current_price - trail_dist
                if new_sl > entry_price:
                    self._try_update_sl(deal_id, epic, new_sl, f"Adaptive trail {r_multiple:.1f}R → ATR×{trail_mult}")
            else:
                new_sl = current_price + trail_dist
                if new_sl < entry_price:
                    self._try_update_sl(deal_id, epic, new_sl, f"Adaptive trail {r_multiple:.1f}R → ATR×{trail_mult}")

            # Partial exit at 2R (50%)
            if deal_id not in self._partial_taken:
                partial_ratio = adaptive.get("partial_exit_ratio", 0.5)
                partial_size = round(size * partial_ratio, 6)
                if partial_size > 0:
                    self._take_partial_profit(deal_id, epic, direction, size, current_price, profit_pct)
                    logger.info(f"[WATCHDOG] {epic}: Adaptive partial exit at {r_multiple:.1f}R ({partial_ratio:.0%})")

        # Level 1: >= 1R → breakeven
        elif r_multiple >= levels.get("breakeven_r", 1.0):
            if deal_id not in self._breakeven_set:
                self._set_breakeven(deal_id, epic, entry_price, direction)
                logger.info(f"[WATCHDOG] {epic}: Adaptive breakeven at {r_multiple:.1f}R")

    def _try_update_sl(self, deal_id, epic, new_sl, reason):
        """Try to update stop loss, only moving it in the protective direction."""
        try:
            self.client.update_position(deal_id, stop_loss=round(new_sl, 2))
            logger.info(f"[WATCHDOG] {epic}: {reason} — SL → {new_sl:.2f}")
        except Exception as e:
            logger.warning(f"Adaptive SL update failed for {deal_id}: {e}")

    def _check_max_hold(self, deal_id, epic, profit_pct, direction, size) -> bool:
        entry_time = self._entry_times.get(deal_id)
        if not entry_time:
            return False

        max_hours = self.risk.get_max_hold_hours(epic)
        elapsed_hours = (datetime.now() - entry_time).total_seconds() / 3600

        if elapsed_hours >= max_hours and profit_pct <= 0.5:
            current_price = self._get_current_price(epic, direction)
            self._close_position(deal_id, epic, direction, size, current_price,
                                 f"Max hold {max_hours}h exceeded ({elapsed_hours:.1f}h)")
            return True
        return False

    def _set_breakeven(self, deal_id, epic, entry_price, direction):
        try:
            # Move SL to entry price (break-even)
            self.client.update_position(deal_id, stop_loss=round(entry_price, 2))
            self._breakeven_set.add(deal_id)
            logger.info(f"[WATCHDOG] {epic}: Break-even stop set at {entry_price}")
            self.notifier.send(f"🔒 {epic}: SL moved to break-even ({entry_price:.2f})")
        except Exception as e:
            logger.warning(f"Failed to set break-even for {deal_id}: {e}")

    def _update_trailing_stop(self, deal_id, epic, entry_price, current_price, direction, profit_pct):
        atr = self._atr_cache.get(epic, 0)
        if atr == 0:
            return

        trail_distance = atr * self.trailing_atr_mult
        if direction == "BUY":
            new_sl = current_price - trail_distance
            # Only move SL up, never down
            if new_sl > entry_price:
                try:
                    self.client.update_position(deal_id, stop_loss=round(new_sl, 2))
                    logger.info(f"[WATCHDOG] {epic}: Trailing SL updated to {new_sl:.2f} (profit: {profit_pct:.1f}%)")
                except Exception as e:
                    logger.warning(f"Trailing stop update failed: {e}")
        else:
            new_sl = current_price + trail_distance
            if new_sl < entry_price:
                try:
                    self.client.update_position(deal_id, stop_loss=round(new_sl, 2))
                    logger.info(f"[WATCHDOG] {epic}: Trailing SL updated to {new_sl:.2f} (profit: {profit_pct:.1f}%)")
                except Exception as e:
                    logger.warning(f"Trailing stop update failed: {e}")

    def _take_partial_profit(self, deal_id, epic, direction, size, current_price, profit_pct):
        partial_size = round(size * self.partial_close_ratio, 6)
        if partial_size <= 0:
            return

        try:
            self.client.close_position(deal_id, direction=direction, size=partial_size, epic=epic)
            self._partial_taken.add(deal_id)

            # Calculate partial P/L
            entry_price = self._get_entry_price(deal_id)
            if entry_price and direction == "BUY":
                partial_pl = (current_price - entry_price) * partial_size
            elif entry_price:
                partial_pl = (entry_price - current_price) * partial_size
            else:
                partial_pl = 0

            logger.info(f"[WATCHDOG] {epic}: Partial close {self.partial_close_ratio:.0%} @ {current_price} (P/L: ${partial_pl:.2f})")
            self.notifier.send(f"💰 {epic}: Partial profit ({self.partial_close_ratio:.0%}) at {profit_pct:.1f}%, P/L: ${partial_pl:.2f}")

            if self.executor:
                self.executor.update_trade_close(deal_id, current_price, partial_pl, epic=epic, exit_reason="partial_profit")
        except Exception as e:
            logger.warning(f"Partial close failed for {deal_id}: {e}")

    def _close_position(self, deal_id, epic, direction, size, current_price, reason):
        try:
            self.client.close_position(deal_id, direction=direction, size=size, epic=epic)

            entry_price = self._get_entry_price(deal_id)
            if entry_price and direction == "BUY":
                pl = (current_price - entry_price) * size
            elif entry_price:
                pl = (entry_price - current_price) * size
            else:
                pl = 0

            logger.info(f"[WATCHDOG] {epic}: Closed — {reason} (P/L: ${pl:.2f})")
            emoji = "✅" if pl >= 0 else "❌"
            self.notifier.send(f"{emoji} {epic}: Closed — {reason}\nP/L: ${pl:.2f}")

            if self.executor:
                self.executor.update_trade_close(deal_id, current_price, pl, epic=epic, exit_reason=reason)

            # Notify strategy
            if self.strategy:
                self.strategy.on_position_closed(
                    {"deal_id": deal_id, "epic": epic, "direction": direction},
                    current_price, pl
                )
        except Exception as e:
            logger.error(f"Close position failed for {deal_id}: {e}")

    def _get_entry_price(self, deal_id) -> float:
        """Get entry price from position tracker."""
        if hasattr(self.client, 'position_tracker') and self.client.position_tracker:
            pos = self.client.position_tracker.get_position(deal_id)
            if pos:
                return pos["entry_price"]
        return 0

    def _get_current_price(self, epic, direction) -> float:
        """Get current price for closing."""
        try:
            info = self.client.get_market_info(epic)
            if direction == "BUY":
                return info.get("snapshot", {}).get("bid", 0)
            return info.get("snapshot", {}).get("offer", 0)
        except Exception:
            return 0
