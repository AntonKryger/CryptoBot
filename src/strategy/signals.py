import pandas as pd
import logging

logger = logging.getLogger(__name__)


class SignalEngine:
    """Trend-following signal engine with mean-reversion in ranging markets.
    Primary: trade WITH the trend (strongest documented edge in crypto).
    Secondary: mean-reversion at extremes only when regime is RANGING.
    Tertiary: trend-following pullback BUY/SELL when price is NOT at extremes.
    Includes Reddit sentiment and regime detection."""

    def __init__(self, config):
        signals_cfg = config.get("signals", {})
        self.ema_fast = signals_cfg.get("ema_fast", 9)
        self.ema_slow = signals_cfg.get("ema_slow", 21)
        self.rsi_period = signals_cfg.get("rsi_period", 14)
        self.rsi_overbought = signals_cfg.get("rsi_overbought", 70)
        self.rsi_oversold = signals_cfg.get("rsi_oversold", 30)
        self.volume_multiplier = signals_cfg.get("volume_multiplier", 1.5)
        self.atr_period = signals_cfg.get("atr_period", 14)
        self.range_period = signals_cfg.get("range_period", 24)  # 24 x 1H = 24 hours
        self.buy_zone_pct = signals_cfg.get("buy_zone_pct", 20)  # bottom 20% of range
        self.sell_zone_pct = signals_cfg.get("sell_zone_pct", 80)  # top 80%+ of range
        self.min_range_pct = signals_cfg.get("min_range_pct", 3.0)  # min range to trade

        # Trend-following pullback zone
        self.trend_pullback_buy_max = signals_cfg.get("trend_pullback_buy_max", 65)
        self.trend_pullback_buy_min = signals_cfg.get("trend_pullback_buy_min", 25)
        self.trend_pullback_sell_max = signals_cfg.get("trend_pullback_sell_max", 75)
        self.trend_pullback_sell_min = signals_cfg.get("trend_pullback_sell_min", 35)

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
        # -- Range detection --
        df["range_high"] = df["high"].rolling(window=self.range_period).max()
        df["range_low"] = df["low"].rolling(window=self.range_period).min()
        df["range_size"] = df["range_high"] - df["range_low"]
        df["range_pct"] = df["range_size"] / df["range_low"] * 100

        # Where is price in the range? 0% = bottom, 100% = top
        range_size = df["range_high"] - df["range_low"]
        df["range_position"] = ((df["close"] - df["range_low"]) / range_size.replace(0, float("nan"))) * 100

        # -- Support & Resistance levels (pivot-based) --
        window = 10
        df["swing_low"] = df["low"][(df["low"] == df["low"].rolling(window=window * 2 + 1, center=True).min())]
        df["swing_high"] = df["high"][(df["high"] == df["high"].rolling(window=window * 2 + 1, center=True).max())]
        df["support"] = df["swing_low"].ffill()
        df["resistance"] = df["swing_high"].ffill()

        # Distance from support/resistance
        df["dist_to_support_pct"] = (df["close"] - df["support"]) / df["close"] * 100
        df["dist_to_resistance_pct"] = (df["resistance"] - df["close"]) / df["close"] * 100

        # -- RSI --
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        # RSI divergence detection (price makes new low but RSI doesn't)
        df["rsi_prev_low"] = df["rsi"].rolling(window=20).min()

        # -- Bollinger Bands --
        df["bb_mid"] = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_mid"] + (bb_std * 2)
        df["bb_lower"] = df["bb_mid"] - (bb_std * 2)
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, float("nan"))

        # -- EMAs --
        df[f"ema_{self.ema_fast}"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df[f"ema_{self.ema_slow}"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()
        df["ema_bullish"] = df[f"ema_{self.ema_fast}"] > df[f"ema_{self.ema_slow}"]

        # -- VWAP --
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_vol = df["volume"].cumsum()
        cum_tp_vol = (typical_price * df["volume"]).cumsum()
        df["vwap"] = cum_tp_vol / cum_vol.replace(0, float("nan"))

        # -- ATR (volatility) --
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(window=self.atr_period).mean()
        df["atr_pct"] = df["atr"] / df["close"] * 100

        # -- MACD --
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        # -- Volume --
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        df["volume_spike"] = df["volume"] > (df["volume_ma"] * self.volume_multiplier)
        df["volume_ratio"] = df["volume"] / df["volume_ma"].replace(0, float("nan"))

        # -- Momentum / bounce detection --
        df["roc_3"] = df["close"].pct_change(3) * 100   # 3 candles
        df["roc_6"] = df["close"].pct_change(6) * 100   # 6 candles

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

    def _get_sentiment_and_regime(self, epic):
        """Fetch sentiment, regime, and time bias data for an epic."""
        buy_sentiment_adj = 0
        sell_sentiment_adj = 0
        sentiment_data = None
        regime = None
        adx = 0.0
        time_bias_label = None
        time_bias_return = 0.0

        if epic:
            try:
                buy_sentiment_adj, sell_sentiment_adj, sentiment_data = self.reddit.get_signal_adjustment(epic)
            except Exception as e:
                logger.warning(f"Reddit sentiment failed for {epic}: {e}")

            if self.regime_detector:
                try:
                    regime, adx = self.regime_detector.get_regime(epic)
                except Exception as e:
                    logger.warning(f"Regime detection failed for {epic}: {e}")

            if self.time_bias:
                try:
                    time_bias_label, time_bias_return, _ = self.time_bias.get_bias(epic)
                except Exception as e:
                    logger.warning(f"Time bias failed for {epic}: {e}")

        return {
            "buy_sentiment_adj": buy_sentiment_adj,
            "sell_sentiment_adj": sell_sentiment_adj,
            "sentiment_data": sentiment_data,
            "regime": regime,
            "adx": adx,
            "time_bias_label": time_bias_label,
            "time_bias_return": time_bias_return,
        }

    def _apply_common_adjustments(self, score, reasons, df, epic, direction, ctx):
        """Apply sentiment, MACD, volume climax, regime, and time bias adjustments."""
        # Sentiment
        adj_key = "buy_sentiment_adj" if direction == "BUY" else "sell_sentiment_adj"
        sentiment_adj = ctx[adj_key]
        if sentiment_adj != 0:
            score += sentiment_adj
            label = ctx["sentiment_data"]["label"] if ctx["sentiment_data"] else "?"
            reasons.append(f"Sentiment {label} ({sentiment_adj:+d})")

        # MACD divergence
        macd_div = self._detect_macd_divergence(df, direction)
        if macd_div > 0:
            score += macd_div
            reasons.append(f"MACD {'bullish' if direction == 'BUY' else 'bearish'} divergence (+{macd_div})")

        # Volume climax
        vol_climax = self._detect_volume_climax(df, direction)
        if vol_climax > 0:
            score += vol_climax
            reasons.append(f"Volume climax ({vol_climax:+d})")

        # Regime adjustment
        if ctx["regime"] and self.regime_detector:
            regime_adj = self.regime_detector.get_signal_adjustment(epic, direction)
            if regime_adj != 0:
                score += regime_adj
                reasons.append(f"Regime {ctx['regime']} ({regime_adj:+d})")

        # Time-of-day bias
        if self.time_bias and epic:
            time_adj = self.time_bias.get_signal_adjustment(epic, direction)
            if time_adj != 0:
                score += time_adj
                reasons.append(f"Time bias {ctx['time_bias_label']} ({time_adj:+d})")

        return score, reasons

    def get_signal(self, df, epic=None):
        """
        Signal engine with three modes:
        1. Mean-reversion BUY at bottom of range (range_pos <= 20%)
        2. Mean-reversion SELL at top of range (range_pos >= 80%, only RANGING/TRENDING_DOWN)
        3. Trend-following BUY on pullback in TRENDING_UP (range_pos 25-65%)
        4. Trend-following SELL on pullback in TRENDING_DOWN (range_pos 35-75%)

        Returns: ('BUY'|'SELL'|'HOLD', details_dict)
        """
        if df is None or len(df) < self.range_period + 5:
            return "HOLD", {"reason": "Insufficient data"}

        # Get external data
        ctx = self._get_sentiment_and_regime(epic)

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
            "sentiment": ctx["sentiment_data"],
            "regime": ctx["regime"],
            "adx": ctx["adx"],
            "time_bias": ctx["time_bias_label"],
            "time_bias_return": ctx["time_bias_return"],
        }

        # -- Check if there's a tradeable range --
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

        # -- Trend alignment (EMA 21) --
        ema_trend_bullish = latest["ema_bullish"]  # ema_fast > ema_slow
        regime = ctx["regime"]

        # ================================================================
        # MODE 1: MEAN-REVERSION BUY - Price near bottom of range
        # ================================================================
        if range_pos <= self.buy_zone_pct:
            signal, result_details = self._evaluate_mean_reversion_buy(
                df, latest, range_pos, ema_trend_bullish, ctx, epic, details
            )
            if signal:
                return signal, result_details

        # ================================================================
        # MODE 2: MEAN-REVERSION SELL - Price near top of range
        # ================================================================
        elif range_pos >= self.sell_zone_pct:
            signal, result_details = self._evaluate_mean_reversion_sell(
                df, latest, range_pos, ema_trend_bullish, ctx, epic, details
            )
            if signal:
                return signal, result_details

        # ================================================================
        # MODE 3: TREND-FOLLOWING BUY - Pullback in uptrend
        # Buy on dips when market is trending up, even if not at range bottom
        # ================================================================
        if (regime == "TRENDING_UP" and ema_trend_bullish
                and self.trend_pullback_buy_min <= range_pos <= self.trend_pullback_buy_max):
            signal, result_details = self._evaluate_trend_buy(
                df, latest, range_pos, ctx, epic, details
            )
            if signal:
                return signal, result_details

        # ================================================================
        # MODE 4: TREND-FOLLOWING SELL - Pullback in downtrend
        # Short on rallies when market is trending down
        # ================================================================
        if (regime == "TRENDING_DOWN" and not ema_trend_bullish
                and self.trend_pullback_sell_min <= range_pos <= self.trend_pullback_sell_max):
            signal, result_details = self._evaluate_trend_sell(
                df, latest, range_pos, ctx, epic, details
            )
            if signal:
                return signal, result_details

        # -- HOLD: No signal triggered --
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

    # ================================================================
    # Mean-reversion BUY (bottom of range)
    # ================================================================
    def _evaluate_mean_reversion_buy(self, df, latest, range_pos, ema_trend_bullish, ctx, epic, details):
        score = 0
        reasons = []

        # 1. In buy zone (bottom of range)
        score += 1
        reasons.append(f"Buy zone (range pos: {range_pos:.0f}%)")

        # TREND FILTER: Trading against trend gets penalized (unless ranging)
        if ema_trend_bullish:
            score += 1
            reasons.append("Trend-aligned (EMA bullish)")
        elif ctx["regime"] != "RANGING":
            score -= 2
            reasons.append("COUNTER-TREND penalty (EMA bearish, -2)")

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

        # Common adjustments (sentiment, MACD, volume climax, regime, time bias)
        score, reasons = self._apply_common_adjustments(score, reasons, df, epic, "BUY", ctx)

        details["buy_score"] = score
        details["buy_reasons"] = reasons

        # Need minimum score of 4 to trigger
        if score >= 4:
            details["signal_strength"] = score
            details["reasons"] = reasons
            logger.info(f"BUY signal (score={score}, range_pos={range_pos:.0f}%): {reasons}")
            return "BUY", details

        return None, details

    # ================================================================
    # Mean-reversion SELL (top of range)
    # ================================================================
    def _evaluate_mean_reversion_sell(self, df, latest, range_pos, ema_trend_bullish, ctx, epic, details):
        # Adjust sell zone for memecoins (75% instead of 80%)
        if epic and epic in {"DOGEUSD", "SHIBAUSD", "PEPEUSD", "FLOKIUSD"}:
            memecoin_sell_zone = 75
            if range_pos < memecoin_sell_zone:
                details["reason"] = f"Memecoin: not in sell zone yet ({range_pos:.0f}% < {memecoin_sell_zone}%)"
                return None, details

        # Regime check: only short in RANGING or TRENDING_DOWN
        regime = ctx["regime"]
        if regime and regime not in (None, "RANGING", "TRENDING_DOWN"):
            details["reason"] = f"Short blocked: regime is {regime} (need RANGING or TRENDING_DOWN)"
            return None, details

        score = 0
        reasons = []

        # 1. In sell zone (top of range)
        score += 1
        reasons.append(f"Sell zone (range pos: {range_pos:.0f}%)")

        # TREND FILTER
        if not ema_trend_bullish:
            score += 1
            reasons.append("Trend-aligned (EMA bearish)")
        elif regime != "RANGING":
            score -= 2
            reasons.append("COUNTER-TREND penalty (EMA bullish, -2)")

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

        # Common adjustments
        score, reasons = self._apply_common_adjustments(score, reasons, df, epic, "SELL", ctx)

        # Failed breakout bonus
        failed_bo = self._detect_failed_breakout(df, "SELL")
        if failed_bo > 0:
            score += failed_bo
            reasons.append(f"Failed breakout above range high (+{failed_bo})")

        details["sell_score"] = score
        details["sell_reasons"] = reasons

        # Need minimum score of 4 to trigger
        if score >= 4:
            details["signal_strength"] = score
            details["reasons"] = reasons
            logger.info(f"SELL signal (score={score}, range_pos={range_pos:.0f}%): {reasons}")
            return "SELL", details

        return None, details

    # ================================================================
    # TREND-FOLLOWING BUY - Pullback in uptrend
    # Buys dips when EMA bullish + TRENDING_UP, range_pos 25-65%
    # ================================================================
    def _evaluate_trend_buy(self, df, latest, range_pos, ctx, epic, details):
        prev = df.iloc[-2]
        score = 0
        reasons = []

        # 1. Trend pullback zone (price pulled back from highs in uptrend)
        score += 1
        reasons.append(f"Trend pullback zone (range pos: {range_pos:.0f}%, regime: TRENDING_UP)")

        # 2. EMA alignment confirmed (already checked, but adds to score)
        score += 1
        reasons.append("EMA 9 > EMA 21 (trend confirmed)")

        # 3. RSI pullback — ideal entry when RSI dips to 40-55 in uptrend
        if 30 <= latest["rsi"] <= 45:
            score += 2
            reasons.append(f"RSI deep pullback ({latest['rsi']:.0f})")
        elif 45 < latest["rsi"] <= 55:
            score += 1
            reasons.append(f"RSI moderate pullback ({latest['rsi']:.0f})")

        # 4. Bollinger Band — price near middle or lower band = pullback
        if latest["bb_pct"] < 0.3:
            score += 2
            reasons.append(f"BB pullback (BB%: {latest['bb_pct']:.2f})")
        elif latest["bb_pct"] < 0.5:
            score += 1
            reasons.append(f"BB near mid ({latest['bb_pct']:.2f})")

        # 5. Bounce detection (bullish candle forming after dip)
        bounce = self._detect_bounce(df, "BUY")
        if bounce >= 2:
            score += 2
            reasons.append(f"Strong bounce on pullback (score={bounce})")
        elif bounce >= 1:
            score += 1
            reasons.append(f"Bounce forming (score={bounce})")

        # 6. MACD histogram positive or turning positive
        macd_hist = latest.get("macd_histogram", 0)
        prev_macd_hist = prev.get("macd_histogram", 0)
        if macd_hist > 0:
            score += 1
            reasons.append("MACD histogram positive")
        elif macd_hist > prev_macd_hist and prev_macd_hist < 0:
            score += 1
            reasons.append("MACD histogram turning up")

        # 7. Volume spike on green candle
        if latest["volume_spike"] and latest["bullish_candle"]:
            score += 1
            reasons.append("Volume spike on green candle")

        # 8. Price above VWAP (confirms buying pressure)
        vwap = latest.get("vwap")
        if vwap and latest["close"] > vwap:
            score += 1
            reasons.append("Price above VWAP")

        # 9. Sentiment and time bias
        sentiment_adj = ctx["buy_sentiment_adj"]
        if sentiment_adj > 0:
            score += sentiment_adj
            label = ctx["sentiment_data"]["label"] if ctx["sentiment_data"] else "?"
            reasons.append(f"Sentiment {label} ({sentiment_adj:+d})")

        if self.time_bias and epic:
            time_adj = self.time_bias.get_signal_adjustment(epic, "BUY")
            if time_adj > 0:
                score += time_adj
                reasons.append(f"Time bias {ctx['time_bias_label']} ({time_adj:+d})")

        # 10. ADX strength bonus (strong trend = higher conviction)
        adx = ctx["adx"]
        if adx >= 35:
            score += 1
            reasons.append(f"Strong trend (ADX: {adx:.0f})")

        details["trend_buy_score"] = score
        details["trend_buy_reasons"] = reasons

        # Need minimum score of 5 (higher bar since we're not at extremes)
        if score >= 5:
            details["signal_strength"] = score
            details["reasons"] = reasons
            details["signal_type"] = "TREND_BUY"
            logger.info(f"TREND BUY signal (score={score}, range_pos={range_pos:.0f}%, ADX={adx:.0f}): {reasons}")
            return "BUY", details

        return None, details

    # ================================================================
    # TREND-FOLLOWING SELL - Rally in downtrend
    # Shorts rallies when EMA bearish + TRENDING_DOWN, range_pos 35-75%
    # ================================================================
    def _evaluate_trend_sell(self, df, latest, range_pos, ctx, epic, details):
        prev = df.iloc[-2]
        score = 0
        reasons = []

        # 1. Trend rally zone (price bounced up in downtrend)
        score += 1
        reasons.append(f"Trend rally zone (range pos: {range_pos:.0f}%, regime: TRENDING_DOWN)")

        # 2. EMA alignment confirmed
        score += 1
        reasons.append("EMA 9 < EMA 21 (downtrend confirmed)")

        # 3. RSI rally — ideal short entry when RSI rises to 55-70 in downtrend
        if 55 <= latest["rsi"] <= 70:
            score += 2
            reasons.append(f"RSI rally into resistance ({latest['rsi']:.0f})")
        elif 45 < latest["rsi"] < 55:
            score += 1
            reasons.append(f"RSI moderate rally ({latest['rsi']:.0f})")

        # 4. Bollinger Band — price near upper or middle band = rally
        if latest["bb_pct"] > 0.7:
            score += 2
            reasons.append(f"BB rally (BB%: {latest['bb_pct']:.2f})")
        elif latest["bb_pct"] > 0.5:
            score += 1
            reasons.append(f"BB near mid ({latest['bb_pct']:.2f})")

        # 5. Rejection detection (bearish candle forming after rally)
        bounce = self._detect_bounce(df, "SELL")
        if bounce >= 2:
            score += 2
            reasons.append(f"Strong rejection on rally (score={bounce})")
        elif bounce >= 1:
            score += 1
            reasons.append(f"Rejection forming (score={bounce})")

        # 6. MACD histogram negative or turning negative
        macd_hist = latest.get("macd_histogram", 0)
        prev_macd_hist = prev.get("macd_histogram", 0)
        if macd_hist < 0:
            score += 1
            reasons.append("MACD histogram negative")
        elif macd_hist < prev_macd_hist and prev_macd_hist > 0:
            score += 1
            reasons.append("MACD histogram turning down")

        # 7. Volume spike on red candle
        if latest["volume_spike"] and latest["bearish_candle"]:
            score += 1
            reasons.append("Volume spike on red candle")

        # 8. Price below VWAP (confirms selling pressure)
        vwap = latest.get("vwap")
        if vwap and latest["close"] < vwap:
            score += 1
            reasons.append("Price below VWAP")

        # 9. Sentiment and time bias
        sentiment_adj = ctx["sell_sentiment_adj"]
        if sentiment_adj > 0:
            score += sentiment_adj
            label = ctx["sentiment_data"]["label"] if ctx["sentiment_data"] else "?"
            reasons.append(f"Sentiment {label} ({sentiment_adj:+d})")

        if self.time_bias and epic:
            time_adj = self.time_bias.get_signal_adjustment(epic, "SELL")
            if time_adj > 0:
                score += time_adj
                reasons.append(f"Time bias {ctx['time_bias_label']} ({time_adj:+d})")

        # 10. ADX strength bonus
        adx = ctx["adx"]
        if adx >= 35:
            score += 1
            reasons.append(f"Strong trend (ADX: {adx:.0f})")

        details["trend_sell_score"] = score
        details["trend_sell_reasons"] = reasons

        # Need minimum score of 5
        if score >= 5:
            details["signal_strength"] = score
            details["reasons"] = reasons
            details["signal_type"] = "TREND_SELL"
            logger.info(f"TREND SELL signal (score={score}, range_pos={range_pos:.0f}%, ADX={adx:.0f}): {reasons}")
            return "SELL", details

        return None, details
