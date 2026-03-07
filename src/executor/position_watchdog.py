"""
Position Watchdog - Fast position monitor that runs every 10-15 seconds.
No AI calls, no sentiment - pure price-based protection.

Features:
1. ATR-based dynamic trailing stop (adapts to volatility)
2. Partial profit-taking (close 50% at configurable threshold)
3. Break-even stop move (update on Capital.com server-side)
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionWatchdog:
    """Fast position monitor - checks open positions every 10-15 seconds."""

    def __init__(self, client, risk_manager, notifier, config):
        self.client = client
        self.risk = risk_manager
        self.notifier = notifier

        watchdog_cfg = config.get("watchdog", {})
        self.check_interval = watchdog_cfg.get("check_interval", 12)
        self.trailing_atr_mult = watchdog_cfg.get("trailing_atr_mult", 2.0)
        self.partial_profit_pct = watchdog_cfg.get("partial_profit_pct", 4.0)
        self.partial_close_ratio = watchdog_cfg.get("partial_close_ratio", 0.5)
        self.breakeven_atr_mult = watchdog_cfg.get("breakeven_atr_mult", 1.0)

        # Internal state
        self._running = False
        self._thread = None
        self._atr_cache = {}        # {epic: atr_pct} - updated by main scan
        self._peak_prices = {}      # {deal_id: best price seen}
        self._partial_taken = set() # deal_ids where partial profit was taken
        self._breakeven_set = set() # deal_ids where stop moved to break-even

        logger.info(
            f"Watchdog initialized (interval={self.check_interval}s, "
            f"trailing={self.trailing_atr_mult}xATR, "
            f"partial={self.partial_profit_pct}%@{self.partial_close_ratio*100:.0f}%)"
        )

    def update_atr(self, epic, atr_pct):
        """Called by main scan cycle to cache latest ATR for each coin."""
        self._atr_cache[epic] = atr_pct

    def start(self):
        """Start the watchdog background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info("Position watchdog started")

    def stop(self):
        """Stop the watchdog."""
        self._running = False
        logger.info("Position watchdog stopped")

    def _watch_loop(self):
        """Main watchdog loop - runs every check_interval seconds."""
        while self._running:
            try:
                self._check_positions()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            time.sleep(self.check_interval)

    def _check_positions(self):
        """Check all open positions for trailing stop, partial profit, break-even."""
        try:
            positions = self.client.get_positions()
        except Exception as e:
            logger.warning(f"Watchdog: Could not fetch positions: {e}")
            return

        open_positions = positions.get("positions", [])

        # Clean up tracking for closed positions
        active_deal_ids = {p["position"]["dealId"] for p in open_positions}
        closed_ids = set(self._peak_prices.keys()) - active_deal_ids
        for deal_id in closed_ids:
            self._peak_prices.pop(deal_id, None)
            self._partial_taken.discard(deal_id)
            self._breakeven_set.discard(deal_id)

        for pos in open_positions:
            self._evaluate_position(pos)

    def _evaluate_position(self, pos):
        """Evaluate a single position for all watchdog rules."""
        deal_id = pos["position"]["dealId"]
        epic = pos["market"]["epic"]
        direction = pos["position"]["direction"]
        entry_price = pos["position"]["level"]
        size = pos["position"]["size"]
        current_price = pos["market"]["bid"] if direction == "BUY" else pos["market"]["offer"]

        # Calculate current P/L percentage
        if direction == "BUY":
            pl_pct = (current_price - entry_price) / entry_price * 100
        else:
            pl_pct = (entry_price - current_price) / entry_price * 100

        # Track peak price (best price since entry)
        if deal_id not in self._peak_prices:
            self._peak_prices[deal_id] = current_price
        else:
            if direction == "BUY":
                self._peak_prices[deal_id] = max(self._peak_prices[deal_id], current_price)
            else:
                self._peak_prices[deal_id] = min(self._peak_prices[deal_id], current_price)

        peak = self._peak_prices[deal_id]

        # Calculate drawdown from peak
        if direction == "BUY":
            drawdown_from_peak_pct = (peak - current_price) / peak * 100
            peak_profit_pct = (peak - entry_price) / entry_price * 100
        else:
            drawdown_from_peak_pct = (current_price - peak) / peak * 100
            peak_profit_pct = (entry_price - peak) / entry_price * 100

        # Get ATR for dynamic calculations (default 2% if not cached yet)
        atr_pct = self._atr_cache.get(epic, 2.0)
        trailing_distance = atr_pct * self.trailing_atr_mult

        # ── Rule 1: Break-even stop (server-side on Capital.com) ──
        # When profit exceeds 1x ATR, move stop-loss to entry price
        if deal_id not in self._breakeven_set and pl_pct >= atr_pct * self.breakeven_atr_mult:
            try:
                self.client.update_position(deal_id, stop_loss=round(entry_price, 5))
                self._breakeven_set.add(deal_id)
                logger.info(
                    f"WATCHDOG: Break-even stop set for {epic} "
                    f"(P/L: +{pl_pct:.1f}%, ATR: {atr_pct:.1f}%)"
                )
                self.notifier.send(
                    f"🛡 <b>Break-even stop: {epic}</b>\n"
                    f"P/L: +{pl_pct:.1f}% | Stop flyttet til entry ({entry_price:.4f})"
                )
            except Exception as e:
                logger.warning(f"Watchdog: Failed to set break-even for {epic}: {e}")

        # ── Rule 2: Partial profit-taking ──
        # Close 50% when profit hits threshold
        if deal_id not in self._partial_taken and pl_pct >= self.partial_profit_pct:
            partial_size = round(size * self.partial_close_ratio, 4)
            if partial_size > 0:
                try:
                    close_direction = "SELL" if direction == "BUY" else "BUY"
                    self.client.close_position(deal_id, direction=direction, size=partial_size)
                    self._partial_taken.add(deal_id)
                    logger.info(
                        f"WATCHDOG: Partial profit taken on {epic} "
                        f"(+{pl_pct:.1f}%, closed {partial_size} of {size})"
                    )
                    self.notifier.send(
                        f"💰 <b>Delvis profit: {epic}</b>\n"
                        f"P/L: +{pl_pct:.1f}% | Lukket {partial_size} af {size}\n"
                        f"Resten koerer med trailing stop ({trailing_distance:.1f}%)"
                    )
                except Exception as e:
                    logger.error(f"Watchdog: Partial close failed for {epic}: {e}")

        # ── Rule 3: ATR-based trailing stop ──
        # Only applies when position has been in profit (peak > entry)
        if peak_profit_pct > 0 and drawdown_from_peak_pct > trailing_distance:
            remaining_size = size
            # If partial was taken, the remaining size is smaller
            # Capital.com API returns current size, so we use that
            try:
                logger.warning(
                    f"WATCHDOG: Trailing stop triggered for {epic}! "
                    f"Peak: {peak:.4f}, Now: {current_price:.4f}, "
                    f"Drawdown: {drawdown_from_peak_pct:.1f}% > {trailing_distance:.1f}%"
                )
                self.client.close_position(deal_id, direction=direction, size=remaining_size)
                self.notifier.send(
                    f"🔒 <b>Trailing stop: {epic}</b>\n"
                    f"Peak: {peak:.4f} | Lukket: {current_price:.4f}\n"
                    f"Drawdown fra top: {drawdown_from_peak_pct:.1f}% (graense: {trailing_distance:.1f}%)\n"
                    f"Profit fra entry: {pl_pct:+.1f}%"
                )
            except Exception as e:
                logger.error(f"Watchdog: Trailing close failed for {epic}: {e}")

    def get_status(self):
        """Get watchdog status for /status command."""
        return {
            "running": self._running,
            "interval": self.check_interval,
            "tracked_positions": len(self._peak_prices),
            "partial_taken": len(self._partial_taken),
            "breakeven_set": len(self._breakeven_set),
            "atr_cache": {k: f"{v:.2f}%" for k, v in self._atr_cache.items()},
        }
