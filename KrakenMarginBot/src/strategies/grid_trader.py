"""
Grid Trading Strategy (KG1) — Ranging Markets

Places buy orders below current price and sell orders above,
capturing profits from grid spacing as price oscillates.

Active when: ADX < 18 (ranging/sideways market)
Auto-stops when: ADX > 28 (trending market starts)
Coins: BTC/USD, ETH/USD (most liquid)

ChatGPT-tuned (2026-03-14):
- ATR-based grid spacing (min 0.8%, BTC 1.0%, ETH 1.2%)
- Bell curve capital distribution (center levels get 2x, outer 0.5x)
- Smart handoff: cancel only orders >2 levels from price
"""

import logging
import math
import time
from typing import Optional

import numpy as np

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class GridTrader(BaseStrategy):
    """Grid trading for ranging markets."""

    def __init__(self, config):
        super().__init__(config)

        self.grid_levels = self.strategy_cfg.get("grid_levels", 10)
        self.grid_spacing_pct = self.strategy_cfg.get("grid_spacing_pct", 1.0)  # ATR-based preferred
        self.range_detection = self.strategy_cfg.get("range_detection", "auto")
        self.rebalance_interval = self.strategy_cfg.get("rebalance_interval", 3600)
        self.adx_stop_threshold = self.strategy_cfg.get("adx_stop_threshold", 28)
        self.adx_start_threshold = self.strategy_cfg.get("adx_start_threshold", 18)
        self.use_atr_spacing = self.strategy_cfg.get("use_atr_spacing", True)
        self.atr_spacing_mult = self.strategy_cfg.get("atr_spacing_mult", 0.8)

        # Minimum spacing per coin (must cover round-trip fees: maker 0.16% x2 = 0.32%)
        self.min_spacing_pct = {
            "BTC/USD": 1.0, "BTCUSD": 1.0,
            "ETH/USD": 1.2, "ETHUSD": 1.2,
        }
        self.default_min_spacing_pct = 0.8

        # Grid state
        self._grid_active = {}       # {epic: bool}
        self._grid_orders = {}       # {epic: [{"level": float, "side": str, "order_id": str}]}
        self._grid_range = {}        # {epic: {"high": float, "low": float}}
        self._last_rebalance = {}    # {epic: timestamp}
        self._grid_fills = {}        # {epic: int} count of fills for profit tracking

    def get_active_regime(self) -> str:
        return "RANGING"

    def should_be_active(self, regime: str, adx: float) -> bool:
        return adx < self.adx_stop_threshold

    def scan(self, epic: str, prices_data: dict) -> Optional[dict]:
        """Grid strategy scan:
        1. If no grid active: detect range, place grid
        2. If grid active: check for fills, rebalance if needed
        3. If ADX rising > threshold: cancel grid, stop
        """
        df = self.prepare_dataframe(prices_data)
        if df is None or len(df) < 30:
            return None

        current_price = df["close"].iloc[-1]
        adx = self.calculate_adx(df)

        # Auto-stop grid when market starts trending (smart: keep nearby orders)
        if self._grid_active.get(epic, False) and adx > self.adx_stop_threshold:
            logger.info(f"[GRID] {epic}: ADX {adx:.1f} > {self.adx_stop_threshold} — smart grid handoff (trending)")
            self._deactivate_grid(epic, smart=True, current_price=current_price)
            return None

        # Don't start grid in trending market
        if not self._grid_active.get(epic, False) and adx > self.adx_start_threshold:
            return None

        # Setup or manage grid
        if not self._grid_active.get(epic, False):
            return self._setup_grid(epic, df, current_price)
        else:
            return self._manage_grid(epic, df, current_price)

    def _get_min_spacing(self, epic: str) -> float:
        """Get minimum grid spacing for a coin (must exceed round-trip fees)."""
        normalized = epic.replace("/", "")
        return self.min_spacing_pct.get(normalized, self.default_min_spacing_pct)

    def _calculate_bell_curve_weights(self, n_levels: int) -> list:
        """Bell curve distribution: center levels get 2x, outer levels get 0.5x."""
        if n_levels <= 1:
            return [1.0]
        center = (n_levels - 1) / 2.0
        sigma = n_levels / 4.0  # ~68% of weight in center half
        weights = []
        for i in range(n_levels):
            w = math.exp(-0.5 * ((i - center) / sigma) ** 2)
            weights.append(w)
        # Normalize so average = 1.0
        avg_w = sum(weights) / len(weights)
        return [w / avg_w for w in weights]

    def _setup_grid(self, epic: str, df, current_price: float) -> Optional[dict]:
        """Detect range and calculate grid levels with ATR-based spacing."""
        # Calculate ATR-based spacing if enabled
        if self.use_atr_spacing:
            atr = self.calculate_atr(df)
            atr_pct = (atr / current_price) * 100 if current_price > 0 else self.grid_spacing_pct
            spacing_pct = atr_pct * self.atr_spacing_mult
        else:
            spacing_pct = self.grid_spacing_pct

        # Enforce minimum spacing (must exceed round-trip fees)
        min_spacing = self._get_min_spacing(epic)
        if spacing_pct < min_spacing:
            logger.info(f"[GRID] {epic}: ATR spacing {spacing_pct:.2f}% below minimum {min_spacing}%, using minimum")
            spacing_pct = min_spacing

        if self.range_detection == "auto":
            # Use ±range_buffer_pct from current price (default 5%)
            range_buffer = self.strategy_cfg.get("range_buffer_pct", 5.0)
            grid_high = current_price * (1 + range_buffer / 100)
            grid_low = current_price * (1 - range_buffer / 100)
            range_pct = range_buffer * 2

            if range_pct < min_spacing:
                logger.debug(f"[GRID] {epic}: range too narrow ({range_pct:.2f}% < min {min_spacing}%)")
                return None

            self._grid_range[epic] = {"high": grid_high, "low": grid_low}
        else:
            manual = self.strategy_cfg.get("manual_range", {})
            self._grid_range[epic] = {
                "high": manual.get("high", current_price * 1.02),
                "low": manual.get("low", current_price * 0.98),
            }

        grid_range = self._grid_range[epic]

        # Calculate grid levels using spacing_pct
        level_spacing = current_price * (spacing_pct / 100)
        grid_levels = []
        for i in range(1, self.grid_levels + 1):
            buy_level = current_price - (level_spacing * i)
            sell_level = current_price + (level_spacing * i)
            if buy_level >= grid_range["low"]:
                grid_levels.append({"level": round(buy_level, 2), "side": "BUY", "distance": i})
            if sell_level <= grid_range["high"]:
                grid_levels.append({"level": round(sell_level, 2), "side": "SELL", "distance": i})

        if not grid_levels:
            return None

        # Apply bell curve weights for capital distribution
        weights = self._calculate_bell_curve_weights(len(grid_levels))
        for j, lvl in enumerate(grid_levels):
            lvl["weight"] = round(weights[j], 3)

        logger.info(
            f"[GRID] {epic}: Setting up grid with {len(grid_levels)} levels "
            f"(range: {grid_range['low']:.2f} - {grid_range['high']:.2f}, "
            f"spacing: {spacing_pct:.2f}%, ATR-based: {self.use_atr_spacing})"
        )

        self._grid_orders[epic] = grid_levels
        self._grid_active[epic] = True
        self._last_rebalance[epic] = time.time()
        self._grid_fills[epic] = 0

        return {
            "direction": "GRID_SETUP",
            "epic": epic,
            "confidence": 7,
            "entry_price": current_price,
            "signal_type": "GRID_SETUP",
            "grid_levels": grid_levels,
            "grid_range": grid_range,
            "reasons": [
                f"Range detected: {grid_range['low']:.0f}-{grid_range['high']:.0f}",
                f"{len(grid_levels)} grid levels (bell curve weighted)",
                f"Spacing: {spacing_pct:.2f}% ({'ATR-based' if self.use_atr_spacing else 'fixed'})",
            ],
            "details": {
                "range_high": grid_range["high"],
                "range_low": grid_range["low"],
                "level_count": len(grid_levels),
                "spacing_pct": round(spacing_pct, 2),
                "spacing_usd": round(level_spacing, 2),
                "atr_based": self.use_atr_spacing,
                "bell_curve": True,
            },
        }

    def _manage_grid(self, epic: str, df, current_price: float) -> Optional[dict]:
        """Check fills and rebalance grid if needed."""
        now = time.time()
        last_rebalance = self._last_rebalance.get(epic, 0)

        # Check if rebalance needed (price drifted too far from grid center)
        if now - last_rebalance > self.rebalance_interval:
            grid_range = self._grid_range.get(epic, {})
            if grid_range:
                center = (grid_range["high"] + grid_range["low"]) / 2
                drift_pct = abs(current_price - center) / center * 100

                if drift_pct > self.grid_spacing_pct * 3:
                    logger.info(f"[GRID] {epic}: Price drifted {drift_pct:.1f}% from center — rebalancing")
                    self._deactivate_grid(epic)
                    return self._setup_grid(epic, df, current_price)

            self._last_rebalance[epic] = now

        return None

    def _deactivate_grid(self, epic: str, smart: bool = False, current_price: float = 0):
        """Cancel grid orders and deactivate.

        If smart=True (regime handoff), only cancel orders >2 grid levels from price.
        If smart=False (full shutdown), cancel everything.
        """
        if self.client:
            try:
                if smart and current_price > 0:
                    # Smart handoff: keep nearby orders, cancel distant ones
                    orders = self._grid_orders.get(epic, [])
                    cancelled = 0
                    for order in orders:
                        distance = order.get("distance", 999)
                        if distance > 2:
                            # Cancel this order (>2 levels away)
                            order_id = order.get("order_id")
                            if order_id:
                                try:
                                    self.client.cancel_order(order_id)
                                    cancelled += 1
                                except Exception:
                                    pass
                    logger.info(f"[GRID] {epic}: Smart handoff — cancelled {cancelled} distant orders, kept nearby")
                else:
                    cancelled = self.client.cancel_all_orders(epic)
                    logger.info(f"[GRID] {epic}: Cancelled {cancelled} grid orders")
            except Exception as e:
                logger.warning(f"[GRID] {epic}: Failed to cancel orders: {e}")

        self._grid_active[epic] = False
        self._grid_orders.pop(epic, None)
        self._grid_range.pop(epic, None)

    def on_position_opened(self, position_info: dict):
        epic = position_info.get("epic", "")
        self._grid_fills[epic] = self._grid_fills.get(epic, 0) + 1
        logger.info(f"[GRID] {epic}: Fill #{self._grid_fills[epic]}")

    def on_position_closed(self, position_info: dict, exit_price: float, profit_loss: float):
        epic = position_info.get("epic", "")
        logger.info(f"[GRID] {epic}: Position closed at {exit_price}, P/L: {profit_loss:.2f}")

    def get_grid_status(self, epic: str) -> dict:
        """Get current grid status for monitoring."""
        return {
            "active": self._grid_active.get(epic, False),
            "range": self._grid_range.get(epic, {}),
            "orders": len(self._grid_orders.get(epic, [])),
            "fills": self._grid_fills.get(epic, 0),
        }

    def shutdown(self):
        """Cancel all grids on shutdown."""
        for epic in list(self._grid_active.keys()):
            if self._grid_active[epic]:
                self._deactivate_grid(epic)
