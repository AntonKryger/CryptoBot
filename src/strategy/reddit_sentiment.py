"""
Reddit Sentiment Analysis for CryptoBot.
Uses Reddit OAuth API + CryptoPanic for crypto sentiment.
Scores sentiment as bullish/bearish using keyword analysis.
"""

import requests
import logging
import time
import math
from datetime import datetime

logger = logging.getLogger(__name__)

# Map trading epics to search terms
EPIC_TO_SEARCH = {
    "BTCUSD": {"reddit": ["bitcoin", "btc"], "cryptopanic": "BTC", "coingecko": "bitcoin"},
    "ETHUSD": {"reddit": ["ethereum", "eth"], "cryptopanic": "ETH", "coingecko": "ethereum"},
    "SOLUSD": {"reddit": ["solana", "sol"], "cryptopanic": "SOL", "coingecko": "solana"},
    "XRPUSD": {"reddit": ["xrp", "ripple"], "cryptopanic": "XRP", "coingecko": "ripple"},
    "ADAUSD": {"reddit": ["cardano", "ada"], "cryptopanic": "ADA", "coingecko": "cardano"},
    "DOGEUSD": {"reddit": ["dogecoin", "doge"], "cryptopanic": "DOGE", "coingecko": "dogecoin"},
    "AVAXUSD": {"reddit": ["avalanche", "avax"], "cryptopanic": "AVAX", "coingecko": "avalanche-2"},
    "DOTUSD": {"reddit": ["polkadot", "dot"], "cryptopanic": "DOT", "coingecko": "polkadot"},
    "LINKUSD": {"reddit": ["chainlink", "link"], "cryptopanic": "LINK", "coingecko": "chainlink"},
    "MATICUSD": {"reddit": ["polygon", "matic"], "cryptopanic": "MATIC", "coingecko": "matic-network"},
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

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


class RedditSentiment:
    """Fetches and analyzes sentiment from Reddit OAuth + CryptoPanic."""

    def __init__(self, config):
        reddit_cfg = config.get("reddit", {})
        self.enabled = reddit_cfg.get("enabled", True)
        self.cache_minutes = reddit_cfg.get("cache_minutes", 15)
        self.max_posts = reddit_cfg.get("max_posts", 25)

        # Reddit OAuth credentials
        self.reddit_client_id = reddit_cfg.get("client_id", "")
        self.reddit_client_secret = reddit_cfg.get("client_secret", "")
        self.reddit_username = reddit_cfg.get("username", "")
        self.reddit_password = reddit_cfg.get("password", "")
        self.reddit_enabled = bool(self.reddit_client_id and self.reddit_client_secret)
        self._reddit_token = None
        self._reddit_token_expiry = 0

        # CryptoPanic
        cryptopanic_cfg = config.get("cryptopanic", {})
        self.cryptopanic_key = cryptopanic_cfg.get("api_key", "")
        self.cryptopanic_enabled = bool(self.cryptopanic_key)

        self._cache = {}  # {epic: (timestamp, sentiment_data)}
        self._fng_cache = None  # (timestamp, fng_data)
        self._fng_cache_minutes = 30  # Fear & Greed updates daily, cache 30 min
        self._last_request = 0
        self._request_delay = 1.5  # seconds between requests

        if self.reddit_enabled:
            logger.info("Reddit OAuth configured")
        if self.cryptopanic_enabled:
            logger.info("CryptoPanic API configured")
        if not self.reddit_enabled and not self.cryptopanic_enabled:
            logger.warning("No sentiment sources configured (Reddit/CryptoPanic)")

    def _rate_limit(self):
        """Rate limit requests."""
        now = time.time()
        elapsed = now - self._last_request
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request = time.time()

    # ── Reddit OAuth ──────────────────────────────────────────────

    def _get_reddit_token(self):
        """Get or refresh Reddit OAuth token."""
        now = time.time()
        if self._reddit_token and now < self._reddit_token_expiry:
            return self._reddit_token

        try:
            auth = requests.auth.HTTPBasicAuth(self.reddit_client_id, self.reddit_client_secret)
            data = {
                "grant_type": "password",
                "username": self.reddit_username,
                "password": self.reddit_password,
            }
            headers = {"User-Agent": "CryptoBot/1.0 by AntonKryger"}
            resp = requests.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=auth, data=data, headers=headers, timeout=10,
            )
            resp.raise_for_status()
            token_data = resp.json()
            self._reddit_token = token_data["access_token"]
            self._reddit_token_expiry = now + token_data.get("expires_in", 3600) - 60
            logger.info("Reddit OAuth token obtained")
            return self._reddit_token
        except Exception as e:
            logger.error(f"Reddit OAuth failed: {e}")
            return None

    def _fetch_reddit(self, query, subreddit="cryptocurrency"):
        """Fetch posts from Reddit using OAuth API."""
        token = self._get_reddit_token()
        if not token:
            return []

        self._rate_limit()
        url = f"https://oauth.reddit.com/r/{subreddit}/search"
        params = {
            "q": query,
            "sort": "new",
            "t": "day",
            "limit": self.max_posts,
            "restrict_sr": "on",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "CryptoBot/1.0 by AntonKryger",
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 401:
                self._reddit_token = None  # force refresh
                return []
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            return [p["data"] for p in posts]
        except Exception as e:
            logger.error(f"Reddit fetch failed for '{query}': {e}")
            return []

    # ── CryptoPanic ───────────────────────────────────────────────

    def _fetch_cryptopanic(self, currency):
        """Fetch news from CryptoPanic Developer API v2."""
        self._rate_limit()
        url = "https://cryptopanic.com/api/developer/v2/posts/"
        params = {
            "auth_token": self.cryptopanic_key,
            "currencies": currency,
            "public": "true",
            "kind": "news",
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            logger.info(f"CryptoPanic: {len(results)} posts for {currency}")
            return results
        except Exception as e:
            logger.error(f"CryptoPanic fetch failed for {currency}: {e}")
            return []

    def _fetch_cryptopanic_bullish(self, currency):
        """Fetch bullish-filtered news from CryptoPanic."""
        self._rate_limit()
        url = "https://cryptopanic.com/api/developer/v2/posts/"
        params = {
            "auth_token": self.cryptopanic_key,
            "currencies": currency,
            "public": "true",
            "filter": "bullish",
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return len(resp.json().get("results", []))
        except Exception:
            return 0

    def _fetch_cryptopanic_bearish(self, currency):
        """Fetch bearish-filtered news from CryptoPanic."""
        self._rate_limit()
        url = "https://cryptopanic.com/api/developer/v2/posts/"
        params = {
            "auth_token": self.cryptopanic_key,
            "currencies": currency,
            "public": "true",
            "filter": "bearish",
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return len(resp.json().get("results", []))
        except Exception:
            return 0

    def _score_cryptopanic_post(self, post):
        """Score a CryptoPanic news item."""
        title = post.get("title", "")
        # CryptoPanic provides its own sentiment votes
        votes = post.get("votes", {})
        positive = votes.get("positive", 0)
        negative = votes.get("negative", 0)
        important = votes.get("important", 0)

        # Also do keyword analysis on title
        title_bull, title_bear = self._analyze_text(title)

        # Combine CryptoPanic votes with keyword analysis
        bullish = title_bull + positive + (important * 0.5)
        bearish = title_bear + negative

        return {
            "bullish": bullish,
            "bearish": bearish,
            "title": title[:80],
            "source": post.get("source", {}).get("title", ""),
        }

    # ── CoinGecko (free, coin-specific sentiment) ─────────────────

    def _fetch_coingecko_sentiment(self, coin_id):
        """Fetch sentiment from CoinGecko (free, no API key)."""
        self._rate_limit()
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "true",
            "developer_data": "false",
            "sparkline": "false",
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 429:
                logger.warning("CoinGecko rate limited")
                return None
            resp.raise_for_status()
            data = resp.json()
            up = data.get("sentiment_votes_up_percentage", 50) or 50
            down = data.get("sentiment_votes_down_percentage", 50) or 50
            logger.info(f"CoinGecko {coin_id}: {up:.0f}% bullish / {down:.0f}% bearish")
            return {"up_pct": up, "down_pct": down}
        except Exception as e:
            logger.error(f"CoinGecko fetch failed for {coin_id}: {e}")
            return None

    # ── Fear & Greed Index ────────────────────────────────────────

    def _fetch_fear_greed(self):
        """Fetch Bitcoin Fear & Greed Index (free, no API key needed)."""
        if self._fng_cache:
            cached_time, cached_data = self._fng_cache
            age_minutes = (datetime.now() - cached_time).total_seconds() / 60
            if age_minutes < self._fng_cache_minutes:
                return cached_data

        try:
            resp = requests.get(FEAR_GREED_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            fng = data.get("data", [{}])[0]
            result = {
                "value": int(fng.get("value", 50)),
                "label": fng.get("value_classification", "Neutral"),
            }
            self._fng_cache = (datetime.now(), result)
            logger.info(f"Fear & Greed Index: {result['value']} ({result['label']})")
            return result
        except Exception as e:
            logger.error(f"Fear & Greed fetch failed: {e}")
            return {"value": 50, "label": "Neutral"}

    # ── Shared analysis ───────────────────────────────────────────

    def _analyze_text(self, text):
        """Score text as bullish/bearish. Returns (bullish_count, bearish_count)."""
        text_lower = text.lower()
        bullish = sum(1 for word in BULLISH_WORDS if word in text_lower)
        bearish = sum(1 for word in BEARISH_WORDS if word in text_lower)
        return bullish, bearish

    def _score_reddit_post(self, post):
        """Score a single Reddit post."""
        title = post.get("title", "")
        selftext = post.get("selftext", "")[:500]
        score = post.get("score", 1)
        num_comments = post.get("num_comments", 0)

        title_bull, title_bear = self._analyze_text(title)
        body_bull, body_bear = self._analyze_text(selftext)

        total_bull = title_bull + body_bull
        total_bear = title_bear + body_bear

        popularity = 1 + math.log1p(max(score, 0)) + math.log1p(num_comments) * 0.5

        return {
            "bullish": total_bull * popularity,
            "bearish": total_bear * popularity,
            "title": title[:80],
            "score": score,
            "comments": num_comments,
        }

    # ── Main sentiment API ────────────────────────────────────────

    def get_sentiment(self, epic):
        """Get combined sentiment from all sources.
        Returns dict with score (0-100), label, and details."""
        if not self.enabled:
            return self._neutral_result()

        # Check cache
        if epic in self._cache:
            cached_time, cached_data = self._cache[epic]
            age_minutes = (datetime.now() - cached_time).total_seconds() / 60
            if age_minutes < self.cache_minutes:
                return cached_data

        mapping = EPIC_TO_SEARCH.get(epic, {})
        total_bullish = 0
        total_bearish = 0
        total_posts = 0
        all_titles_bull = []
        all_titles_bear = []

        # ── CoinGecko (coin-specific sentiment, free) ──
        coingecko_id = mapping.get("coingecko")
        coingecko_data = None
        if coingecko_id:
            coingecko_data = self._fetch_coingecko_sentiment(coingecko_id)
            if coingecko_data:
                # Convert percentage to weighted score (weight 4 = significant)
                up = coingecko_data["up_pct"]
                down = coingecko_data["down_pct"]
                total_bullish += (up / 100) * 4
                total_bearish += (down / 100) * 4
                total_posts += 1  # count as data source

        # ── CryptoPanic (if available - may be rate limited) ──
        if self.cryptopanic_enabled:
            currency = mapping.get("cryptopanic", epic.replace("USD", ""))
            cp_posts = self._fetch_cryptopanic(currency)

            if cp_posts:  # Only do extra calls if main call succeeded
                cp_bullish_count = self._fetch_cryptopanic_bullish(currency)
                cp_bearish_count = self._fetch_cryptopanic_bearish(currency)
                total_bullish += cp_bullish_count * 3
                total_bearish += cp_bearish_count * 3

                for post in cp_posts:
                    scored = self._score_cryptopanic_post(post)
                    total_bullish += scored["bullish"]
                    total_bearish += scored["bearish"]
                    if scored["bullish"] > scored["bearish"]:
                        all_titles_bull.append(scored["title"])
                    elif scored["bearish"] > scored["bullish"]:
                        all_titles_bear.append(scored["title"])
                total_posts += len(cp_posts)

        # ── Reddit (secondary) ──
        if self.reddit_enabled:
            search_terms = mapping.get("reddit", [epic.replace("USD", "").lower()])
            query = " OR ".join(search_terms)
            for subreddit in SUBREDDITS:
                posts = self._fetch_reddit(query, subreddit)
                for post in posts:
                    scored = self._score_reddit_post(post)
                    total_bullish += scored["bullish"]
                    total_bearish += scored["bearish"]
                    if scored["bullish"] > scored["bearish"]:
                        all_titles_bull.append(scored["title"])
                    elif scored["bearish"] > scored["bullish"]:
                        all_titles_bear.append(scored["title"])
                total_posts += len(posts)

        # ── Fear & Greed Index (always available, free) ──
        fng = self._fetch_fear_greed()
        fng_value = fng["value"]  # 0=extreme fear, 100=extreme greed

        # Convert Fear & Greed to bullish/bearish weight
        # FNG > 50 = greed = bullish, FNG < 50 = fear = bearish
        if fng_value >= 50:
            fng_bullish = (fng_value - 50) / 50 * 5  # 0-5 weight
            fng_bearish = 0
        else:
            fng_bullish = 0
            fng_bearish = (50 - fng_value) / 50 * 5  # 0-5 weight

        total_bullish += fng_bullish
        total_bearish += fng_bearish

        # Calculate score
        total = total_bullish + total_bearish
        if total == 0:
            sentiment_score = 50
        else:
            sentiment_score = (total_bullish / total) * 100

        result = {
            "score": round(sentiment_score, 1),
            "label": self._score_to_label(sentiment_score),
            "total_posts": total_posts,
            "bullish_weight": round(total_bullish, 1),
            "bearish_weight": round(total_bearish, 1),
            "top_bullish": all_titles_bull[:3],
            "top_bearish": all_titles_bear[:3],
            "fear_greed": fng,
            "sources": [],
        }
        result["sources"].append("Fear&Greed")
        if coingecko_data:
            result["sources"].append("CoinGecko")
            result["coingecko"] = coingecko_data
        if self.cryptopanic_enabled:
            result["sources"].append("CryptoPanic")
        if self.reddit_enabled:
            result["sources"].append("Reddit")

        self._cache[epic] = (datetime.now(), result)
        logger.info(
            f"Sentiment {epic}: {result['label']} ({result['score']}/100, "
            f"{result['total_posts']} posts, sources: {result['sources']})"
        )
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
            "sources": [],
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
        """Get score adjustment for signal engine.
        Returns: (buy_adjustment, sell_adjustment, sentiment_details)"""
        sentiment = self.get_sentiment(epic)
        label = sentiment["label"]

        buy_adj = 0
        sell_adj = 0

        if label == "BULLISH":
            buy_adj = 2
            sell_adj = -1
        elif label == "SLIGHTLY_BULLISH":
            buy_adj = 1
        elif label == "BEARISH":
            sell_adj = 2
            buy_adj = -1
        elif label == "SLIGHTLY_BEARISH":
            sell_adj = 1

        return buy_adj, sell_adj, sentiment
