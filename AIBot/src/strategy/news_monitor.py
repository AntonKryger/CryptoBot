"""
News Monitor - Breaking news detection and BTC dominance tracking.
F1: CryptoPanic hot news (last 30 min) for score adjustments.
F2: BTC dominance via CoinGecko for altcoin bias.
"""

import logging
import time
import requests

logger = logging.getLogger(__name__)

# Map epics to CryptoPanic currency codes
EPIC_TO_CURRENCY = {
    "BTCUSD": "BTC",
    "ETHUSD": "ETH",
    "SOLUSD": "SOL",
    "AVAXUSD": "AVAX",
    "LINKUSD": "LINK",
    "LTCUSD": "LTC",
    "XRPUSD": "XRP",
    "ADAUSD": "ADA",
    "DOGEUSD": "DOGE",
    "DOTUSD": "DOT",
    "MATICUSD": "MATIC",
}


class NewsMonitor:
    """Monitors breaking news and market-wide data for trading signals."""

    def __init__(self, config):
        cryptopanic_cfg = config.get("cryptopanic", {})
        self.api_key = cryptopanic_cfg.get("api_key", "")
        self.enabled = bool(self.api_key)

        # News cache
        self._news_cache = {}      # {epic: {"news": list, "timestamp": float}}
        self._news_cache_ttl = 300  # 5 min cache

        # BTC dominance cache
        self._dominance_cache = None  # {"dominance": float, "change_24h": float, "timestamp": float}
        self._dominance_cache_ttl = 900  # 15 min cache

        if self.enabled:
            logger.info("NewsMonitor initialized (CryptoPanic + CoinGecko)")
        else:
            logger.info("NewsMonitor: no CryptoPanic API key, news disabled")

    # ── F1: Breaking News ─────────────────────────────────────

    def get_breaking_news(self, epic):
        """Get hot/important news from the last 30 minutes for a coin.

        Returns list of news items: [{"title": str, "kind": str, "votes": dict}]
        """
        if not self.enabled:
            return []

        cached = self._news_cache.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._news_cache_ttl:
            return cached["news"]

        currency = EPIC_TO_CURRENCY.get(epic)
        if not currency:
            return []

        try:
            url = "https://cryptopanic.com/api/developer/v2/posts/"
            params = {
                "auth_token": self.api_key,
                "currencies": currency,
                "filter": "hot",
                "kind": "news",
                "public": "true",
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            news = []
            for post in data.get("results", [])[:5]:
                title = post.get("title", "")
                kind = post.get("kind", "news")
                votes = post.get("votes", {})
                published = post.get("published_at", "")

                # Check if recent (within ~30 min based on ordering)
                news.append({
                    "title": title,
                    "kind": kind,
                    "votes": votes,
                    "published": published,
                    "source": post.get("source", {}).get("title", ""),
                })

            self._news_cache[epic] = {"news": news, "timestamp": time.time()}
            if news:
                logger.info(f"NewsMonitor {epic}: {len(news)} hot news items")
            return news

        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                logger.warning(f"NewsMonitor: CryptoPanic rate limited")
            else:
                logger.warning(f"NewsMonitor: CryptoPanic error for {epic}: {e}")
            return []
        except Exception as e:
            logger.warning(f"NewsMonitor: Failed to fetch news for {epic}: {e}")
            return []

    def get_news_score_adjustment(self, epic):
        """Get score adjustment based on breaking news sentiment.

        Returns: int from -3 to +3
        """
        news = self.get_breaking_news(epic)
        if not news:
            return 0

        total_sentiment = 0
        for item in news:
            votes = item.get("votes", {})
            positive = votes.get("positive", 0)
            negative = votes.get("negative", 0)
            important = votes.get("important", 0)

            # Weight by importance and vote balance
            weight = 1 + (important * 0.5)
            if positive > negative:
                total_sentiment += weight
            elif negative > positive:
                total_sentiment -= weight

        # Clamp to [-3, +3]
        if total_sentiment >= 3:
            return 3
        elif total_sentiment >= 1.5:
            return 2
        elif total_sentiment >= 0.5:
            return 1
        elif total_sentiment <= -3:
            return -3
        elif total_sentiment <= -1.5:
            return -2
        elif total_sentiment <= -0.5:
            return -1
        return 0

    # ── F2: BTC Dominance ─────────────────────────────────────

    def get_btc_dominance(self):
        """Get BTC dominance from CoinGecko.

        Returns: {"dominance": float, "change_trend": "rising"|"falling"|"stable"} or None
        """
        if self._dominance_cache and (time.time() - self._dominance_cache["timestamp"]) < self._dominance_cache_ttl:
            return self._dominance_cache.get("data")

        try:
            resp = requests.get(
                "https://api.coingecko.com/api/v3/global",
                timeout=10,
                headers={"accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})

            btc_dom = data.get("market_cap_percentage", {}).get("btc", 0)
            btc_change = data.get("market_cap_change_percentage_24h_usd", 0)

            # Determine dominance trend
            if btc_change > 1.0:
                trend = "rising"
            elif btc_change < -1.0:
                trend = "falling"
            else:
                trend = "stable"

            result = {
                "dominance": round(btc_dom, 2),
                "market_cap_change_24h": round(btc_change, 2),
                "change_trend": trend,
                "total_market_cap_usd": data.get("total_market_cap", {}).get("usd", 0),
            }

            self._dominance_cache = {"data": result, "timestamp": time.time()}
            logger.debug(f"BTC Dominance: {btc_dom:.1f}% (trend: {trend})")
            return result

        except Exception as e:
            logger.warning(f"NewsMonitor: BTC dominance fetch failed: {e}")
            return None

    def get_altcoin_adjustment(self, epic):
        """Get score adjustment for altcoins based on BTC dominance trend.

        Rising BTC dominance = bearish for altcoins (-1)
        Falling BTC dominance = bullish for altcoins (+1)
        Only applies to non-BTC coins.

        Returns: int (-1, 0, or +1)
        """
        if epic == "BTCUSD":
            return 0

        dom = self.get_btc_dominance()
        if not dom:
            return 0

        trend = dom.get("change_trend", "stable")
        if trend == "rising":
            return -1  # BTC dominance rising = capital flowing to BTC, bearish altcoins
        elif trend == "falling":
            return 1   # BTC dominance falling = capital flowing to alts, bullish altcoins
        return 0

    def get_market_context(self):
        """Get overall market context for AI prompt."""
        dom = self.get_btc_dominance()
        if not dom:
            return ""

        trend_emoji = "📈" if dom["change_trend"] == "rising" else "📉" if dom["change_trend"] == "falling" else "➡️"
        alt_impact = "bearish for altcoins" if dom["change_trend"] == "rising" else "bullish for altcoins" if dom["change_trend"] == "falling" else "neutral"

        return (
            f"MARKET CONTEXT:\n"
            f"- BTC Dominance: {dom['dominance']:.1f}% ({trend_emoji} {dom['change_trend']})\n"
            f"- Market cap change 24h: {dom['market_cap_change_24h']:+.1f}%\n"
            f"- Implication: {alt_impact}\n"
        )
