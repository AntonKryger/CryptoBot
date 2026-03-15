"""
Volatility/Crash Bot Strategy (KV1) — Extreme Events

Monitors for sudden price drops (flash crashes) and buys the panic.
Counter-trend with tight stop, targeting quick 1-2% bounce.
Highest priority — can override other bots via coordinator.

Active when: Volatility spike detected (per-asset thresholds)
Coins: All 6 (opportunistic, event-driven)
Max hold: 30 minutes

ChatGPT-tuned (2026-03-14):
- Per-asset crash thresholds: BTC 2%, ETH 2.5%, alts 4-5% (was flat 3%)
"""

import logging
import time
from typing import Optional

import numpy as np

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class VolatilityTrader(BaseStrategy):
    """Flash crash / volatility spike bot — buy the panic."""

    def __init__(self, config):
        super().__init__(config)

        # Per-asset crash thresholds (ChatGPT: BTC/ETH drop less for same significance)
        self.crash_thresholds = self.strategy_cfg.get("crash_thresholds", {
            "BTC/USD": 2.0, "BTCUSD": 2.0,
            "ETH/USD": 2.5, "ETHUSD": 2.5,
            "SOL/USD": 4.0, "SOLUSD": 4.0,
            "AVAX/USD": 5.0, "AVAXUSD": 5.0,
            "LINK/USD": 4.0, "LINKUSD": 4.0,
            "LTC/USD": 4.0, "LTCUSD": 4.0,
        })
        self.crash_threshold_pct = self.strategy_cfg.get("crash_threshold_pct", 3.0)  # Fallback
        self.bounce_target_pct = self.strategy_cfg.get("bounce_target_pct", 1.5)
        self.max_hold_minutes = self.strategy_cfg.get("max_hold_minutes", 30)
        self.orderbook_depth = self.strategy_cfg.get("orderbook_depth", 20)
        self.scan_interval = self.strategy_cfg.get("scan_interval", 30)
        self.spike_up_threshold_pct = self.strategy_cfg.get("spike_up_threshold_pct", 4.0)
        self.atr_expansion_mult = self.strategy_cfg.get("atr_expansion_mult", 2.5)
        self.bb_width_threshold = self.strategy_cfg.get("bb_width_threshold", 5.0)
        self.max_active_positions = self.strategy_cfg.get("max_active_positions", 2)
        self.cooldown_minutes = self.strategy_cfg.get("cooldown_minutes", 15)

        # State tracking
        self._last_trigger = {}      # {epic: timestamp}
        self._active_positions = {}  # {epic: count}

    def get_active_regime(self) -> str:
        return "ANY"

    def should_be_active(self, regime: str, adx: float) -> bool:
        # Volatility bot is ALWAYS scanning — event-driven, not regime-gated
        return True

    def scan(self, epic: str, prices_data: dict) -> Optional[dict]:
        """Volatility scan:
        1. Detect sudden price drop > crash_threshold in last 15 min
        2. Check ATR expansion (current ATR >> recent average)
        3. Bollinger Band width expansion
        4. Orderbook depth for support detection
        5. Buy into panic with tight stop and quick target
        """
        df = self.prepare_dataframe(prices_data)
        if df is None or len(df) < 30:
            return None

        # Check cooldown
        last_trigger = self._last_trigger.get(epic, 0)
        if time.time() - last_trigger < self.cooldown_minutes * 60:
            return None

        # Check max positions
        if self._active_positions.get(epic, 0) >= self.max_active_positions:
            return None

        current_price = df["close"].iloc[-1]
        atr = self.calculate_atr(df)
        atr_pct = self.calculate_atr_pct(df)

        # --- Crash Detection ---
        # Check price change over last N bars (15m candles: 1 bar = 15 min)
        lookback = min(4, len(df) - 1)  # ~1 hour for 15m candles
        recent_high = df["high"].tail(lookback).max()
        price_drop_pct = (recent_high - current_price) / recent_high * 100

        # Check for price spike up (short opportunity)
        recent_low = df["low"].tail(lookback).min()
        price_spike_pct = (current_price - recent_low) / recent_low * 100

        # --- ATR Expansion ---
        atr_values = []
        for i in range(max(1, len(df) - 20), len(df)):
            h = df["high"].iloc[i]
            l = df["low"].iloc[i]
            c_prev = df["close"].iloc[i - 1] if i > 0 else df["close"].iloc[i]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            atr_values.append(tr)

        if len(atr_values) >= 5:
            recent_atr = np.mean(atr_values[-3:])  # last 3 bars
            avg_atr = np.mean(atr_values)
            atr_expansion = recent_atr / avg_atr if avg_atr > 0 else 1
        else:
            atr_expansion = 1.0

        # --- Bollinger Band Width ---
        bb_period = 20
        if len(df) >= bb_period:
            bb_mid = df["close"].rolling(window=bb_period).mean().iloc[-1]
            bb_std = df["close"].rolling(window=bb_period).std().iloc[-1]
            bb_width_pct = (bb_std * 4 / bb_mid * 100) if bb_mid > 0 else 0
        else:
            bb_width_pct = 0

        # --- Signal Generation ---
        reasons = []
        confidence = 0
        direction = None

        # Get per-asset crash threshold (ChatGPT: BTC=2%, ETH=2.5%, alts=4-5%)
        epic_normalized = epic.replace("/", "")
        crash_threshold = self.crash_thresholds.get(epic, self.crash_thresholds.get(epic_normalized, self.crash_threshold_pct))

        # Flash Crash (BUY the dip)
        if price_drop_pct >= crash_threshold:
            direction = "BUY"
            confidence += 4
            reasons.append(f"Flash crash: -{price_drop_pct:.1f}% in {lookback} bars")

            if atr_expansion >= self.atr_expansion_mult:
                confidence += 2
                reasons.append(f"ATR expansion {atr_expansion:.1f}x")

            if bb_width_pct > self.bb_width_threshold:
                confidence += 1
                reasons.append(f"BB width expanded ({bb_width_pct:.1f}%)")

            # Volume confirmation (panic selling = high volume)
            vol_avg = df["volume"].rolling(20).mean().iloc[-1]
            if vol_avg > 0 and df["volume"].iloc[-1] > vol_avg * 2:
                confidence += 1
                reasons.append(f"Panic volume {df['volume'].iloc[-1] / vol_avg:.1f}x")

        # Blow-off top (SELL the spike) — less common, requires bigger threshold
        elif price_spike_pct >= self.spike_up_threshold_pct:
            direction = "SELL"
            confidence += 3
            reasons.append(f"Blow-off spike: +{price_spike_pct:.1f}% in {lookback} bars")

            if atr_expansion >= self.atr_expansion_mult:
                confidence += 2
                reasons.append(f"ATR expansion {atr_expansion:.1f}x")

        if direction is None or confidence < 5:
            return None

        # Calculate tight SL/TP
        if direction == "BUY":
            stop_loss = current_price - (atr * 1.5)  # Tight stop
            take_profit = current_price * (1 + self.bounce_target_pct / 100)
        else:
            stop_loss = current_price + (atr * 1.5)
            take_profit = current_price * (1 - self.bounce_target_pct / 100)

        confidence = min(confidence, 10)

        logger.info(
            f"[VOLATILITY] {epic}: {direction} signal (conf={confidence}, "
            f"drop={price_drop_pct:.1f}%, ATR exp={atr_expansion:.1f}x)"
        )

        self._last_trigger[epic] = time.time()

        return {
            "direction": direction,
            "epic": epic,
            "confidence": confidence,
            "entry_price": current_price,
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "signal_type": f"VOLATILITY_{direction}",
            "reasons": reasons,
            "details": {
                "price_drop_pct": round(price_drop_pct, 2),
                "price_spike_pct": round(price_spike_pct, 2),
                "atr_expansion": round(atr_expansion, 2),
                "bb_width_pct": round(bb_width_pct, 2),
                "atr": round(atr, 2),
                "atr_pct": round(atr_pct, 2),
                "max_hold_minutes": self.max_hold_minutes,
                "bounce_target_pct": self.bounce_target_pct,
            },
        }

    def on_position_opened(self, position_info: dict):
        epic = position_info.get("epic", "")
        self._active_positions[epic] = self._active_positions.get(epic, 0) + 1
        logger.info(f"[VOLATILITY] {epic}: Position opened (active: {self._active_positions[epic]})")

    def on_position_closed(self, position_info: dict, exit_price: float, profit_loss: float):
        epic = position_info.get("epic", "")
        self._active_positions[epic] = max(0, self._active_positions.get(epic, 0) - 1)
        logger.info(f"[VOLATILITY] {epic}: Position closed at {exit_price}, P/L: {profit_loss:.2f}")
