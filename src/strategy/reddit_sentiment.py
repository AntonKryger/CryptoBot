"""
Reddit Sentiment Analysis for CryptoBot.
Fetches recent posts from crypto subreddits and scores sentiment
as bullish/bearish using keyword analysis.
"""

import requests
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Map trading epics to Reddit search terms
EPIC_TO_SEARCH = {
    "BTCUSD": ["bitcoin", "btc"],
    "ETHUSD": ["ethereum", "eth"],
    "SOLUSD": ["solana", "sol"],
    "XRPUSD": ["xrp", "ripple"],
    "ADAUSD": ["cardano", "ada"],
    "DOGEUSD": ["dogecoin", "doge"],
    "AVAXUSD": ["avalanche", "avax"],
    "DOTUSD": ["polkadot", "dot"],
    "LINKUSD": ["chainlink", "link"],
    "MATICUSD": ["polygon", "matic"],
}

BULLISH_WORDS = [
    "bull", "bullish", "moon", "mooning", "pump", "pumping",
    "buy", "buying", "long", "breakout", "rally", "surge",
    "rocket", "soar", "green", "uptrend", "ath", "all time high",
    "accumulate", "undervalued", "cheap", "discount", "hodl",
    "adoption", "partnership", "upgrade", "launch", "milestone",
    "support", "bounce", "recovery", "reversal",
]

BEARISH_WORDS = [
    "bear", "bearish", "crash", "crashing", "dump", "dumping",
    "sell", "selling", "short", "breakdown", "plunge", "tank",
    "scam", "rug", "rugpull", "overvalued", "bubble", "ponzi",
    "hack", "exploit", "ban", "regulation", "sec", "lawsuit",
    "resistance", "death cross", "capitulation", "fear",
    "red", "downtrend", "collapse", "panic",
]

SUBREDDITS = ["cryptocurrency", "CryptoMarkets"]


