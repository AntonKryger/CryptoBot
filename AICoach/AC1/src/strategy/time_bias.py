"""
Time-of-Day Bias Detector - Analyzes hourly return patterns over the past 7 days.
Identifies which hours tend to be bullish vs bearish for each coin.
Adaptive: recalculates from real data, not hardcoded patterns.
"""

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# Thresholds for classifying hours
BULLISH_THRESHOLD = 0.05   # avg return > +0.05% = bullish hour
BEARISH_THRESHOLD = -0.05  # avg return < -0.05% = bearish hour


class TimeBias:
    """Detects time-of-day trading bias from historical hourly data."""

    def __init__(self, client):
        self.client = client
        self._cache = {}        # {epic: {"hourly_bias": {...}, "timestamp": float}}
        self._cache_ttl = 3600  # Recalculate every hour

    def get_bias(self, epic):
        """Get bias for current hour. Returns (bias_label, avg_return_pct, hourly_data).

        bias_label: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        avg_return_pct: average return for this hour over past 7 days
        hourly_data: dict of {hour: avg_return_pct} for all 24 hours
        """
        cached = self._cache.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._cache_ttl:
            hourly = cached["hourly_bias"]
        else:
            hourly = self._calculate_hourly_bias(epic)
            if hourly:
                self._cache[epic] = {"hourly_bias": hourly, "timestamp": time.time()}
            else:
                return "NEUTRAL", 0.0, {}

        current_hour = datetime.utcnow().hour
        avg_return = hourly.get(current_hour, 0.0)

        if avg_return > BULLISH_THRESHOLD:
            bias = "BULLISH"
        elif avg_return < BEARISH_THRESHOLD:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return bias, avg_return, hourly

    def get_signal_adjustment(self, epic, signal_direction):
        """Get score adjustment based on time-of-day bias.

        Returns:
            int: -2 to +2 adjustment to signal score
            Strong hours (avg return > 0.10% or < -0.10%) get ±2.
        """
        bias, avg_return, _ = self.get_bias(epic)
        strong = abs(avg_return) > 0.10  # Strong hour = bigger adjustment

        if bias == "BULLISH" and signal_direction == "BUY":
            return 2 if strong else 1
        elif bias == "BULLISH" and signal_direction == "SELL":
            return -2 if strong else -1
        elif bias == "BEARISH" and signal_direction == "SELL":
            return 2 if strong else 1
        elif bias == "BEARISH" and signal_direction == "BUY":
            return -2 if strong else -1

        return 0

    def _calculate_hourly_bias(self, epic):
        """Fetch 7 days of 1h candles and calculate average return per hour."""
        try:
            # 7 days * 24 hours = 168 candles
            prices = self.client.get_prices(epic, resolution="HOUR", max_count=168)
            candles = prices.get("prices", [])

            if len(candles) < 48:  # Need at least 2 days
                logger.warning(f"TimeBias {epic}: Not enough hourly data ({len(candles)} candles)")
                return None

            # Group returns by hour of day (UTC)
            hourly_returns = {}  # {hour: [returns]}

            for c in candles:
                try:
                    timestamp = c["snapshotTime"]
                    # Parse timestamp - Capital.com format: "2026/03/09 12:00:00"
                    if "/" in timestamp:
                        dt = datetime.strptime(timestamp, "%Y/%m/%d %H:%M:%S")
                    else:
                        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    hour = dt.hour

                    open_price = (c["openPrice"]["bid"] + c["openPrice"]["ask"]) / 2
                    close_price = (c["closePrice"]["bid"] + c["closePrice"]["ask"]) / 2

                    if open_price > 0:
                        ret = (close_price - open_price) / open_price * 100
                        if hour not in hourly_returns:
                            hourly_returns[hour] = []
                        hourly_returns[hour].append(ret)
                except (ValueError, KeyError) as e:
                    continue

            # Calculate average return per hour
            hourly_bias = {}
            for hour, returns in hourly_returns.items():
                if len(returns) >= 2:  # Need at least 2 data points
                    hourly_bias[hour] = sum(returns) / len(returns)

            if hourly_bias:
                # Log the pattern
                bullish_hours = [h for h, r in sorted(hourly_bias.items()) if r > BULLISH_THRESHOLD]
                bearish_hours = [h for h, r in sorted(hourly_bias.items()) if r < BEARISH_THRESHOLD]
                logger.info(
                    f"TimeBias {epic}: Bullish hours (UTC): {bullish_hours}, "
                    f"Bearish hours (UTC): {bearish_hours}"
                )

            return hourly_bias

        except Exception as e:
            logger.warning(f"TimeBias calculation failed for {epic}: {e}")
            return None

    def get_all_biases(self):
        """Return all cached biases for debug display."""
        result = {}
        current_hour = datetime.utcnow().hour

        for epic, data in self._cache.items():
            hourly = data["hourly_bias"]
            avg = hourly.get(current_hour, 0.0)
            if avg > BULLISH_THRESHOLD:
                label = "BULLISH"
            elif avg < BEARISH_THRESHOLD:
                label = "BEARISH"
            else:
                label = "NEUTRAL"
            result[epic] = {
                "current_hour_utc": current_hour,
                "bias": label,
                "avg_return": f"{avg:+.3f}%",
            }

        return result

    def get_hourly_summary(self, epic):
        """Get a visual summary of hourly biases for a coin (for Telegram)."""
        cached = self._cache.get(epic)
        if not cached:
            # Force calculation
            hourly = self._calculate_hourly_bias(epic)
            if not hourly:
                return f"{epic}: Ingen data"
            self._cache[epic] = {"hourly_bias": hourly, "timestamp": time.time()}
        else:
            hourly = cached["hourly_bias"]

        current_hour = datetime.utcnow().hour
        lines = []
        for h in range(24):
            ret = hourly.get(h, 0.0)
            if ret > BULLISH_THRESHOLD:
                bar = "🟢"
            elif ret < BEARISH_THRESHOLD:
                bar = "🔴"
            else:
                bar = "⚪"
            marker = " ◀" if h == current_hour else ""
            lines.append(f"  {h:02d}:00 {bar} {ret:+.3f}%{marker}")

        return "\n".join(lines)
