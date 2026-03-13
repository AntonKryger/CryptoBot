"""
Market data provider for Coach — read-only Capital.com access.
Fetches current prices, candles, and market conditions to give context to trade analysis.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

DEMO_URL = "https://demo-api-capital.backend-capital.com"
LIVE_URL = "https://api-capital.backend-capital.com"

COINS = ["BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD"]


class CoachMarketData:
    """Read-only Capital.com client for coach market analysis."""

    def __init__(self, config):
        capital_cfg = config.get("coach", {}).get("capital", config.get("capital", {}))
        self.email = capital_cfg.get("email", "")
        self.password = capital_cfg.get("password", "")
        self.api_key = capital_cfg.get("api_key", "")
        self.demo = capital_cfg.get("demo", True)
        self.base_url = DEMO_URL if self.demo else LIVE_URL

        self.cst = None
        self.security_token = None
        self._last_request = 0
        self._enabled = bool(self.email and self.password and self.api_key)

        if not self._enabled:
            logger.warning("[Coach] No Capital.com credentials — market data disabled")

    @property
    def enabled(self):
        return self._enabled

    def _start_session(self):
        url = f"{self.base_url}/api/v1/session"
        headers = {
            "X-CAP-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        body = {
            "identifier": self.email,
            "password": self.password,
            "encryptedPassword": False,
        }
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        resp.raise_for_status()
        self.cst = resp.headers.get("CST")
        self.security_token = resp.headers.get("X-SECURITY-TOKEN")
        logger.info("[Coach] Capital.com session started (read-only)")

    def _headers(self):
        return {
            "X-CAP-API-KEY": self.api_key,
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.security_token,
            "Content-Type": "application/json",
        }

    def _request(self, endpoint, params=None):
        if not self._enabled:
            return None

        # Rate limit
        elapsed = time.time() - self._last_request
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)
        self._last_request = time.time()

        if not self.cst:
            self._start_session()

        url = f"{self.base_url}{endpoint}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=10)

        if resp.status_code == 401:
            self._start_session()
            resp = requests.get(url, headers=self._headers(), params=params, timeout=10)

        resp.raise_for_status()
        return resp.json() if resp.content else None

    def get_market_snapshot(self, epic):
        """Get current market snapshot for a coin."""
        try:
            data = self._request(f"/api/v1/markets/{epic}")
            if not data:
                return None
            snap = data.get("snapshot", {})
            return {
                "epic": epic,
                "bid": snap.get("bid"),
                "offer": snap.get("offer"),
                "high": snap.get("high"),
                "low": snap.get("low"),
                "change_pct": snap.get("percentageChange"),
                "status": snap.get("marketStatus"),
            }
        except Exception as e:
            logger.warning(f"[Coach] Market snapshot failed for {epic}: {e}")
            return None

    def get_candles(self, epic, resolution="HOUR", count=100):
        """Get historical candles."""
        try:
            data = self._request(f"/api/v1/prices/{epic}", params={
                "resolution": resolution,
                "max": count,
            })
            if not data or "prices" not in data:
                return []

            candles = []
            for p in data["prices"]:
                candles.append({
                    "time": p.get("snapshotTime", ""),
                    "open": float(p["openPrice"]["mid"]) if "openPrice" in p else 0,
                    "high": float(p["highPrice"]["mid"]) if "highPrice" in p else 0,
                    "low": float(p["lowPrice"]["mid"]) if "lowPrice" in p else 0,
                    "close": float(p["closePrice"]["mid"]) if "closePrice" in p else 0,
                    "volume": int(p.get("lastTradedVolume", 0)),
                })
            return candles
        except Exception as e:
            logger.warning(f"[Coach] Candles failed for {epic}: {e}")
            return []

    def get_all_snapshots(self):
        """Get snapshots for all 6 coins."""
        snapshots = {}
        for epic in COINS:
            snap = self.get_market_snapshot(epic)
            if snap:
                snapshots[epic] = snap
        return snapshots

    def format_market_context(self):
        """Format current market conditions for LLM prompt."""
        snapshots = self.get_all_snapshots()
        if not snapshots:
            return ""

        lines = ["CURRENT MARKET CONDITIONS:"]
        for epic, snap in snapshots.items():
            change = snap.get("change_pct", 0) or 0
            direction = "↑" if change > 0 else "↓" if change < 0 else "→"
            bid = snap.get("bid", 0) or 0
            lines.append(f"  {epic}: {bid:.2f} ({change:+.2f}%) {direction}")

        # Overall market sentiment
        changes = [s.get("change_pct", 0) or 0 for s in snapshots.values()]
        avg_change = sum(changes) / len(changes) if changes else 0
        positive = sum(1 for c in changes if c > 0)
        negative = sum(1 for c in changes if c < 0)

        if avg_change > 1.5:
            lines.append(f"\n  MARKET: STRONG BULLISH ({positive}/{len(changes)} coins up, avg {avg_change:+.2f}%)")
        elif avg_change > 0.3:
            lines.append(f"\n  MARKET: MILD BULLISH ({positive}/{len(changes)} coins up, avg {avg_change:+.2f}%)")
        elif avg_change < -1.5:
            lines.append(f"\n  MARKET: STRONG BEARISH ({negative}/{len(changes)} coins down, avg {avg_change:+.2f}%)")
        elif avg_change < -0.3:
            lines.append(f"\n  MARKET: MILD BEARISH ({negative}/{len(changes)} coins down, avg {avg_change:+.2f}%)")
        else:
            lines.append(f"\n  MARKET: NEUTRAL/FLAT (avg {avg_change:+.2f}%)")

        return "\n".join(lines)

    def get_coin_context(self, epic):
        """Get detailed market context for a specific coin (for per-bot analysis)."""
        try:
            candles_1h = self.get_candles(epic, "HOUR", 48)
            candles_4h = self.get_candles(epic, "HOUR_4", 30)
            snap = self.get_market_snapshot(epic)

            if not candles_1h or not snap:
                return ""

            lines = [f"\nMARKET DATA FOR {epic}:"]
            lines.append(f"  Current: {snap.get('bid', 0):.2f} ({snap.get('change_pct', 0):+.2f}%)")
            lines.append(f"  Day range: {snap.get('low', 0):.2f} - {snap.get('high', 0):.2f}")

            # 1H trend (last 12 candles)
            if len(candles_1h) >= 12:
                recent = candles_1h[-12:]
                green = sum(1 for c in recent if c["close"] > c["open"])
                h_high = max(c["high"] for c in recent)
                h_low = min(c["low"] for c in recent)
                lines.append(f"  12H candles: {green}/12 green, range {h_low:.2f}-{h_high:.2f}")

            # 4H trend
            if len(candles_4h) >= 6:
                recent_4h = candles_4h[-6:]
                green_4h = sum(1 for c in recent_4h if c["close"] > c["open"])
                first_close = recent_4h[0]["close"]
                last_close = recent_4h[-1]["close"]
                change_24h = (last_close - first_close) / first_close * 100 if first_close > 0 else 0
                lines.append(f"  24H trend (4H): {green_4h}/6 green, {change_24h:+.2f}%")

            # Key levels from 4H data
            if len(candles_4h) >= 20:
                highs = sorted([c["high"] for c in candles_4h[-20:]], reverse=True)
                lows = sorted([c["low"] for c in candles_4h[-20:]])
                lines.append(f"  4H resistance zone: {highs[0]:.2f} - {highs[2]:.2f}")
                lines.append(f"  4H support zone: {lows[0]:.2f} - {lows[2]:.2f}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[Coach] Coin context failed for {epic}: {e}")
            return ""