class RedditSentiment:
    """Fetches and analyzes Reddit sentiment for crypto coins."""

    def __init__(self, config):
        reddit_cfg = config.get("reddit", {})
        self.enabled = reddit_cfg.get("enabled", True)
        self.cache_minutes = reddit_cfg.get("cache_minutes", 15)
        self.max_posts = reddit_cfg.get("max_posts", 25)
        self._cache = {}  # {epic: (timestamp, sentiment_data)}
        self._last_request = 0  # rate limiting
        self._request_delay = 2  # seconds between Reddit requests

    def _rate_limit(self):
        """Respect Reddit's rate limits."""
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request = time.time()

    def _fetch_reddit(self, query, subreddit="cryptocurrency"):
        """Fetch recent posts from Reddit's public JSON API."""
        self._rate_limit()
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": query,
            "sort": "new",
            "t": "day",  # last 24 hours
            "limit": self.max_posts,
            "restrict_sr": "on",
        }
        headers = {
            "User-Agent": "CryptoBot/1.0 (trading sentiment analysis)",
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 429:
                logger.warning("Reddit rate limit hit, backing off")
                time.sleep(10)
                return []
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            return [p["data"] for p in posts]
        except Exception as e:
            logger.error(f"Reddit fetch failed for '{query}': {e}")
            return []

    def _analyze_text(self, text):
        """Score a text as bullish or bearish.
        Returns (bullish_count, bearish_count)."""
        text_lower = text.lower()
        bullish = sum(1 for word in BULLISH_WORDS if word in text_lower)
        bearish = sum(1 for word in BEARISH_WORDS if word in text_lower)
        return bullish, bearish

    def _score_post(self, post):
        """Score a single Reddit post. Returns weighted sentiment."""
        title = post.get("title", "")
        selftext = post.get("selftext", "")[:500]  # limit text length
        score = post.get("score", 1)
        num_comments = post.get("num_comments", 0)

        # Analyze title and body
        title_bull, title_bear = self._analyze_text(title)
        body_bull, body_bear = self._analyze_text(selftext)

        total_bull = title_bull + body_bull
        total_bear = title_bear + body_bear

        # Weight by post popularity (log scale to avoid outliers)
        import math
        popularity = 1 + math.log1p(max(score, 0)) + math.log1p(num_comments) * 0.5

        return {
            "bullish": total_bull * popularity,
            "bearish": total_bear * popularity,
            "raw_bullish": total_bull,
            "raw_bearish": total_bear,
            "popularity": popularity,
            "title": title[:80],
            "score": score,
            "comments": num_comments,
        }

    def get_sentiment(self, epic):
        """Get sentiment analysis for a coin.
        Returns dict with sentiment score, counts, and top posts.
        Uses cache to avoid hammering Reddit."""
        if not self.enabled:
            return self._neutral_result()

        # Check cache
        if epic in self._cache:
            cached_time, cached_data = self._cache[epic]
            age_minutes = (datetime.now() - cached_time).total_seconds() / 60
            if age_minutes < self.cache_minutes:
                return cached_data

        search_terms = EPIC_TO_SEARCH.get(epic, [epic.replace("USD", "").lower()])
        query = " OR ".join(search_terms)

        all_posts = []
        for subreddit in SUBREDDITS:
            posts = self._fetch_reddit(query, subreddit)
            all_posts.extend(posts)

        if not all_posts:
            result = self._neutral_result()
            result["reason"] = "No Reddit posts found"
            self._cache[epic] = (datetime.now(), result)
            return result

        # Score all posts
        scored = [self._score_post(p) for p in all_posts]

        total_bullish = sum(s["bullish"] for s in scored)
        total_bearish = sum(s["bearish"] for s in scored)
        total = total_bullish + total_bearish

        if total == 0:
            sentiment_score = 50  # neutral
        else:
            sentiment_score = (total_bullish / total) * 100  # 0=very bearish, 100=very bullish

        # Top posts by sentiment strength
        top_bullish = sorted(scored, key=lambda s: s["raw_bullish"], reverse=True)[:3]
        top_bearish = sorted(scored, key=lambda s: s["raw_bearish"], reverse=True)[:3]

        result = {
            "score": round(sentiment_score, 1),  # 0-100
            "label": self._score_to_label(sentiment_score),
            "total_posts": len(all_posts),
            "bullish_weight": round(total_bullish, 1),
            "bearish_weight": round(total_bearish, 1),
            "top_bullish": [p["title"] for p in top_bullish if p["raw_bullish"] > 0],
            "top_bearish": [p["title"] for p in top_bearish if p["raw_bearish"] > 0],
        }

        self._cache[epic] = (datetime.now(), result)
        logger.info(f"Reddit sentiment {epic}: {result['label']} ({result['score']}/100, {result['total_posts']} posts)")
        return result

    def _neutral_result(self):
        return {
            "score": 50,
            "label": "NEUTRAL",
            "total_posts": 0,
            "bullish_weight": 0,
            "bearish_weight": 0,
            "top_bullish": [],
            "top_bearish": [],
        }

    def _score_to_label(self, score):
        if score >= 70:
            return "BULLISH"
        elif score >= 55:
            return "SLIGHTLY_BULLISH"
        elif score <= 30:
            return "BEARISH"
        elif score <= 45:
            return "SLIGHTLY_BEARISH"
        return "NEUTRAL"

    def get_signal_adjustment(self, epic):
        """Get a score adjustment for the signal engine.
        Returns: (buy_adjustment, sell_adjustment, sentiment_details)
        Each adjustment is -1 to +2."""
        sentiment = self.get_sentiment(epic)
        score = sentiment["score"]
        label = sentiment["label"]

        buy_adj = 0
        sell_adj = 0

        if label == "BULLISH":
            buy_adj = 2   # strong boost to buy signals
            sell_adj = -1  # penalize short signals
        elif label == "SLIGHTLY_BULLISH":
            buy_adj = 1
        elif label == "BEARISH":
            sell_adj = 2   # strong boost to short signals
            buy_adj = -1   # penalize buy signals
        elif label == "SLIGHTLY_BEARISH":
            sell_adj = 1

        return buy_adj, sell_adj, sentiment
