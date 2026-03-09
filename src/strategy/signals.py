import pandas as pd
import logging

logger = logging.getLogger(__name__)


class SignalEngine:
    """Range-trading signal engine that detects swing highs/lows and trades
    mean-reversion patterns. Buys near support, shorts near resistance.
    Includes Reddit sentiment analysis as additional signal layer.
    Integrates regime detection for signal adjustment."""

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

        # Reddit sentiment
        from src.strategy.reddit_sentiment import RedditSentiment
        self.reddit = RedditSentiment(config)

        # Regime detector and time bias (set externally by main.py / main_ai.py)
        self.regime_detector = None
        self.time_bias = None

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
        window = 10
        df["swing_low"] = df["low"][(df["low"] == df["low"].rolling(window=window * 2 + 1, center=True).min())]
        df["swing_high"] = df["high"][(df["high"] == df["high"].rolling(window=window * 2 + 1, center=True).max())]
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

        # ── MACD ──
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        # ── Volume ──
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        df["volume_spike"] = df["volume"] > (df["volume_ma"] * self.volume_multiplier)
        df["volume_ratio"] = df["volume"] / df["volume_ma"].replace(0, float("nan"))

        # ── Momentum / bounce detection ──
        df["roc_3"] = df["close"].pct_change(3) * 100   # 3 candles = 45 min
        df["roc_6"] = df["close"].pct_change(6) * 100   # 6 candles = 1.5 hours

        # Candle patterns - bullish/bearish engulfing
        df["bullish_candle"] = df["close"] > df["open"]
        df["bearish_candle"] = df["close"] < df["open"]
        df["candle_body"] = (df["close"] - df["open"]).abs()
        df["prev_candle_body"] = df["candle_body"].shift(1)
        df["bullish_engulfing"] = (
            df["bullish_candle"] &
            ~df["bullish_candle"].shift(1).fillna(True) &
            (df["candle_body"] > df["prev_candle_body"])
        )
        df["bearish_engulfing"] = (
            df["bearish_candle"] &
            df["bullish_candle"].shift(1).fillna(False) &
            (df["candle_body"] > df["prev_candle_body"])
        )

        return df

    def _detect_bounce(self, df, direction):
        """Detect if price is bouncing off support (BUY) or resistance (SELL)."""
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) > 2 else prev

        if direction == "BUY":
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

    def _detect_macd_divergence(self, df, direction):
        """Detect MACD divergence - price makes new extreme but MACD doesn't.
        Returns score adjustment (0 or +2)."""
        if len(df) < 20:
            return 0

        recent = df.tail(20)

        if direction == "SELL":
            # Bearish divergence: price makes new high but MACD histogram decreasing
            price_high = recent["high"].iloc[-1] >= recent["high"].iloc[-10:].max() * 0.998
            macd_lower = recent["macd_histogram"].iloc[-1] < recent["macd_histogram"].iloc[-5:].mean()
            if price_high and macd_lower:
                return 2
        else:  # BUY
            # Bullish divergence: price makes new low but MACD histogram increasing
            price_low = recent["low"].iloc[-1] <= recent["low"].iloc[-10:].min() * 1.002
            macd_higher = recent["macd_histogram"].iloc[-1] > recent["macd_histogram"].iloc[-5:].mean()
            if price_low and macd_higher:
                return 2

        return 0

    def _detect_volume_climax(self, df, direction):
        """Detect volume climax: >3x average volume on a directional candle.
        Returns score adjustment (0 or +2)."""
        latest = df.iloc[-1]
        vol_ratio = latest.get("volume_ratio", 0)

        if vol_ratio < 3.0:
            return 0

        if direction == "SELL" and latest["bearish_candle"]:
            return 2
        elif direction == "BUY" and latest["bullish_candle"]:
            return 2

        return 0

    def _detect_failed_breakout(self, df, direction):
        """Detect failed breakout above range_high (sell signal).
        High went above range_high but close is back below.
        Returns score adjustment (0 or +3)."""
        if direction != "SELL":
            return 0

        latest = df.iloc[-1]
        range_high = latest.get("range_high")
        if range_high is None or pd.isna(range_high):
            return 0

        # High exceeded range_high but close is below it
        if latest["high"] > range_high and latest["close"] < range_high:
            return 3

        return 0

    def get_signal(self, df, epic=None):
        """
        Range-trading signal: buy at support, short at resistance.
        Reddit sentiment and regime detection as additional scoring layers.
        Returns: ('BUY'|'SELL'|'HOLD', details_dict)
        """
        if df is None or len(df) < self.range_period + 5:
            return "HOLD", {"reason": "Insufficient data"}

        # Get Reddit sentiment adjustment
        buy_sentiment_adj = 0
        sell_sentiment_adj = 0
        sentiment_data = None
        if epic:
            try:
                buy_sentiment_adj, sell_sentiment_adj, sentiment_data = self.reddit.get_signal_adjustment(epic)
            except Exception as e:
                logger.warning(f"Reddit sentiment failed for {epic}: {e}")

        # Get regime info
        regime = None
        adx = 0.0
        if self.regime_detector and epic:
            try:
                regime, adx = self.regime_detector.get_regime(epic)
            except Exception as e:
                logger.warning(f"Regime detection failed for {epic}: {e}")

        # Get time-of-day bias
        time_bias_label = None
        time_bias_return = 0.0
        if self.time_bias and epic:
            try:
                time_bias_label, time_bias_return, _ = self.time_bias.get_bias(epic)
            except Exception as e:
                logger.warning(f"Time bias failed for {epic}: {e}")

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
            "macd_histogram": latest.get("macd_histogram", 0),
            "sentiment": sentiment_data,
            "regime": regime,
            "adx": adx,
            "time_bias": time_bias_label,
            "time_bias_return": time_bias_return,
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

            # 7. Reddit sentiment
            if buy_sentiment_adj != 0:
                score += buy_sentiment_adj
                label = sentiment_data["label"] if sentiment_data else "?"
                reasons.append(f"Reddit {label} ({buy_sentiment_adj:+d})")

            # 8. MACD bullish divergence
            macd_div = self._detect_macd_divergence(df, "BUY")
            if macd_div > 0:
                score += macd_div
                reasons.append(f"MACD bullish divergence (+{macd_div})")

            # 9. Volume climax on bullish candle
            vol_climax = self._detect_volume_climax(df, "BUY")
            if vol_climax > 0:
                score += vol_climax
                reasons.append(f"Volume climax on green candle (+{vol_climax})")

            # 10. Regime adjustment
            if regime:
                regime_adj = 0
                if self.regime_detector:
                    regime_adj = self.regime_detector.get_signal_adjustment(epic, "BUY")
                if regime_adj != 0:
                    score += regime_adj
                    reasons.append(f"Regime {regime} ({regime_adj:+d})")

            # 11. Time-of-day bias
            if self.time_bias and epic:
                time_adj = self.time_bias.get_signal_adjustment(epic, "BUY")
                if time_adj != 0:
                    score += time_adj
                    reasons.append(f"Time bias {time_bias_label} ({time_adj:+d}, avg {time_bias_return:+.3f}%)")

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
            # Adjust sell zone for memecoins (75% instead of 80%)
            if epic and epic in {"DOGEUSD", "SHIBAUSD", "PEPEUSD", "FLOKIUSD"}:
                memecoin_sell_zone = 75
                if range_pos < memecoin_sell_zone:
                    details["reason"] = f"Memecoin: not in sell zone yet ({range_pos:.0f}% < {memecoin_sell_zone}%)"
                    return "HOLD", details

            # Regime check: only short in RANGING or TRENDING_DOWN
            if regime and regime not in (None, "RANGING", "TRENDING_DOWN"):
                details["reason"] = f"Short blocked: regime is {regime} (need RANGING or TRENDING_DOWN)"
                return "HOLD", details

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

            # 7. Reddit sentiment
            if sell_sentiment_adj != 0:
                score += sell_sentiment_adj
                label = sentiment_data["label"] if sentiment_data else "?"
                reasons.append(f"Reddit {label} ({sell_sentiment_adj:+d})")

            # 8. MACD bearish divergence (+2)
            macd_div = self._detect_macd_divergence(df, "SELL")
            if macd_div > 0:
                score += macd_div
                reasons.append(f"MACD bearish divergence (+{macd_div})")

            # 9. Volume climax on bearish candle (+2)
            vol_climax = self._detect_volume_climax(df, "SELL")
            if vol_climax > 0:
                score += vol_climax
                reasons.append(f"Volume climax on red candle (+{vol_climax})")

            # 10. Failed breakout above range high (+3)
            failed_bo = self._detect_failed_breakout(df, "SELL")
            if failed_bo > 0:
                score += failed_bo
                reasons.append(f"Failed breakout above range high (+{failed_bo})")

            # 11. Regime adjustment
            if regime:
                regime_adj = 0
                if self.regime_detector:
                    regime_adj = self.regime_detector.get_signal_adjustment(epic, "SELL")
                if regime_adj != 0:
                    score += regime_adj
                    reasons.append(f"Regime {regime} ({regime_adj:+d})")

            # 12. Time-of-day bias
            if self.time_bias and epic:
                time_adj = self.time_bias.get_signal_adjustment(epic, "SELL")
                if time_adj != 0:
                    score += time_adj
                    reasons.append(f"Time bias {time_bias_label} ({time_adj:+d}, avg {time_bias_return:+.3f}%)")

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
