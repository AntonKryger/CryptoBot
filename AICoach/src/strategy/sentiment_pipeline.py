"""
Sentiment Pipeline - Async sentiment aggregation from multiple sources.
Never blocks trade execution. Results cached 15 min in SQLite.

Sources (priority order):
A) CryptoPanic (news, AI-scored)
B) Twitter/X via snscrape (mention volume + sentiment)
C) Reddit (top posts, keyword-scored)
D) Fear & Greed Index (integrated, not replaced)
E) YouTube (low priority, only on unusual activity)
"""

import json
import logging
import sqlite3
import os
import threading
import time
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# Reuse existing epic mapping
EPIC_TO_SEARCH = {
    "BTCUSD": {"ticker": "BTC", "name": "bitcoin", "reddit": ["bitcoin", "btc"]},
    "ETHUSD": {"ticker": "ETH", "name": "ethereum", "reddit": ["ethereum", "eth"]},
    "SOLUSD": {"ticker": "SOL", "name": "solana", "reddit": ["solana", "sol"]},
    "AVAXUSD": {"ticker": "AVAX", "name": "avalanche", "reddit": ["avalanche", "avax"]},
    "LINKUSD": {"ticker": "LINK", "name": "chainlink", "reddit": ["chainlink", "link"]},
    "LTCUSD": {"ticker": "LTC", "name": "litecoin", "reddit": ["litecoin", "ltc"]},
}

BULLISH_WORDS = [
    "bull", "bullish", "moon", "pump", "buy", "long", "breakout", "rally",
    "surge", "rocket", "green", "uptrend", "ath", "accumulate", "undervalued",
    "bounce", "recovery", "reversal", "adoption", "partnership", "upgrade",
]

BEARISH_WORDS = [
    "bear", "bearish", "crash", "dump", "sell", "short", "breakdown", "plunge",
    "scam", "rug", "overvalued", "bubble", "hack", "exploit", "ban", "sec",
    "resistance", "death cross", "capitulation", "fear", "red", "collapse",
]

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


