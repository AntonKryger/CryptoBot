"""
Range Scalper — Automatic range trading without AI analysis.
Buys bottoms, shorts tops, based on range_position + time_bias.
Designed for high-frequency intraday trading (scalping swings).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Copenhagen")


class RangeScalper:
    """Automatic range-based trading: buy low, sell high, flip positions."""

    def __init__(self, config):
        scalper_cfg = config.get("scalper", {})
        self.enabled = scalper_cfg.get("enabled", False)
        self.short_zone = scalper_cfg.get("short_zone", 78)  # range_pos > X% = SHORT
        self.long_zone = scalper_cfg.get("long_zone", 22)    # range_pos < X% = BUY
        self.dead_zone_low = scalper_cfg.get("dead_zone_low", 40)   # 40-60% = no trade
        self.dead_zone_high = scalper_cfg.get("dead_zone_high", 60)
        self.min_range_pct = scalper_cfg.get("min_range_pct", 1.5)  # min 1.5% range to trade
        self.use_time_bias = scalper_cfg.get("use_time_bias", True)
        self.rsi_overbought = scalper_cfg.get("rsi_overbought", 68)
        self.rsi_oversold = scalper_cfg.get("rsi_oversold", 32)
        self._min_confidence = scalper_cfg.get("min_confidence", 5)

        logger.info(
            f"[RangeScalper] Config: enabled={self.enabled} | "
            f"SHORT zone > {self.short_zone}% | LONG zone < {self.long_zone}% | "
            f"Dead zone {self.dead_zone_low}-{self.dead_zone_high}% | "
            f"Min range {self.min_range_pct}%"
        )

    def evaluate(self, epic, df, time_bias_label=None, time_bias_return=0,
                 current_direction=None):
        """Evaluate whether to open/close/flip a position.

        Args:
            epic: Trading pair
            df: DataFrame with calculated indicators (can be 5m or 15m candles)
            time_bias_label: "BULLISH", "BEARISH", or "NEUTRAL"
            time_bias_return: Average return for this hour
            current_direction: "BUY" or "SELL" if we have an open position, None if flat

        Returns:
            dict with:
                action: "BUY" | "SELL" | "CLOSE" | "HOLD"
                confidence: 1-10
                reason: str
                stop_loss: float (suggested)
                take_profit: float (suggested)
        """
        if not self.enabled or df is None or len(df) < 20:
            return {"action": "HOLD", "confidence": 0, "reason": "Scalper disabled or insufficient data"}

        latest = df.iloc[-1]
        price = latest["close"]
        range_pos = latest.get("range_position", 50)
        range_high = latest.get("range_high", 0)
        range_low = latest.get("range_low", 0)
        range_pct = latest.get("range_pct", 0)
        rsi = latest.get("rsi", 50)
        bb_pct = latest.get("bb_pct", 0.5)
        ema_9 = latest.get("ema_9", price)
        ema_21 = latest.get("ema_21", price)

        # Check minimum range — no point scalping a flat market
        if range_pct < self.min_range_pct:
            return {"action": "HOLD", "confidence": 0,
                    "reason": f"Range too small ({range_pct:.1f}% < {self.min_range_pct}%)"}

        # Build signal
        signal = self._evaluate_signal(
            epic, price, range_pos, range_high, range_low, range_pct,
            rsi, bb_pct, ema_9, ema_21,
            time_bias_label, time_bias_return, current_direction
        )

        return signal

    def _evaluate_signal(self, epic, price, range_pos, range_high, range_low,
                         range_pct, rsi, bb_pct, ema_9, ema_21,
                         time_bias_label, time_bias_return, current_direction):
        """Core signal logic — pure range + momentum."""

        confidence = 0
        reasons = []

        # ── SHORT ZONE: price near top of range ──
        if range_pos >= self.short_zone:
            signal = "SELL"
            confidence += 3
            reasons.append(f"Range top zone ({range_pos:.0f}% >= {self.short_zone}%)")

            # RSI confirms overbought
            if rsi >= self.rsi_overbought:
                confidence += 2
                reasons.append(f"RSI overbought ({rsi:.0f})")
            elif rsi >= 60:
                confidence += 1
                reasons.append(f"RSI elevated ({rsi:.0f})")

            # Bollinger Band confirms top
            if bb_pct >= 0.8:
                confidence += 1
                reasons.append(f"BB top zone ({bb_pct:.2f})")

            # Time bias alignment
            if self.use_time_bias and time_bias_label == "BEARISH":
                confidence += 2
                reasons.append(f"Bearish hour (avg {time_bias_return:+.3f}%)")
            elif self.use_time_bias and time_bias_label == "BULLISH":
                confidence -= 1
                reasons.append(f"Bullish hour conflicts (avg {time_bias_return:+.3f}%)")

            # EMA rejection (price turning down from EMA)
            if ema_9 < ema_21:
                confidence += 1
                reasons.append("EMA bearish cross")

            # SL above range high, TP at range midpoint or lower
            range_size = range_high - range_low
            stop_loss = range_high + (range_size * 0.05)  # 5% above range high
            take_profit = range_low + (range_size * 0.3)  # 30% from bottom

            # If we already have a LONG, this is a flip signal — stronger
            if current_direction == "BUY":
                confidence += 1
                reasons.append("FLIP: Close LONG, open SHORT")

            return {
                "action": signal,
                "confidence": min(10, max(1, confidence)),
                "reason": " | ".join(reasons),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "range_pos": range_pos,
            }

        # ── LONG ZONE: price near bottom of range ──
        elif range_pos <= self.long_zone:
            signal = "BUY"
            confidence += 3
            reasons.append(f"Range bottom zone ({range_pos:.0f}% <= {self.long_zone}%)")

            # RSI confirms oversold
            if rsi <= self.rsi_oversold:
                confidence += 2
                reasons.append(f"RSI oversold ({rsi:.0f})")
            elif rsi <= 40:
                confidence += 1
                reasons.append(f"RSI low ({rsi:.0f})")

            # Bollinger Band confirms bottom
            if bb_pct <= 0.2:
                confidence += 1
                reasons.append(f"BB bottom zone ({bb_pct:.2f})")

            # Time bias alignment
            if self.use_time_bias and time_bias_label == "BULLISH":
                confidence += 2
                reasons.append(f"Bullish hour (avg {time_bias_return:+.3f}%)")
            elif self.use_time_bias and time_bias_label == "BEARISH":
                confidence -= 1
                reasons.append(f"Bearish hour conflicts (avg {time_bias_return:+.3f}%)")

            # EMA support (price bouncing off EMA)
            if ema_9 > ema_21:
                confidence += 1
                reasons.append("EMA bullish cross")

            # SL below range low, TP at range midpoint or higher
            range_size = range_high - range_low
            stop_loss = range_low - (range_size * 0.05)   # 5% below range low
            take_profit = range_high - (range_size * 0.3)  # 30% from top

            # If we already have a SHORT, this is a flip signal — stronger
            if current_direction == "SELL":
                confidence += 1
                reasons.append("FLIP: Close SHORT, open LONG")

            return {
                "action": signal,
                "confidence": min(10, max(1, confidence)),
                "reason": " | ".join(reasons),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "range_pos": range_pos,
            }

        # ── DEAD ZONE: middle of range, no clear edge ──
        elif self.dead_zone_low <= range_pos <= self.dead_zone_high:
            # If we have a position in profit, consider closing
            if current_direction:
                return {
                    "action": "HOLD",
                    "confidence": 0,
                    "reason": f"Dead zone ({range_pos:.0f}%) — hold current {current_direction}",
                }
            return {
                "action": "HOLD",
                "confidence": 0,
                "reason": f"Dead zone ({range_pos:.0f}%) — no edge",
            }

        # ── TRANSITION ZONES: between dead zone and entry zones ──
        else:
            # Mild lean but not strong enough for entry
            if range_pos > self.dead_zone_high:
                lean = "SHORT-leaning"
            else:
                lean = "LONG-leaning"
            return {
                "action": "HOLD",
                "confidence": 0,
                "reason": f"Transition zone ({range_pos:.0f}%) — {lean}, waiting for extreme",
            }
