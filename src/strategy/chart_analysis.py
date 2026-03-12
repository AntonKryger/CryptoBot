"""
Advanced Chart Analysis - Fibonacci retracements, S/R zone clustering,
trendline detection, and chart pattern recognition.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ChartAnalysis:
    """Technical chart analysis with Fibonacci, S/R zones, trendlines, and patterns."""

    # D1: Fibonacci Retracement
    @staticmethod
    def calculate_fib_levels(df, lookback=100):
        """Calculate Fibonacci retracement levels from recent swing high/low.

        Returns:
            dict with fib levels and swing direction, or None if insufficient data.
        """
        if df is None or len(df) < 20:
            return None

        recent = df.tail(min(lookback, len(df)))
        high_idx = recent["high"].idxmax()
        low_idx = recent["low"].idxmin()
        swing_high = recent["high"].max()
        swing_low = recent["low"].min()

        if swing_high == swing_low:
            return None

        # Determine swing direction: if high came after low, we're in an upswing
        if high_idx > low_idx:
            direction = "UP"
            diff = swing_high - swing_low
            levels = {
                "0.000": round(swing_high, 4),
                "0.236": round(swing_high - diff * 0.236, 4),
                "0.382": round(swing_high - diff * 0.382, 4),
                "0.500": round(swing_high - diff * 0.500, 4),
                "0.618": round(swing_high - diff * 0.618, 4),
                "0.786": round(swing_high - diff * 0.786, 4),
                "1.000": round(swing_low, 4),
            }
        else:
            direction = "DOWN"
            diff = swing_high - swing_low
            levels = {
                "0.000": round(swing_low, 4),
                "0.236": round(swing_low + diff * 0.236, 4),
                "0.382": round(swing_low + diff * 0.382, 4),
                "0.500": round(swing_low + diff * 0.500, 4),
                "0.618": round(swing_low + diff * 0.618, 4),
                "0.786": round(swing_low + diff * 0.786, 4),
                "1.000": round(swing_high, 4),
            }

        current_price = float(recent["close"].iloc[-1])

        # Find nearest fib level
        nearest_level = None
        nearest_dist = float("inf")
        for name, price in levels.items():
            dist = abs(current_price - price) / current_price * 100
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_level = name

        return {
            "direction": direction,
            "swing_high": round(swing_high, 4),
            "swing_low": round(swing_low, 4),
            "levels": levels,
            "nearest_level": nearest_level,
            "nearest_dist_pct": round(nearest_dist, 2),
        }

    # D2: Support/Resistance Zone Clustering
    @staticmethod
    def find_sr_zones(df, tolerance_pct=0.5):
        """Find support/resistance zones by clustering swing points and round numbers.

        Returns list of zones sorted by strength (touches), each with:
            {"price": float, "type": "support"|"resistance"|"both", "strength": int, "touches": int}
        """
        if df is None or len(df) < 30:
            return []

        current_price = float(df["close"].iloc[-1])
        price_points = []

        # Find swing highs and lows
        window = 5
        for i in range(window, len(df) - window):
            # Swing low
            if df["low"].iloc[i] == df["low"].iloc[i - window:i + window + 1].min():
                price_points.append({"price": float(df["low"].iloc[i]), "type": "support"})
            # Swing high
            if df["high"].iloc[i] == df["high"].iloc[i - window:i + window + 1].max():
                price_points.append({"price": float(df["high"].iloc[i]), "type": "resistance"})

        # Add round number levels
        price_range = float(df["high"].max() - df["low"].min())
        if price_range > 0:
            # Determine round number step based on price magnitude
            if current_price > 10000:
                step = 500
            elif current_price > 1000:
                step = 100
            elif current_price > 100:
                step = 10
            elif current_price > 10:
                step = 5
            else:
                step = 0.5

            low = float(df["low"].min())
            high = float(df["high"].max())
            round_price = (low // step) * step
            while round_price <= high + step:
                price_points.append({"price": round_price, "type": "round"})
                round_price += step

        if not price_points:
            return []

        # Cluster nearby levels
        tolerance = current_price * tolerance_pct / 100
        price_points.sort(key=lambda x: x["price"])

        zones = []
        used = [False] * len(price_points)

        for i, pt in enumerate(price_points):
            if used[i]:
                continue
            cluster = [pt]
            used[i] = True
            for j in range(i + 1, len(price_points)):
                if used[j]:
                    continue
                if abs(price_points[j]["price"] - pt["price"]) <= tolerance:
                    cluster.append(price_points[j])
                    used[j] = True

            # Calculate zone properties
            avg_price = sum(p["price"] for p in cluster) / len(cluster)
            types = set(p["type"] for p in cluster)
            if "support" in types and "resistance" in types:
                zone_type = "both"
            elif "support" in types:
                zone_type = "support"
            elif "resistance" in types:
                zone_type = "resistance"
            else:
                zone_type = "round"

            zones.append({
                "price": round(avg_price, 4),
                "type": zone_type,
                "strength": len(cluster),
                "touches": len([p for p in cluster if p["type"] in ("support", "resistance")]),
                "dist_pct": round(abs(current_price - avg_price) / current_price * 100, 2),
            })

        # Sort by strength (more touches = stronger) and filter to nearby zones
        zones.sort(key=lambda z: z["strength"], reverse=True)
        # Keep only zones within 10% of current price
        zones = [z for z in zones if z["dist_pct"] < 10.0]

        return zones[:10]  # Top 10 zones

    # D3: Trendline Detection
    @staticmethod
    def detect_trendlines(df, min_touches=3):
        """Detect ascending and descending trendlines.

        Returns list of trendlines:
            {"type": "ascending"|"descending", "slope": float, "touches": int,
             "current_price_at_line": float, "dist_pct": float}
        """
        if df is None or len(df) < 30:
            return []

        trendlines = []

        # Find swing lows for ascending trendlines
        window = 5
        swing_lows = []
        swing_highs = []

        for i in range(window, len(df) - window):
            if df["low"].iloc[i] == df["low"].iloc[i - window:i + window + 1].min():
                swing_lows.append((i, float(df["low"].iloc[i])))
            if df["high"].iloc[i] == df["high"].iloc[i - window:i + window + 1].max():
                swing_highs.append((i, float(df["high"].iloc[i])))

        current_price = float(df["close"].iloc[-1])
        n = len(df)

        # Try ascending trendlines (connecting swing lows)
        if len(swing_lows) >= min_touches:
            best = _find_best_trendline(swing_lows, n, current_price, "ascending")
            if best and best["touches"] >= min_touches:
                trendlines.append(best)

        # Try descending trendlines (connecting swing highs)
        if len(swing_highs) >= min_touches:
            best = _find_best_trendline(swing_highs, n, current_price, "descending")
            if best and best["touches"] >= min_touches:
                trendlines.append(best)

        return trendlines

    # D4: Chart Pattern Detection
    @staticmethod
    def detect_patterns(df):
        """Detect chart patterns: double top/bottom, head & shoulders, flag/pennant.

        Returns list of patterns:
            {"pattern": str, "completion_pct": float, "target": float, "direction": "bullish"|"bearish"}
        """
        if df is None or len(df) < 40:
            return []

        patterns = []
        current_price = float(df["close"].iloc[-1])

        # Find swing points
        window = 5
        swings = []
        for i in range(window, len(df) - window):
            if df["low"].iloc[i] == df["low"].iloc[i - window:i + window + 1].min():
                swings.append({"idx": i, "price": float(df["low"].iloc[i]), "type": "low"})
            if df["high"].iloc[i] == df["high"].iloc[i - window:i + window + 1].max():
                swings.append({"idx": i, "price": float(df["high"].iloc[i]), "type": "high"})

        swings.sort(key=lambda s: s["idx"])

        if len(swings) < 4:
            return patterns

        # Double Top: two highs at similar level with a valley between
        highs = [s for s in swings[-8:] if s["type"] == "high"]
        lows = [s for s in swings[-8:] if s["type"] == "low"]

        if len(highs) >= 2:
            h1, h2 = highs[-2], highs[-1]
            tolerance = h1["price"] * 0.01  # 1% tolerance
            if abs(h1["price"] - h2["price"]) < tolerance and h2["idx"] - h1["idx"] >= 5:
                # Find neckline (lowest low between the two highs)
                between_lows = [s for s in lows if h1["idx"] < s["idx"] < h2["idx"]]
                if between_lows:
                    neckline = min(s["price"] for s in between_lows)
                    pattern_height = h1["price"] - neckline
                    target = neckline - pattern_height

                    # Completion: how far price has dropped from second peak
                    if current_price < h2["price"]:
                        completion = min(100, (h2["price"] - current_price) / (h2["price"] - neckline) * 100) if h2["price"] > neckline else 0
                    else:
                        completion = 0

                    if completion > 20:
                        patterns.append({
                            "pattern": "Double Top",
                            "completion_pct": round(completion, 0),
                            "target": round(target, 4),
                            "neckline": round(neckline, 4),
                            "direction": "bearish",
                        })

        # Double Bottom: two lows at similar level with a peak between
        if len(lows) >= 2:
            l1, l2 = lows[-2], lows[-1]
            tolerance = l1["price"] * 0.01
            if abs(l1["price"] - l2["price"]) < tolerance and l2["idx"] - l1["idx"] >= 5:
                between_highs = [s for s in highs if l1["idx"] < s["idx"] < l2["idx"]]
                if between_highs:
                    neckline = max(s["price"] for s in between_highs)
                    pattern_height = neckline - l1["price"]
                    target = neckline + pattern_height

                    if current_price > l2["price"]:
                        completion = min(100, (current_price - l2["price"]) / (neckline - l2["price"]) * 100) if neckline > l2["price"] else 0
                    else:
                        completion = 0

                    if completion > 20:
                        patterns.append({
                            "pattern": "Double Bottom",
                            "completion_pct": round(completion, 0),
                            "target": round(target, 4),
                            "neckline": round(neckline, 4),
                            "direction": "bullish",
                        })

        # Head and Shoulders (bearish)
        if len(highs) >= 3 and len(lows) >= 2:
            h1, h2, h3 = highs[-3], highs[-2], highs[-1]
            tolerance = h2["price"] * 0.015  # 1.5% tolerance

            # Head (h2) should be highest, shoulders (h1, h3) at similar levels
            if (h2["price"] > h1["price"] and h2["price"] > h3["price"] and
                    abs(h1["price"] - h3["price"]) < tolerance):
                # Find neckline
                shoulder_lows = [s for s in lows if h1["idx"] < s["idx"] < h3["idx"]]
                if shoulder_lows:
                    neckline = min(s["price"] for s in shoulder_lows)
                    pattern_height = h2["price"] - neckline
                    target = neckline - pattern_height

                    if current_price < h3["price"]:
                        completion = min(100, (h3["price"] - current_price) / (h3["price"] - neckline) * 100) if h3["price"] > neckline else 0
                    else:
                        completion = 0

                    if completion > 20:
                        patterns.append({
                            "pattern": "Head & Shoulders",
                            "completion_pct": round(completion, 0),
                            "target": round(target, 4),
                            "neckline": round(neckline, 4),
                            "direction": "bearish",
                        })

        # Inverse Head and Shoulders (bullish)
        if len(lows) >= 3 and len(highs) >= 2:
            l1, l2, l3 = lows[-3], lows[-2], lows[-1]
            tolerance = abs(l2["price"]) * 0.015

            if (l2["price"] < l1["price"] and l2["price"] < l3["price"] and
                    abs(l1["price"] - l3["price"]) < tolerance):
                shoulder_highs = [s for s in highs if l1["idx"] < s["idx"] < l3["idx"]]
                if shoulder_highs:
                    neckline = max(s["price"] for s in shoulder_highs)
                    pattern_height = neckline - l2["price"]
                    target = neckline + pattern_height

                    if current_price > l3["price"]:
                        completion = min(100, (current_price - l3["price"]) / (neckline - l3["price"]) * 100) if neckline > l3["price"] else 0
                    else:
                        completion = 0

                    if completion > 20:
                        patterns.append({
                            "pattern": "Inverse H&S",
                            "completion_pct": round(completion, 0),
                            "target": round(target, 4),
                            "neckline": round(neckline, 4),
                            "direction": "bullish",
                        })

        # Flag/Pennant detection (consolidation after strong move)
        if len(df) >= 30:
            # Check for strong move in last 20 candles followed by consolidation in last 10
            move_section = df.iloc[-30:-10]
            consol_section = df.iloc[-10:]

            move_pct = (float(move_section["close"].iloc[-1]) - float(move_section["close"].iloc[0])) / float(move_section["close"].iloc[0]) * 100
            consol_range = (float(consol_section["high"].max()) - float(consol_section["low"].min())) / float(consol_section["close"].mean()) * 100

            # Flag: strong move (>3%) followed by tight consolidation (<2%)
            if abs(move_pct) > 3.0 and consol_range < 2.0:
                if move_pct > 0:
                    # Bull flag: expect continuation upward
                    target = current_price + (current_price * abs(move_pct) / 100)
                    patterns.append({
                        "pattern": "Bull Flag",
                        "completion_pct": round(min(100, consol_range / 2.0 * 100), 0),
                        "target": round(target, 4),
                        "move_pct": round(move_pct, 1),
                        "direction": "bullish",
                    })
                else:
                    # Bear flag
                    target = current_price - (current_price * abs(move_pct) / 100)
                    patterns.append({
                        "pattern": "Bear Flag",
                        "completion_pct": round(min(100, consol_range / 2.0 * 100), 0),
                        "target": round(target, 4),
                        "move_pct": round(move_pct, 1),
                        "direction": "bearish",
                    })

        return patterns

    @staticmethod
    def get_full_analysis(df, lookback=100):
        """Run all chart analyses and return combined result."""
        result = {
            "fib": ChartAnalysis.calculate_fib_levels(df, lookback),
            "sr_zones": ChartAnalysis.find_sr_zones(df),
            "trendlines": ChartAnalysis.detect_trendlines(df),
            "patterns": ChartAnalysis.detect_patterns(df),
        }
        return result

    @staticmethod
    def format_for_prompt(analysis):
        """Format chart analysis for inclusion in AI prompt."""
        if not analysis:
            return ""

        sections = []

        # Fibonacci
        fib = analysis.get("fib")
        if fib:
            levels = fib["levels"]
            sections.append(
                f"FIBONACCI ({fib['direction']} swing):\n"
                f"  0.382={levels['0.382']}, 0.500={levels['0.500']}, 0.618={levels['0.618']}\n"
                f"  Nearest: {fib['nearest_level']} ({fib['nearest_dist_pct']}% away)"
            )

        # S/R Zones (top 5)
        zones = analysis.get("sr_zones", [])
        if zones:
            zone_lines = []
            for z in zones[:5]:
                above_below = "above" if z["price"] > float(z.get("_current", z["price"])) else "below"
                zone_lines.append(
                    f"  {z['price']:.4f} ({z['type']}, strength={z['strength']}, {z['dist_pct']}% away)"
                )
            sections.append("KEY S/R ZONES:\n" + "\n".join(zone_lines))

        # Trendlines
        trendlines = analysis.get("trendlines", [])
        if trendlines:
            tl_lines = []
            for tl in trendlines:
                tl_lines.append(
                    f"  {tl['type'].title()} trendline ({tl['touches']} touches, "
                    f"price at line: {tl['current_price_at_line']:.4f}, {tl['dist_pct']:.1f}% away)"
                )
            sections.append("TRENDLINES:\n" + "\n".join(tl_lines))

        # Patterns
        patterns = analysis.get("patterns", [])
        if patterns:
            pat_lines = []
            for p in patterns:
                pat_lines.append(
                    f"  {p['pattern']} ({p['direction']}, {p['completion_pct']:.0f}% complete, "
                    f"target={p['target']:.4f})"
                )
            sections.append("CHART PATTERNS:\n" + "\n".join(pat_lines))

        return "\n\n".join(sections)


def _find_best_trendline(points, n_candles, current_price, tl_type):
    """Find the best trendline connecting swing points.

    Uses a simple approach: try connecting the first point with each subsequent point,
    then count how many other points are within tolerance of the line.
    """
    if len(points) < 2:
        return None

    best = None
    best_touches = 0
    tolerance_pct = 0.003  # 0.3% tolerance for touching the line

    for i in range(len(points) - 1):
        for j in range(i + 1, len(points)):
            idx1, price1 = points[i]
            idx2, price2 = points[j]

            if idx2 == idx1:
                continue

            # Slope per candle
            slope = (price2 - price1) / (idx2 - idx1)

            # For ascending trendlines, slope should be positive
            if tl_type == "ascending" and slope <= 0:
                continue
            # For descending trendlines, slope should be negative
            if tl_type == "descending" and slope >= 0:
                continue

            # Count touches
            touches = 0
            for k, (idx_k, price_k) in enumerate(points):
                expected_price = price1 + slope * (idx_k - idx1)
                if abs(price_k - expected_price) / price_k < tolerance_pct:
                    touches += 1

            if touches > best_touches:
                best_touches = touches
                # Project line to current candle
                current_line_price = price1 + slope * (n_candles - 1 - idx1)
                dist_pct = abs(current_price - current_line_price) / current_price * 100

                best = {
                    "type": tl_type,
                    "slope": round(slope, 6),
                    "slope_pct": round(slope / current_price * 100, 4),
                    "touches": touches,
                    "current_price_at_line": round(current_line_price, 4),
                    "dist_pct": round(dist_pct, 2),
                }

    return best