class SentimentPipeline:
    """Async sentiment aggregator with SQLite caching."""

    def __init__(self, config):
        self.db_path = config.get("database", {}).get("path", "data_ai/trades.db")
        self._cache_ttl = 900  # 15 min

        # CryptoPanic
        cp_cfg = config.get("cryptopanic", {})
        self.cryptopanic_key = cp_cfg.get("api_key", "")
        self.cryptopanic_enabled = bool(self.cryptopanic_key)

        # Reddit
        reddit_cfg = config.get("reddit", {})
        self.reddit_client_id = reddit_cfg.get("client_id", "")
        self.reddit_client_secret = reddit_cfg.get("client_secret", "")
        self.reddit_username = reddit_cfg.get("username", "")
        self.reddit_password = reddit_cfg.get("password", "")
        self.reddit_enabled = bool(self.reddit_client_id)
        self._reddit_token = None
        self._reddit_token_expiry = 0

        # YouTube Data API
        self.youtube_key = config.get("youtube", {}).get("api_key", "")
        self.youtube_enabled = bool(self.youtube_key)

        # In-memory cache (faster than SQLite for hot path)
        self._mem_cache = {}  # {epic: {"data": dict, "timestamp": float}}

        # Background update state
        self._updating = set()

        self._init_cache_table()
        logger.info(
            f"SentimentPipeline: CryptoPanic={'ON' if self.cryptopanic_enabled else 'OFF'}, "
            f"Reddit={'ON' if self.reddit_enabled else 'OFF'}, "
            f"YouTube={'ON' if self.youtube_enabled else 'OFF'}"
        )

    def _init_cache_table(self):
        """Create SQLite cache table for sentiment data."""
        try:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_cache (
                    epic TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[Sentiment] Cache table init error: {e}")

    # ── Public API ────────────────────────────────────────────

    def get_sentiment(self, epic):
        """Get cached sentiment. Triggers background refresh if stale.
        NEVER blocks the caller."""
        # Check memory cache
        cached = self._mem_cache.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._cache_ttl:
            return cached["data"]

        # Check SQLite cache
        db_data = self._load_from_db(epic)
        if db_data:
            self._mem_cache[epic] = {"data": db_data, "timestamp": time.time()}
            return db_data

        # Trigger background update if not already running
        self._trigger_update(epic)

        # Return neutral while loading
        return self._neutral()

    def get_composite_score(self, epic):
        """Get 0-100 composite score with breakdown per source.
        Returns: {"score": int, "label": str, "breakdown": dict, "flags": list}
        """
        data = self.get_sentiment(epic)
        return {
            "score": data.get("composite_score", 50),
            "label": data.get("label", "NEUTRAL"),
            "breakdown": data.get("breakdown", {}),
            "flags": data.get("flags", []),
        }

    def refresh_all(self, epics):
        """Trigger background refresh for all epics."""
        for epic in epics:
            self._trigger_update(epic)

    # ── Background Update ─────────────────────────────────────

    def _trigger_update(self, epic):
        """Start background sentiment fetch if not already running."""
        if epic in self._updating:
            return
        self._updating.add(epic)
        thread = threading.Thread(target=self._update_async, args=(epic,), daemon=True)
        thread.start()

    def _update_async(self, epic):
        """Fetch all sentiment sources and aggregate."""
        try:
            mapping = EPIC_TO_SEARCH.get(epic, {"ticker": epic[:3], "name": epic[:3].lower(), "reddit": [epic[:3].lower()]})

            scores = {}  # source -> {"score": 0-100, "weight": float, "details": str}
            flags = []

            # A) CryptoPanic
            if self.cryptopanic_enabled:
                cp = self._fetch_cryptopanic_sentiment(mapping["ticker"])
                if cp:
                    scores["cryptopanic"] = cp

            # B) Twitter/X (via public search — snscrape may not work in Docker)
            tw = self._fetch_twitter_sentiment(mapping["ticker"], mapping["name"])
            if tw:
                scores["twitter"] = tw

            # C) Reddit
            if self.reddit_enabled:
                rd = self._fetch_reddit_sentiment(mapping["reddit"])
                if rd:
                    scores["reddit"] = rd

            # D) Fear & Greed
            fng = self._fetch_fear_greed()
            if fng:
                scores["fear_greed"] = fng

            # E) YouTube (low priority)
            if self.youtube_enabled:
                yt = self._fetch_youtube_sentiment(mapping["name"])
                if yt:
                    scores["youtube"] = yt

            # Aggregate
            composite, breakdown = self._aggregate(scores)

            # Flags
            fng_val = scores.get("fear_greed", {}).get("raw_value", 50)
            cp_score = scores.get("cryptopanic", {}).get("score", 50)
            if fng_val < 20 and cp_score > 60:
                flags.append("CONTRARIAN_BOTTOM: Ekstrem frygt + bullish nyheder = potentielt bund-signal")

            if scores.get("twitter", {}).get("spike", False):
                flags.append(f"MENTION_SPIKE: Unormal Twitter-aktivitet på {mapping['ticker']}")

            result = {
                "composite_score": composite,
                "label": self._score_to_label(composite),
                "breakdown": breakdown,
                "flags": flags,
                "sources_active": list(scores.keys()),
                "updated_at": datetime.now().isoformat(),
            }

            # Save to both caches
            self._mem_cache[epic] = {"data": result, "timestamp": time.time()}
            self._save_to_db(epic, result)

            logger.info(f"[Sentiment] {epic}: {composite}/100 ({result['label']}) sources={list(scores.keys())}")

        except Exception as e:
            logger.error(f"[Sentiment] Update failed for {epic}: {e}")
        finally:
            self._updating.discard(epic)

    # ── Source Fetchers ───────────────────────────────────────

    def _fetch_cryptopanic_sentiment(self, ticker):
        """A) CryptoPanic news sentiment."""
        try:
            url = "https://cryptopanic.com/api/developer/v2/posts/"
            params = {
                "auth_token": self.cryptopanic_key,
                "currencies": ticker,
                "public": "true",
                "kind": "news",
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            posts = resp.json().get("results", [])

            if not posts:
                return None

            bullish = 0
            bearish = 0
            headlines = []
            for post in posts[:10]:
                title = post.get("title", "")
                votes = post.get("votes", {})
                bullish += votes.get("positive", 0)
                bearish += votes.get("negative", 0)

                text_lower = title.lower()
                bullish += sum(1 for w in BULLISH_WORDS if w in text_lower)
                bearish += sum(1 for w in BEARISH_WORDS if w in text_lower)
                headlines.append(title[:60])

            total = bullish + bearish
            score = (bullish / total * 100) if total > 0 else 50

            return {
                "score": round(score),
                "weight": 3.0,
                "details": f"{len(posts)} nyheder, {bullish}B/{bearish}S",
                "headlines": headlines[:3],
            }
        except Exception as e:
            logger.debug(f"[Sentiment] CryptoPanic error: {e}")
            return None

    def _fetch_twitter_sentiment(self, ticker, name):
        """B) Twitter sentiment via public nitter/search (no API key needed)."""
        try:
            # Use a public Twitter search proxy/API if available
            # Fallback: use CryptoPanic which includes Twitter sources
            # For now, return None if no dedicated Twitter access
            # This can be expanded with a proper Twitter API key later
            return None
        except Exception:
            return None

    def _fetch_reddit_sentiment(self, search_terms):
        """C) Reddit sentiment from crypto subreddits."""
        try:
            token = self._get_reddit_token()
            if not token:
                return None

            query = " OR ".join(search_terms)
            subreddits = ["cryptocurrency", "CryptoMarkets"]
            all_posts = []

            for sub in subreddits:
                time.sleep(1)  # Rate limit
                url = f"https://oauth.reddit.com/r/{sub}/search"
                headers = {"Authorization": f"Bearer {token}", "User-Agent": "CryptoBot/1.0"}
                params = {"q": query, "sort": "hot", "t": "day", "limit": 10, "restrict_sr": "on"}
                resp = requests.get(url, params=params, headers=headers, timeout=10)
                if resp.status_code == 200:
                    posts = resp.json().get("data", {}).get("children", [])
                    all_posts.extend([p["data"] for p in posts])

            if not all_posts:
                return None

            bullish = 0
            bearish = 0
            for post in all_posts:
                text = (post.get("title", "") + " " + post.get("selftext", "")[:200]).lower()
                upvotes = max(post.get("score", 1), 1)
                weight = 1 + (upvotes / 100)

                b = sum(1 for w in BULLISH_WORDS if w in text)
                s = sum(1 for w in BEARISH_WORDS if w in text)
                bullish += b * weight
                bearish += s * weight

            total = bullish + bearish
            score = (bullish / total * 100) if total > 0 else 50

            return {
                "score": round(score),
                "weight": 2.0,
                "details": f"{len(all_posts)} posts, {bullish:.0f}B/{bearish:.0f}S",
            }
        except Exception as e:
            logger.debug(f"[Sentiment] Reddit error: {e}")
            return None

    def _fetch_fear_greed(self):
        """D) Fear & Greed Index."""
        try:
            resp = requests.get(FEAR_GREED_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json().get("data", [{}])[0]
            value = int(data.get("value", 50))
            label = data.get("value_classification", "Neutral")

            return {
                "score": value,
                "weight": 2.0,
                "details": f"F&G: {value}/100 ({label})",
                "raw_value": value,
            }
        except Exception as e:
            logger.debug(f"[Sentiment] Fear&Greed error: {e}")
            return None

    def _fetch_youtube_sentiment(self, name):
        """E) YouTube trending crypto videos (low priority)."""
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": f"{name} crypto trading",
                "type": "video",
                "order": "date",
                "maxResults": 5,
                "publishedAfter": (datetime.utcnow().replace(hour=0, minute=0, second=0)).isoformat() + "Z",
                "key": self.youtube_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("items", [])

            if len(items) < 2:
                return None

            bullish = 0
            bearish = 0
            for item in items:
                title = item.get("snippet", {}).get("title", "").lower()
                bullish += sum(1 for w in BULLISH_WORDS if w in title)
                bearish += sum(1 for w in BEARISH_WORDS if w in title)

            total = bullish + bearish
            score = (bullish / total * 100) if total > 0 else 50

            return {
                "score": round(score),
                "weight": 1.0,
                "details": f"{len(items)} videoer",
            }
        except Exception as e:
            logger.debug(f"[Sentiment] YouTube error: {e}")
            return None

    # ── Aggregation ───────────────────────────────────────────

    def _aggregate(self, scores):
        """Weighted average of all source scores."""
        if not scores:
            return 50, {}

        total_weight = 0
        weighted_sum = 0
        breakdown = {}

        for source, data in scores.items():
            score = data.get("score", 50)
            weight = data.get("weight", 1.0)
            weighted_sum += score * weight
            total_weight += weight
            breakdown[source] = {
                "score": score,
                "weight": weight,
                "details": data.get("details", ""),
            }

        composite = round(weighted_sum / total_weight) if total_weight > 0 else 50
        return composite, breakdown

    # ── Helpers ────────────────────────────────────────────────

    def _get_reddit_token(self):
        """Get Reddit OAuth token."""
        now = time.time()
        if self._reddit_token and now < self._reddit_token_expiry:
            return self._reddit_token
        try:
            auth = requests.auth.HTTPBasicAuth(self.reddit_client_id, self.reddit_client_secret)
            data = {"grant_type": "password", "username": self.reddit_username, "password": self.reddit_password}
            headers = {"User-Agent": "CryptoBot/1.0"}
            resp = requests.post("https://www.reddit.com/api/v1/access_token", auth=auth, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            token_data = resp.json()
            self._reddit_token = token_data["access_token"]
            self._reddit_token_expiry = now + token_data.get("expires_in", 3600) - 60
            return self._reddit_token
        except Exception:
            return None

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

    def _neutral(self):
        return {
            "composite_score": 50,
            "label": "NEUTRAL",
            "breakdown": {},
            "flags": [],
            "sources_active": [],
        }

    def _save_to_db(self, epic, data):
        """Save sentiment to SQLite cache."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO sentiment_cache (epic, data, updated_at) VALUES (?, ?, ?)",
                (epic, json.dumps(data), datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"[Sentiment] DB save error: {e}")

    def _load_from_db(self, epic):
        """Load sentiment from SQLite cache if fresh."""
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT data, updated_at FROM sentiment_cache WHERE epic = ?", (epic,)
            ).fetchone()
            conn.close()
            if row:
                updated = datetime.fromisoformat(row[1])
                age = (datetime.now() - updated).total_seconds()
                if age < self._cache_ttl:
                    return json.loads(row[0])
        except Exception:
            pass
        return None

    @staticmethod
    def format_for_prompt(sentiment_data):
        """Format sentiment for AI prompt."""
        score = sentiment_data.get("composite_score", 50)
        label = sentiment_data.get("label", "NEUTRAL")
        breakdown = sentiment_data.get("breakdown", {})
        flags = sentiment_data.get("flags", [])

        lines = [f"SENTIMENT SCORE: {score}/100 ({label})"]

        for source, data in breakdown.items():
            lines.append(f"  {source}: {data['score']}/100 (weight: {data['weight']}) — {data.get('details', '')}")

        if flags:
            lines.append("SENTIMENT FLAGS:")
            for flag in flags:
                lines.append(f"  ⚠ {flag}")

        return "\n".join(lines)
