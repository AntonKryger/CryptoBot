"""
Mean Reversion Strategy (KM1) — Oversold/Overbought Extremes

Buys at lower Bollinger Band + RSI oversold, sells at upper BB + RSI overbought.
Targets VWAP/mean for quick exits. Max hold 2 hours.

Active when: ADX < 18 (ranging market) + price at BB extremes
Coins: SOL/USD, AVAX/USD, LINK/USD, LTC/USD (separate from Grid bot!)
Timeframes: 5m + 15m

ChatGPT-tuned (2026-03-14):
- RSI 30/70 (was 25/75, too extreme for crypto)
- BB std 2.2 (was 2.0, better for crypto volatility)
- Trend break filter: volume >2x + ADX rising + close outside BB = NOT mean reversion
"""

import logging
from typing import Optional

import numpy as np

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class MeanReverter(BaseStrategy):
    """Mean reversion at statistical extremes."""

    def __init__(self, config):
        super().__init__(config)

        self.bb_period = self.strategy_cfg.get("bb_period", 20)
        self.bb_std = self.strategy_cfg.get("bb_std", 2.2)  # ChatGPT: 2.2 for crypto volatility
        self.rsi_period = self.strategy_cfg.get("rsi_period", 14)
        self.rsi_oversold = self.strategy_cfg.get("rsi_oversold", 30)   # ChatGPT: 30 (was 25, too extreme)
        self.rsi_overbought = self.strategy_cfg.get("rsi_overbought", 70)  # ChatGPT: 70 (was 75)
        self.vwap_deviation_pct = self.strategy_cfg.get("vwap_deviation_pct", 2.0)
        self.target = self.strategy_cfg.get("target", "vwap")
        self.max_hold_minutes = self.strategy_cfg.get("max_hold_minutes", 120)
        self.adx_threshold = self.strategy_cfg.get("adx_threshold", 18)  # ChatGPT: 18 for crypto
        self.max_entries_per_crash = self.strategy_cfg.get("max_entries_per_crash", 2)

        # Track active entries to prevent overexposure during crashes
        self._active_entries = {}  # {epic: count}

    def get_active_regime(self) -> str:
        return "RANGING"

    def should_be_active(self, regime: str, adx: float) -> bool:
        return adx < self.adx_threshold

    def scan(self, epic: str, prices_data: dict) -> Optional[dict]:
        """Mean reversion scan:
        1. Calculate Bollinger Bands (20, 2σ)
        2. Calculate RSI
        3. Calculate VWAP deviation
        4. Signal when price at BB extreme + RSI extreme + VWAP deviated
        5. Target = VWAP/mean, max hold 2 hours
        """
        df = self.prepare_dataframe(prices_data)
        if df is None or len(df) < self.bb_period + 10:
            return None

        # ADX gate
        adx = self.calculate_adx(df)
        if adx >= self.adx_threshold:
            return None

        # Calculate Bollinger Bands
        df["bb_mid"] = df["close"].rolling(window=self.bb_period).mean()
        df["bb_std"] = df["close"].rolling(window=self.bb_period).std()
        df["bb_upper"] = df["bb_mid"] + (df["bb_std"] * self.bb_std)
        df["bb_lower"] = df["bb_mid"] - (df["bb_std"] * self.bb_std)

        # Calculate RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.inf)
        df["rsi"] = 100 - (100 / (1 + rs))

        # Calculate VWAP (session VWAP using cumulative volume × price)
        df["cum_vol"] = df["volume"].cumsum()
        df["cum_vp"] = (df["close"] * df["volume"]).cumsum()
        df["vwap"] = df["cum_vp"] / df["cum_vol"].replace(0, np.nan)

        latest = df.iloc[-1]
        current_price = latest["close"]
        bb_upper = latest["bb_upper"]
        bb_lower = latest["bb_lower"]
        bb_mid = latest["bb_mid"]
        rsi = latest["rsi"]
        vwap = latest["vwap"]

        if np.isnan(rsi) or np.isnan(bb_upper) or np.isnan(vwap):
            return None

        # VWAP deviation
        vwap_dev_pct = ((current_price - vwap) / vwap * 100) if vwap > 0 else 0

        # Check max entries guard
        active = self._active_entries.get(epic, 0)
        if active >= self.max_entries_per_crash:
            return None

        # Trend break filter (ChatGPT): volume >2x avg + ADX rising + close outside BB
        # = NOT mean reversion, it's a breakout → skip
        vol_avg_20 = df["volume"].rolling(20).mean().iloc[-1]
        volume_explosion = latest["volume"] > vol_avg_20 * 2 if vol_avg_20 > 0 else False
        adx_prev = self.calculate_adx(df.iloc[:-1]) if len(df) > 15 else 0
        adx_rising = adx > adx_prev
        price_outside_bb = current_price > bb_upper or current_price < bb_lower

        if volume_explosion and adx_rising and price_outside_bb:
            logger.info(
                f"[MEANREV] {epic}: Trend break detected (vol {latest['volume']/vol_avg_20:.1f}x, "
                f"ADX rising {adx_prev:.1f}→{adx:.1f}, price outside BB) — skipping"
            )
            return None

        # Detect extremes
        reasons = []
        confidence = 0
        direction = None

        # Oversold (BUY signal)
        if current_price <= bb_lower:
            direction = "BUY"
            confidence += 3
            bb_penetration = (bb_lower - current_price) / bb_lower * 100
            reasons.append(f"Price at lower BB ({bb_penetration:.2f}% below)")

            if rsi <= self.rsi_oversold:
                confidence += 2
                reasons.append(f"RSI oversold ({rsi:.0f})")
            elif rsi <= 35:
                confidence += 1
                reasons.append(f"RSI low ({rsi:.0f})")

            if vwap_dev_pct < -self.vwap_deviation_pct:
                confidence += 2
                reasons.append(f"VWAP deviation {vwap_dev_pct:.1f}%")

        # Overbought (SELL signal)
        elif current_price >= bb_upper:
            direction = "SELL"
            confidence += 3
            bb_penetration = (current_price - bb_upper) / bb_upper * 100
            reasons.append(f"Price at upper BB ({bb_penetration:.2f}% above)")

            if rsi >= self.rsi_overbought:
                confidence += 2
                reasons.append(f"RSI overbought ({rsi:.0f})")
            elif rsi >= 65:
                confidence += 1
                reasons.append(f"RSI high ({rsi:.0f})")

            if vwap_dev_pct > self.vwap_deviation_pct:
                confidence += 2
                reasons.append(f"VWAP deviation +{vwap_dev_pct:.1f}%")

        if direction is None or confidence < 4:
            return None

        # Calculate SL/TP
        atr = self.calculate_atr(df)
        atr_pct = self.calculate_atr_pct(df)

        if direction == "BUY":
            stop_loss = current_price - (atr * 2.0)  # 2x ATR stop
            # Target = VWAP or BB midline
            if self.target == "vwap":
                take_profit = vwap
            else:
                take_profit = bb_mid
            # Ensure min R:R 2:1
            sl_dist = current_price - stop_loss
            tp_dist = take_profit - current_price
            if sl_dist > 0 and tp_dist / sl_dist < 2.0:
                take_profit = current_price + (sl_dist * 2.0)
        else:
            stop_loss = current_price + (atr * 2.0)
            if self.target == "vwap":
                take_profit = vwap
            else:
                take_profit = bb_mid
            sl_dist = stop_loss - current_price
            tp_dist = current_price - take_profit
            if sl_dist > 0 and tp_dist / sl_dist < 2.0:
                take_profit = current_price - (sl_dist * 2.0)

        confidence = min(confidence, 10)

        logger.info(
            f"[MEANREV] {epic}: {direction} signal (conf={confidence}, RSI={rsi:.0f}, "
            f"BB={'lower' if direction == 'BUY' else 'upper'}, VWAP dev={vwap_dev_pct:+.1f}%)"
        )

        return {
            "direction": direction,
            "epic": epic,
            "confidence": confidence,
            "entry_price": current_price,
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "signal_type": f"MEANREV_{direction}",
            "reasons": reasons,
            "details": {
                "rsi": round(rsi, 1),
                "bb_upper": round(bb_upper, 2),
                "bb_lower": round(bb_lower, 2),
                "bb_mid": round(bb_mid, 2),
                "vwap": round(vwap, 2),
                "vwap_deviation_pct": round(vwap_dev_pct, 2),
                "adx": round(adx, 1),
                "atr": round(atr, 2),
                "atr_pct": round(atr_pct, 2),
                "max_hold_minutes": self.max_hold_minutes,
            },
        }

    def on_position_opened(self, position_info: dict):
        epic = position_info.get("epic", "")
        self._active_entries[epic] = self._active_entries.get(epic, 0) + 1
        logger.info(f"[MEANREV] {epic}: Position opened (active entries: {self._active_entries[epic]})")

    def on_position_closed(self, position_info: dict, exit_price: float, profit_loss: float):
        epic = position_info.get("epic", "")
        self._active_entries[epic] = max(0, self._active_entries.get(epic, 0) - 1)
        logger.info(f"[MEANREV] {epic}: Position closed at {exit_price}, P/L: {profit_loss:.2f}")
