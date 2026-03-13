"""
Multi-Timeframe Technical Analysis - Alignment scoring across 15m, 1H, 4H.
Hard gate: alignment < 2 = forced HOLD.
"""

import logging

logger = logging.getLogger(__name__)


class MultiTFAnalysis:
    """Calculates indicator alignment across 3 timeframes."""

    # Capital.com resolution strings
    RESOLUTIONS = {
        "15m": "MINUTE_15",
        "1h": "HOUR",
        "4h": "HOUR_4",
    }

    def __init__(self, client, signal_engine):
        self.client = client
        self.signals = signal_engine
        self._cache = {}      # {epic: {"data": dict, "timestamp": float}}
        self._cache_ttl = 300  # 5 min

    def get_alignment(self, epic):
        """Fetch indicators on 15m, 1H, 4H and calculate alignment.

        Returns:
            {
                "alignment_score": 0-3,
                "direction": "BUY"|"SELL"|"MIXED",
                "timeframes": {
                    "15m": {"trend": "BUY"|"SELL", "rsi": float, "ema_bullish": bool, "macd_positive": bool},
                    "1h":  {...},
                    "4h":  {...},
                },
                "details": str,
            }
        """
        import time
        cached = self._cache.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._cache_ttl:
            return cached["data"]

        tf_data = {}

        for label, resolution in self.RESOLUTIONS.items():
            try:
                prices = self.client.get_prices(epic, resolution=resolution)
                df = self.signals.prepare_dataframe(prices)
                if df is None or len(df) < 30:
                    tf_data[label] = self._empty_tf()
                    continue

                df = self.signals.calculate_indicators(df)
                latest = df.iloc[-1]

                ema_fast = latest.get("ema_9", latest["close"])
                ema_slow = latest.get("ema_21", latest["close"])
                ema_bullish = ema_fast > ema_slow
                rsi = latest.get("rsi", 50)
                macd_hist = latest.get("macd_histogram", 0)
                roc_3 = latest.get("roc_3", 0)

                # Determine trend direction for this TF
                bullish_signals = 0
                bearish_signals = 0

                if ema_bullish:
                    bullish_signals += 1
                else:
                    bearish_signals += 1

                if rsi > 50:
                    bullish_signals += 1
                elif rsi < 50:
                    bearish_signals += 1

                if macd_hist > 0:
                    bullish_signals += 1
                elif macd_hist < 0:
                    bearish_signals += 1

                trend = "BUY" if bullish_signals > bearish_signals else "SELL"

                tf_data[label] = {
                    "trend": trend,
                    "rsi": round(rsi, 1),
                    "ema_bullish": ema_bullish,
                    "macd_positive": macd_hist > 0,
                    "macd_histogram": round(macd_hist, 6),
                    "roc_3": round(roc_3, 3),
                    "close": latest["close"],
                }

            except Exception as e:
                logger.warning(f"[MTF] {epic} {label} failed: {e}")
                tf_data[label] = self._empty_tf()

        # Calculate alignment
        directions = [tf_data[tf]["trend"] for tf in ["15m", "1h", "4h"] if tf_data.get(tf, {}).get("trend")]
        buy_count = sum(1 for d in directions if d == "BUY")
        sell_count = sum(1 for d in directions if d == "SELL")

        alignment_score = max(buy_count, sell_count)
        if buy_count > sell_count:
            direction = "BUY"
        elif sell_count > buy_count:
            direction = "SELL"
        else:
            direction = "MIXED"

        # Build details string
        tf_summary = []
        for tf in ["15m", "1h", "4h"]:
            d = tf_data.get(tf, {})
            trend = d.get("trend", "?")
            rsi = d.get("rsi", "?")
            ema = "↑" if d.get("ema_bullish") else "↓"
            macd = "+" if d.get("macd_positive") else "-"
            tf_summary.append(f"{tf}: {trend} (RSI:{rsi}, EMA{ema}, MACD{macd})")

        details = " | ".join(tf_summary)

        result = {
            "alignment_score": alignment_score,
            "direction": direction,
            "timeframes": tf_data,
            "details": details,
        }

        self._cache[epic] = {"data": result, "timestamp": __import__("time").time()}

        logger.info(f"[MTF] {epic}: alignment={alignment_score}/3 {direction} | {details}")
        return result

    @staticmethod
    def _empty_tf():
        return {
            "trend": None,
            "rsi": 50,
            "ema_bullish": None,
            "macd_positive": None,
            "macd_histogram": 0,
            "roc_3": 0,
            "close": 0,
        }

    @staticmethod
    def passes_alignment_gate(alignment_data, min_score=2):
        """Hard gate: returns (passed: bool, reason: str)."""
        score = alignment_data.get("alignment_score", 0)
        if score < min_score:
            return False, f"Alignment {score}/3 < {min_score} (15m/1H/4H disagree)"
        return True, f"Alignment {score}/3 OK"

    @staticmethod
    def format_for_prompt(alignment_data):
        """Format alignment data for AI prompt."""
        score = alignment_data.get("alignment_score", 0)
        direction = alignment_data.get("direction", "MIXED")
        tfs = alignment_data.get("timeframes", {})

        lines = [f"TIMEFRAME ALIGNMENT: {score}/3 ({direction})"]
        for tf_name in ["15m", "1h", "4h"]:
            d = tfs.get(tf_name, {})
            if not d.get("trend"):
                lines.append(f"  {tf_name}: N/A")
                continue
            ema = "bullish" if d.get("ema_bullish") else "bearish"
            macd = "positive" if d.get("macd_positive") else "negative"
            lines.append(
                f"  {tf_name}: {d['trend']} | RSI={d['rsi']:.0f} | EMA={ema} | MACD={macd}"
            )

        if score == 3:
            lines.append("→ FULD ALIGNMENT: Stærkt signal, alle TF enige.")
        elif score == 2:
            lines.append("→ GOD ALIGNMENT: 2/3 TF enige, acceptable entry.")
        elif score == 1:
            lines.append("→ SVAG ALIGNMENT: Kun 1 TF peger den vej. HOLD.")
        else:
            lines.append("→ INGEN ALIGNMENT: TF i konflikt. HOLD.")

        return "\n".join(lines)
