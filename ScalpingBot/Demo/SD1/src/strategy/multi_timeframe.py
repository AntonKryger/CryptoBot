"""
Multi-Timeframe Analyzer - Fetches 4H and Daily data to provide higher-timeframe context.
Used by signal engine and AI analyst to avoid counter-trend trades.
"""

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class MultiTimeframeAnalyzer:
    """Analyzes higher timeframes (4H, Daily) for trend context."""

    def __init__(self, client, signal_engine=None):
        self.client = client
        self.signal_engine = signal_engine  # Reuse for indicator calculation

        # Cache with TTL
        self._cache_4h = {}    # {epic: {"data": dict, "timestamp": float}}
        self._cache_daily = {} # {epic: {"data": dict, "timestamp": float}}
        self._cache_ttl_4h = 900    # 15 min for 4H
        self._cache_ttl_daily = 3600  # 1 hour for daily

    def get_higher_tf_context(self, epic):
        """Get higher timeframe context for a coin.

        Returns dict with:
            h4_trend: "UP"|"DOWN"|"NEUTRAL"
            h4_rsi: float
            h4_ema_bullish: bool
            daily_trend: "UP"|"DOWN"|"NEUTRAL"
            daily_rsi: float
            daily_support: float
            daily_resistance: float
            trend_alignment: "ALIGNED_UP"|"ALIGNED_DOWN"|"CONFLICTING"
        """
        h4 = self._get_4h_data(epic)
        daily = self._get_daily_data(epic)

        result = {
            "h4_trend": h4.get("trend", "NEUTRAL"),
            "h4_rsi": h4.get("rsi", 50),
            "h4_ema_bullish": h4.get("ema_bullish", False),
            "h4_roc": h4.get("roc_6", 0),
            "daily_trend": daily.get("trend", "NEUTRAL"),
            "daily_rsi": daily.get("rsi", 50),
            "daily_ema_bullish": daily.get("ema_bullish", False),
            "daily_support": daily.get("support"),
            "daily_resistance": daily.get("resistance"),
        }

        # Determine alignment
        if result["h4_trend"] == "UP" and result["daily_trend"] == "UP":
            result["trend_alignment"] = "ALIGNED_UP"
        elif result["h4_trend"] == "DOWN" and result["daily_trend"] == "DOWN":
            result["trend_alignment"] = "ALIGNED_DOWN"
        elif result["h4_trend"] == "NEUTRAL" and result["daily_trend"] == "NEUTRAL":
            result["trend_alignment"] = "NEUTRAL"
        else:
            result["trend_alignment"] = "CONFLICTING"

        return result

    def _get_4h_data(self, epic):
        """Fetch and analyze 4H candles."""
        cached = self._cache_4h.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._cache_ttl_4h:
            return cached["data"]

        data = self._analyze_timeframe(epic, "HOUR_4", 50)
        if data:
            self._cache_4h[epic] = {"data": data, "timestamp": time.time()}
        return data or {}

    def _get_daily_data(self, epic):
        """Fetch and analyze Daily candles."""
        cached = self._cache_daily.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._cache_ttl_daily:
            return cached["data"]

        data = self._analyze_timeframe(epic, "DAY", 30)
        if data:
            self._cache_daily[epic] = {"data": data, "timestamp": time.time()}
        return data or {}

    def _analyze_timeframe(self, epic, resolution, max_count):
        """Fetch candles and calculate key indicators for a timeframe."""
        try:
            prices = self.client.get_prices(epic, resolution=resolution, max_count=max_count)
            candles = prices.get("prices", [])

            if len(candles) < 20:
                logger.debug(f"MTF {epic} {resolution}: not enough data ({len(candles)} candles)")
                return None

            import pandas as pd

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

            # Calculate indicators
            # EMA 9/21
            df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
            df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
            df["ema_bullish"] = df["ema_9"] > df["ema_21"]

            # RSI
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, float("nan"))
            df["rsi"] = 100 - (100 / (1 + rs))

            # ROC
            df["roc_6"] = df["close"].pct_change(6) * 100

            # Support/Resistance (swing high/low)
            window = 5
            df["swing_low"] = df["low"][(df["low"] == df["low"].rolling(window=window * 2 + 1, center=True).min())]
            df["swing_high"] = df["high"][(df["high"] == df["high"].rolling(window=window * 2 + 1, center=True).max())]
            df["support"] = df["swing_low"].ffill()
            df["resistance"] = df["swing_high"].ffill()

            latest = df.iloc[-1]

            # Determine trend
            ema_bullish = bool(latest["ema_bullish"])
            rsi = float(latest["rsi"]) if not pd.isna(latest["rsi"]) else 50
            roc = float(latest["roc_6"]) if not pd.isna(latest["roc_6"]) else 0

            if ema_bullish and rsi > 45:
                trend = "UP"
            elif not ema_bullish and rsi < 55:
                trend = "DOWN"
            else:
                trend = "NEUTRAL"

            result = {
                "trend": trend,
                "rsi": round(rsi, 1),
                "ema_bullish": ema_bullish,
                "roc_6": round(roc, 2),
                "support": round(float(latest["support"]), 4) if not pd.isna(latest.get("support")) else None,
                "resistance": round(float(latest["resistance"]), 4) if not pd.isna(latest.get("resistance")) else None,
                "close": round(float(latest["close"]), 4),
            }

            logger.debug(f"MTF {epic} {resolution}: trend={trend}, RSI={rsi:.1f}, EMA={'bull' if ema_bullish else 'bear'}")
            return result

        except Exception as e:
            logger.warning(f"MTF analysis failed for {epic} {resolution}: {e}")
            return None

    def get_signal_adjustment(self, epic, signal_direction):
        """Get score adjustment based on higher-timeframe alignment.

        Returns:
            int: -3 to +2 adjustment
        """
        ctx = self.get_higher_tf_context(epic)
        alignment = ctx.get("trend_alignment", "NEUTRAL")

        if signal_direction == "BUY":
            if alignment == "ALIGNED_UP":
                return 2  # Strong support from higher TFs
            elif alignment == "ALIGNED_DOWN":
                return -3  # Trading against both higher TFs
            elif ctx["daily_trend"] == "DOWN":
                return -2  # Against daily trend
            elif ctx["h4_trend"] == "UP":
                return 1   # 4H supports

        elif signal_direction == "SELL":
            if alignment == "ALIGNED_DOWN":
                return 2
            elif alignment == "ALIGNED_UP":
                return -3
            elif ctx["daily_trend"] == "UP":
                return -2
            elif ctx["h4_trend"] == "DOWN":
                return 1

        return 0

    def get_debug_info(self):
        """Return cached data for debug display."""
        result = {}
        for epic in set(list(self._cache_4h.keys()) + list(self._cache_daily.keys())):
            h4 = self._cache_4h.get(epic, {}).get("data", {})
            daily = self._cache_daily.get(epic, {}).get("data", {})
            result[epic] = {
                "h4_trend": h4.get("trend", "?"),
                "h4_rsi": h4.get("rsi", "?"),
                "daily_trend": daily.get("trend", "?"),
                "daily_rsi": daily.get("rsi", "?"),
            }
        return result
