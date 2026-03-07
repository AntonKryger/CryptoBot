import pandas as pd
import logging

logger = logging.getLogger(__name__)


class SignalEngine:
    """Range-trading signal engine that detects swing highs/lows and trades
    mean-reversion patterns. Buys near support, shorts near resistance."""

    def __init__(self, config):
        signals_cfg = config.get("signals", {})
        self.ema_fast = signals_cfg.get("ema_fast", 9)
        self.ema_slow = signals_cfg.get("ema_slow", 21)
        self.rsi_period = signals_cfg.get("rsi_period", 14)
        self.rsi_overbought = signals_cfg.get("rsi_overbought", 70)
        self.rsi_oversold = signals_cfg.get("rsi_oversold", 30)
        self.volume_multiplier = signals_cfg.get("volume_multiplier", 1.5)
        self.atr_period = signals_cfg.get("atr_period", 14)
        self.range_period = signals_cfg.get("range_period", 96)  # 96 x 15min = 24 hours
        self.buy_zone_pct = signals_cfg.get("buy_zone_pct", 20)  # bottom 20% of range
        self.sell_zone_pct = signals_cfg.get("sell_zone_pct", 80)  # top 80%+ of range
        self.min_range_pct = signals_cfg.get("min_range_pct", 3.0)  # min range to trade

    def prepare_dataframe(self, prices_data):
        """Convert Capital.com price data to a pandas DataFrame."""
        candles = prices_data.get("prices", [])
        if not candles:
            return None

        rows = []
        for c in candles:
            rows.append({
                "timestamp": c["snapshotTime"],
                "open": (c["openPrice"]["bid"] + c["openPrice"]["ask"]) / 2,
                "high": (c["highPrice"]["bid"] + c["highPrice"]["ask"]) / 2,
                "low": (c["lowPrice"]["bid"] + c["lowPrice"]["ask"]) / 2,
                "close": (c["closePrice"]["bid"] + c["closePrice"]["ask"]) / 2,
                "volume": c.get("lastTradedVolume", 0),
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        return df

    def calculate_indicators(self, df):
        """Add technical indicators focused on range detection and mean reversion."""
        # ── Range detection ──
        df["range_high"] = df["high"].rolling(window=self.range_period).max()
        df["range_low"] = df["low"].rolling(window=self.range_period).min()
        df["range_size"] = df["range_high"] - df["range_low"]
        df["range_pct"] = df["range_size"] / df["range_low"] * 100

        # Where is price in the range? 0% = bottom, 100% = top
        range_size = df["range_high"] - df["range_low"]
        df["range_position"] = ((df["close"] - df["range_low"]) / range_size.replace(0, float("nan"))) * 100

        # ── Support & Resistance levels (pivot-based) ──
        # Find swing lows (support) and swing highs (resistance)
        window = 10
        df["swing_low"] = df["low"][(df["low"] == df["low"].rolling(window=window * 2 + 1, center=True).min())]
        df["swing_high"] = df["high"][(df["high"] == df["high"].rolling(window=window * 2 + 1, center=True).max())]
        # Forward-fill support/resistance for comparison
        df["support"] = df["swing_low"].ffill()
        df["resistance"] = df["swing_high"].ffill()

        # Distance from support/resistance
        df["dist_to_support_pct"] = (df["close"] - df["support"]) / df["close"] * 100
        df["dist_to_resistance_pct"] = (df["resistance"] - df["close"]) / df["close"] * 100

        # ── RSI ──
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        # RSI divergence detection (price makes new low but RSI doesn't)
        df["rsi_prev_low"] = df["rsi"].rolling(window=20).min()

        # ── Bollinger Bands ──
        df["bb_mid"] = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_mid"] + (bb_std * 2)
        df["bb_lower"] = df["bb_mid"] - (bb_std * 2)
        # %B - where price is in Bollinger Bands (0=lower, 1=upper)
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, float("nan"))

        # ── EMAs ──
        df[f"ema_{self.ema_fast}"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df[f"ema_{self.ema_slow}"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()
        df["ema_bullish"] = df[f"ema_{self.ema_fast}"] > df[f"ema_{self.ema_slow}"]

        # ── VWAP ──
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_vol = df["volume"].cumsum()
        cum_tp_vol = (typical_price * df["volume"]).cumsum()
        df["vwap"] = cum_tp_vol / cum_vol.replace(0, float("nan"))

        # ── ATR (volatility) ──
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=self.atr_period).mean()
        df["atr_pct"] = df["atr"] / df["close"] * 100

        # ── Volume ──
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        df["volume_spike"] = df["volume"] > (df["volume_ma"] * self.volume_multiplier)

        # ── Momentum / bounce detection ──
        # Price rate of change over short periods
        df["roc_3"] = df["close"].pct_change(3) * 100   # 3 candles = 45 min
        df["roc_6"] = df["close"].pct_change(6) * 100   # 6 candles = 1.5 hours

        # Candle patterns - bullish/bearish engulfing
        df["bullish_candle"] = df["close"] > df["open"]
        df["bearish_candle"] = df["close"] < df["open"]
        df["candle_body"] = (df["close"] - df["open"]).abs()
        df["prev_candle_body"] = df["candle_body"].shift(1)
        # Bullish engulfing: current green candle body bigger than previous red candle
        df["bullish_engulfing"] = (
            df["bullish_candle"] &
            ~df["bullish_candle"].shift(1).fillna(True) &
            (df["candle_body"] > df["prev_candle_body"])
        )
        # Bearish engulfing
        df["bearish_engulfing"] = (
            df["bearish_candle"] &
            df["bullish_candle"].shift(1).fillna(False) &
            (df["candle_body"] > df["prev_candle_body"])
        )

        return df

    def _detect_bounce(self, df, direction):
        """Detect if price is bouncing off support (BUY) or resistance (SELL).
        Looks for reversal candle patterns and momentum shift."""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) > 2 else prev

        if direction == "BUY":
            # Price was falling, now turning up
            was_falling = prev["roc_3"] < -0.5 or prev2["roc_3"] < -0.5
            now_rising = latest["close"] > prev["close"]
            bullish_candle = latest["bullish_candle"]
            engulfing = latest["bullish_engulfing"]
            rsi_turning = latest["rsi"] > prev["rsi"] and prev["rsi"] < 45

            bounce_score = 0
            if was_falling and now_rising:
                bounce_score += 1
            if bullish_candle:
                bounce_score += 1
            if engulfing:
                bounce_score += 2
            if rsi_turning:
                bounce_score += 1
            return bounce_score

        else:  # SELL
            # Price was rising, now turning down
            was_rising = prev["roc_3"] > 0.5 or prev2["roc_3"] > 0.5
            now_falling = latest["close"] < prev["close"]
            bearish_candle = latest["bearish_candle"]
            engulfing = latest["bearish_engulfing"]
            rsi_turning = latest["rsi"] < prev["rsi"] and prev["rsi"] > 55

            bounce_score = 0
            if was_rising and now_falling:
                bounce_score += 1
            if bearish_candle:
                bounce_score += 1
            if engulfing:
                bounce_score += 2
            if rsi_turning:
                bounce_score += 1
            return bounce_score

    def get_signal(self, df):
        """
        Range-trading signal: buy at support, short at resistance.
        Returns: ('BUY'|'SELL'|'HOLD', details_dict)
        """
        if df is None or len(df) < self.range_period + 5:
            return "HOLD", {"reason": "Insufficient data"}

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]

        details = {
            "close": latest["close"],
            "rsi": latest["rsi"],
            "range_position": latest["range_position"],
            "range_pct": latest["range_pct"],
            "range_high": latest["range_high"],
            "range_low": latest["range_low"],
            "support": latest.get("support"),
            "resistance": latest.get("resistance"),
            "bb_pct": latest["bb_pct"],
            "volume_spike": latest["volume_spike"],
            "atr_pct": latest.get("atr_pct", 0),
            "vwap": latest.get("vwap"),
            "ema_fast": latest[f"ema_{self.ema_fast}"],
            "ema_slow": latest[f"ema_{self.ema_slow}"],
        }

        # ── Check if there's a tradeable range ──
        range_pct = latest["range_pct"]
        if range_pct < self.min_range_pct:
            details["reason"] = f"Range too small ({range_pct:.1f}% < {self.min_range_pct}%)"
            return "HOLD", details

        range_pos = latest["range_position"]  # 0-100
        details["zone"] = (
            "BUY_ZONE" if range_pos <= self.buy_zone_pct else
            "SELL_ZONE" if range_pos >= self.sell_zone_pct else
            "NEUTRAL"
        )

        # ── BUY SIGNAL: Price near bottom of range ──
        if range_pos <= self.buy_zone_pct:
            score = 0
            reasons = []

            # 1. In buy zone (bottom of range)
            score += 1
            reasons.append(f"Buy zone (range pos: {range_pos:.0f}%)")

            # 2. RSI oversold or approaching
            if latest["rsi"] < self.rsi_oversold:
                score += 2
                reasons.append(f"RSI oversold ({latest['rsi']:.0f})")
            elif latest["rsi"] < 40:
                score += 1
                reasons.append(f"RSI low ({latest['rsi']:.0f})")

            # 3. Bollinger Band - price near/below lower band
            if latest["bb_pct"] < 0.1:
                score += 2
                reasons.append("Below lower Bollinger Band")
            elif latest["bb_pct"] < 0.25:
                score += 1
                reasons.append("Near lower Bollinger Band")

            # 4. Bounce detection (reversal candle patterns)
            bounce = self._detect_bounce(df, "BUY")
            if bounce >= 2:
                score += 2
                reasons.append(f"Strong bounce detected (score={bounce})")
            elif bounce >= 1:
                score += 1
                reasons.append(f"Possible bounce (score={bounce})")

            # 5. Near support level
            dist_support = latest.get("dist_to_support_pct", 99)
            if dist_support < 1.0:
                score += 1
                reasons.append(f"Near support ({dist_support:.1f}%)")

            # 6. Volume confirmation on bounce
            if latest["volume_spike"] and latest["bullish_candle"]:
                score += 1
                reasons.append("Volume spike on green candle")

            details["buy_score"] = score
            details["buy_reasons"] = reasons

            # Need minimum score of 4 to trigger
            if score >= 4:
                details["signal_strength"] = score
                details["reasons"] = reasons
                logger.info(f"BUY signal (score={score}, range_pos={range_pos:.0f}%): {reasons}")
                return "BUY", details

        # ── SELL/SHORT SIGNAL: Price near top of range ──
        elif range_pos >= self.sell_zone_pct:
            score = 0
            reasons = []

            # 1. In sell zone (top of range)
            score += 1
            reasons.append(f"Sell zone (range pos: {range_pos:.0f}%)")

            # 2. RSI overbought or approaching
            if latest["rsi"] > self.rsi_overbought:
                score += 2
                reasons.append(f"RSI overbought ({latest['rsi']:.0f})")
            elif latest["rsi"] > 60:
                score += 1
                reasons.append(f"RSI high ({latest['rsi']:.0f})")

            # 3. Bollinger Band - price near/above upper band
            if latest["bb_pct"] > 0.9:
                score += 2
                reasons.append("Above upper Bollinger Band")
            elif latest["bb_pct"] > 0.75:
                score += 1
                reasons.append("Near upper Bollinger Band")

            # 4. Rejection/reversal detection
            bounce = self._detect_bounce(df, "SELL")
            if bounce >= 2:
                score += 2
                reasons.append(f"Strong rejection detected (score={bounce})")
            elif bounce >= 1:
                score += 1
                reasons.append(f"Possible rejection (score={bounce})")

            # 5. Near resistance level
            dist_resistance = latest.get("dist_to_resistance_pct", 99)
            if dist_resistance < 1.0:
                score += 1
                reasons.append(f"Near resistance ({dist_resistance:.1f}%)")

            # 6. Volume confirmation on rejection
            if latest["volume_spike"] and latest["bearish_candle"]:
                score += 1
                reasons.append("Volume spike on red candle")

            details["sell_score"] = score
            details["sell_reasons"] = reasons

            # Need minimum score of 4 to trigger
            if score >= 4:
                details["signal_strength"] = score
                details["reasons"] = reasons
                logger.info(f"SELL signal (score={score}, range_pos={range_pos:.0f}%): {reasons}")
                return "SELL", details

        # ── HOLD: Price in middle of range - no edge ──
        details["reason"] = (
            f"Neutral zone (range pos: {range_pos:.0f}%, "
            f"RSI: {latest['rsi']:.0f}, "
            f"range: {latest['range_low']:.4f}-{latest['range_high']:.4f})"
        )
        logger.info(
            f"HOLD: range_pos={range_pos:.0f}% RSI={latest['rsi']:.0f} "
            f"range={range_pct:.1f}% BB={latest['bb_pct']:.2f}"
        )
        return "HOLD", details
