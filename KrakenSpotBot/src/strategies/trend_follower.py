"""
Trend Following Strategy (KT1) — Trending Markets

Pure trend-following: EMA crossover + MACD momentum + volume confirmation.
No mean-reversion, no sentiment, no range calculations.
Uses adaptive trailing stop to let profits run.

Active when: ADX >= 28 (strong trend, ChatGPT-tuned for crypto)
Coins: All 6
Timeframes: 15m entry, 1H+4H confirmation

ChatGPT-tuned (2026-03-14):
- Adaptive trailing: ATR×3 initial → breakeven at 1R → ATR×2 at 2R → ATR×1.5 at 3R
- Partial exit: 50% at 2R, rest trails
"""

import logging
from typing import Optional

import numpy as np

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class TrendFollower(BaseStrategy):
    """Pure trend-following for trending markets."""

    def __init__(self, config):
        super().__init__(config)

        self.ema_fast = self.strategy_cfg.get("ema_fast", 20)
        self.ema_slow = self.strategy_cfg.get("ema_slow", 50)
        self.adx_threshold = self.strategy_cfg.get("adx_threshold", 28)  # ChatGPT: 28 for crypto
        self.volume_multiplier = self.strategy_cfg.get("volume_multiplier", 1.5)
        self.trailing_stop_atr_mult = self.strategy_cfg.get("trailing_stop_atr_mult", 3.0)  # Start wide, tighten later
        self.macd_fast = self.strategy_cfg.get("macd_fast", 12)
        self.macd_slow = self.strategy_cfg.get("macd_slow", 26)
        self.macd_signal = self.strategy_cfg.get("macd_signal", 9)
        self.min_trend_bars = self.strategy_cfg.get("min_trend_bars", 3)

        # Adaptive trailing stop levels (R-multiples → ATR multiplier)
        self.trailing_levels = self.strategy_cfg.get("trailing_levels", {
            "breakeven_r": 1.0,     # Move SL to entry at 1R profit
            "tight_1_r": 2.0,      # Tighten to ATR×2.0 at 2R profit
            "tight_2_r": 3.0,      # Tighten to ATR×1.5 at 3R profit
            "tight_1_atr": 2.0,
            "tight_2_atr": 1.5,
        })

        # Partial exit: close 50% at 2R
        self.partial_exit_r = self.strategy_cfg.get("partial_exit_r", 2.0)
        self.partial_exit_ratio = self.strategy_cfg.get("partial_exit_ratio", 0.5)

        # Track crossover state to detect fresh crosses
        self._last_ema_state = {}   # {epic: "BULL"|"BEAR"|None}

    def get_active_regime(self) -> str:
        return "TRENDING"

    def should_be_active(self, regime: str, adx: float) -> bool:
        return adx >= self.adx_threshold

    def scan(self, epic: str, prices_data: dict) -> Optional[dict]:
        """Trend scan:
        1. Calculate EMA 20/50 crossover
        2. Confirm with MACD histogram direction
        3. Check volume spike > 1.5x average
        4. ADX gate > 25
        5. Set trailing stop, no fixed TP
        """
        df = self.prepare_dataframe(prices_data)
        if df is None or len(df) < self.ema_slow + 10:
            return None

        # Calculate indicators
        df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()

        # MACD
        ema_macd_fast = df["close"].ewm(span=self.macd_fast, adjust=False).mean()
        ema_macd_slow = df["close"].ewm(span=self.macd_slow, adjust=False).mean()
        df["macd_line"] = ema_macd_fast - ema_macd_slow
        df["macd_signal"] = df["macd_line"].ewm(span=self.macd_signal, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]

        # Volume average
        df["vol_avg"] = df["volume"].rolling(window=20).mean()

        # ADX
        adx = self.calculate_adx(df)
        if adx < self.adx_threshold:
            return None

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = latest["close"]
        atr = self.calculate_atr(df)
        atr_pct = self.calculate_atr_pct(df)

        # EMA crossover detection
        ema_bullish = latest["ema_fast"] > latest["ema_slow"]
        prev_ema_bullish = prev["ema_fast"] > prev["ema_slow"]

        # Check for fresh crossover or sustained trend
        current_state = "BULL" if ema_bullish else "BEAR"
        last_state = self._last_ema_state.get(epic)
        fresh_cross = (last_state is not None and current_state != last_state)
        self._last_ema_state[epic] = current_state

        # MACD confirmation
        macd_bullish = latest["macd_hist"] > 0
        macd_rising = latest["macd_hist"] > prev["macd_hist"]

        # Volume spike
        vol_avg = latest["vol_avg"]
        volume_spike = latest["volume"] > vol_avg * self.volume_multiplier if vol_avg > 0 else False

        # Trend strength: count consecutive bars in same direction
        trend_bars = 0
        for i in range(len(df) - 1, max(0, len(df) - 10), -1):
            if ema_bullish and df.iloc[i]["ema_fast"] > df.iloc[i]["ema_slow"]:
                trend_bars += 1
            elif not ema_bullish and df.iloc[i]["ema_fast"] < df.iloc[i]["ema_slow"]:
                trend_bars += 1
            else:
                break

        # Build signal
        reasons = []
        confidence = 0

        # EMA cross (required)
        if ema_bullish:
            direction = "BUY"
            if fresh_cross:
                confidence += 3
                reasons.append(f"Fresh EMA {self.ema_fast}/{self.ema_slow} bullish cross")
            else:
                confidence += 2
                reasons.append(f"EMA {self.ema_fast}/{self.ema_slow} bullish")
        else:
            direction = "SELL"
            if fresh_cross:
                confidence += 3
                reasons.append(f"Fresh EMA {self.ema_fast}/{self.ema_slow} bearish cross")
            else:
                confidence += 2
                reasons.append(f"EMA {self.ema_fast}/{self.ema_slow} bearish")

        # MACD confirmation
        if (direction == "BUY" and macd_bullish) or (direction == "SELL" and not macd_bullish):
            confidence += 2
            reasons.append(f"MACD confirms ({'+' if macd_bullish else '-'})")
            if macd_rising == (direction == "BUY"):
                confidence += 1
                reasons.append("MACD momentum accelerating")

        # Volume spike
        if volume_spike:
            confidence += 1
            vol_ratio = latest["volume"] / vol_avg if vol_avg > 0 else 0
            reasons.append(f"Volume spike {vol_ratio:.1f}x avg")

        # ADX strength bonus
        if adx > 35:
            confidence += 1
            reasons.append(f"Strong trend (ADX {adx:.1f})")

        # Minimum confidence check
        if confidence < 4:
            return None

        # Adaptive trailing stop: start wide at ATR×3, tighten as profit grows
        # Initial SL = ATR × 3.0 (gives room for trend to breathe)
        if direction == "BUY":
            stop_loss = current_price - (atr * self.trailing_stop_atr_mult)
        else:
            stop_loss = current_price + (atr * self.trailing_stop_atr_mult)

        # Initial TP far away — trailing stop is the real exit mechanism
        # Partial exit at 2R (50%), rest trails with adaptive tightening
        if direction == "BUY":
            take_profit = current_price + (atr * self.trailing_stop_atr_mult * 4)
        else:
            take_profit = current_price - (atr * self.trailing_stop_atr_mult * 4)

        confidence = min(confidence, 10)

        logger.info(
            f"[TREND] {epic}: {direction} signal (conf={confidence}, ADX={adx:.1f}, "
            f"EMA {'bull' if ema_bullish else 'bear'}, MACD {'+'if macd_bullish else '-'})"
        )

        return {
            "direction": direction,
            "epic": epic,
            "confidence": confidence,
            "entry_price": current_price,
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "signal_type": f"TREND_{direction}",
            "reasons": reasons,
            "details": {
                "adx": round(adx, 1),
                "ema_fast": round(latest["ema_fast"], 2),
                "ema_slow": round(latest["ema_slow"], 2),
                "macd_hist": round(latest["macd_hist"], 6),
                "volume_ratio": round(latest["volume"] / vol_avg, 1) if vol_avg > 0 else 0,
                "atr": round(atr, 2),
                "atr_pct": round(atr_pct, 2),
                "trend_bars": trend_bars,
                "fresh_cross": fresh_cross,
                "trailing_stop_atr_mult": self.trailing_stop_atr_mult,
                # Adaptive trailing metadata for watchdog
                "adaptive_trailing": True,
                "trailing_levels": self.trailing_levels,
                "partial_exit_r": self.partial_exit_r,
                "partial_exit_ratio": self.partial_exit_ratio,
                "initial_risk": round(abs(current_price - stop_loss), 2),  # 1R in USD
            },
        }

    def on_position_opened(self, position_info: dict):
        epic = position_info.get("epic", "")
        logger.info(f"[TREND] {epic}: Position opened, trailing stop active")

    def on_position_closed(self, position_info: dict, exit_price: float, profit_loss: float):
        epic = position_info.get("epic", "")
        logger.info(f"[TREND] {epic}: Position closed at {exit_price}, P/L: {profit_loss:.2f}")
