"""
Market Regime Detector - Classifies market as TRENDING or RANGING using ADX(14).
Cached per epic, updated every 15 minutes.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Regime constants
TRENDING_UP = "TRENDING_UP"
TRENDING_DOWN = "TRENDING_DOWN"
RANGING = "RANGING"
NEUTRAL = "NEUTRAL"


class RegimeDetector:
    """Detects market regime using ADX(14) from 1h candles."""

    def __init__(self, client, config=None):
        self.client = client
        self._cache = {}  # {epic: {"regime": str, "adx": float, "timestamp": float}}
        self._cache_ttl = 900  # 15 minutes

    def get_regime(self, epic):
        """Get cached regime for an epic. Returns (regime, adx) tuple."""
        cached = self._cache.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._cache_ttl:
            return cached["regime"], cached["adx"]

        # Fetch fresh data
        try:
            regime, adx = self._calculate_regime(epic)
            self._cache[epic] = {
                "regime": regime,
                "adx": adx,
                "timestamp": time.time(),
            }
            logger.info(f"Regime {epic}: {regime} (ADX: {adx:.1f})")
            return regime, adx
        except Exception as e:
            logger.warning(f"Regime detection failed for {epic}: {e}")
            # Return cached if available, else NEUTRAL
            if cached:
                return cached["regime"], cached["adx"]
            return NEUTRAL, 0.0

    def _calculate_regime(self, epic):
        """Calculate ADX(14) from 1h candles and classify regime."""
        prices = self.client.get_prices(epic, resolution="HOUR", max_count=50)
        candles = prices.get("prices", [])

        if len(candles) < 30:
            return NEUTRAL, 0.0

        # Extract OHLC
        highs = []
        lows = []
        closes = []
        for c in candles:
            highs.append((c["highPrice"]["bid"] + c["highPrice"]["ask"]) / 2)
            lows.append((c["lowPrice"]["bid"] + c["lowPrice"]["ask"]) / 2)
            closes.append((c["closePrice"]["bid"] + c["closePrice"]["ask"]) / 2)

        # Calculate +DM, -DM, TR
        period = 14
        plus_dm = []
        minus_dm = []
        tr_list = []

        for i in range(1, len(highs)):
            high_diff = highs[i] - highs[i - 1]
            low_diff = lows[i - 1] - lows[i]

            pdm = high_diff if high_diff > low_diff and high_diff > 0 else 0
            mdm = low_diff if low_diff > high_diff and low_diff > 0 else 0

            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )

            plus_dm.append(pdm)
            minus_dm.append(mdm)
            tr_list.append(tr)

        if len(tr_list) < period:
            return NEUTRAL, 0.0

        # Wilder's smoothing for +DM, -DM, TR
        smooth_plus_dm = sum(plus_dm[:period])
        smooth_minus_dm = sum(minus_dm[:period])
        smooth_tr = sum(tr_list[:period])

        dx_values = []

        for i in range(period, len(tr_list)):
            smooth_plus_dm = smooth_plus_dm - (smooth_plus_dm / period) + plus_dm[i]
            smooth_minus_dm = smooth_minus_dm - (smooth_minus_dm / period) + minus_dm[i]
            smooth_tr = smooth_tr - (smooth_tr / period) + tr_list[i]

            if smooth_tr == 0:
                continue

            plus_di = 100 * smooth_plus_dm / smooth_tr
            minus_di = 100 * smooth_minus_dm / smooth_tr

            di_sum = plus_di + minus_di
            if di_sum == 0:
                continue

            dx = 100 * abs(plus_di - minus_di) / di_sum
            dx_values.append((dx, plus_di, minus_di))

        if len(dx_values) < period:
            return NEUTRAL, 0.0

        # ADX = smoothed average of DX
        adx = sum(d[0] for d in dx_values[-period:]) / period
        latest_plus_di = dx_values[-1][1]
        latest_minus_di = dx_values[-1][2]

        # Classify regime
        if adx > 25:
            if latest_plus_di > latest_minus_di:
                return TRENDING_UP, adx
            else:
                return TRENDING_DOWN, adx
        elif adx < 20:
            return RANGING, adx
        else:
            return NEUTRAL, adx

    def get_signal_adjustment(self, epic, signal_direction):
        """Get score adjustment based on regime.
        Returns int adjustment to add to signal score."""
        regime, adx = self.get_regime(epic)

        if regime == RANGING:
            return 1  # mean-reversion bonus
        elif regime == TRENDING_UP:
            if signal_direction == "BUY":
                return 1
            else:
                return -2
        elif regime == TRENDING_DOWN:
            if signal_direction == "SELL":
                return 1
            else:
                return -2
        # NEUTRAL
        return 0

    def should_skip_signal(self, epic):
        """Check if regime is NEUTRAL (no new positions)."""
        regime, _ = self.get_regime(epic)
        return regime == NEUTRAL

    def get_all_regimes(self):
        """Return all cached regimes for debug display."""
        return {
            epic: {"regime": data["regime"], "adx": data["adx"]}
            for epic, data in self._cache.items()
        }
