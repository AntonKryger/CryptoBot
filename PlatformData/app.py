"""
PlatformData — Dedicated data service for the SaaS platform.
Separate from bot containers to avoid shared rate limits.
Uses its own Kraken API key.
"""

import os
import time
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS
import ccxt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [PlatformData] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# --- Kraken exchange (platform-dedicated API key) ---
KRAKEN_API_KEY = os.environ.get("KRAKEN_API_KEY", "")
KRAKEN_API_SECRET = os.environ.get("KRAKEN_API_SECRET", "")

# Only pass credentials if they exist (public data works without)
exchange_config: dict = {"enableRateLimit": True}
if KRAKEN_API_KEY and KRAKEN_API_SECRET:
    exchange_config["apiKey"] = KRAKEN_API_KEY
    exchange_config["secret"] = KRAKEN_API_SECRET
    log.info("Using authenticated Kraken API (higher rate limits)")
else:
    log.info("Using public Kraken API (no credentials)")

exchange = ccxt.kraken(exchange_config)

# Symbol aliases (BTC → XBT for Kraken)
SYMBOL_ALIASES = {"BTC": "XBT"}

# Resolution map: our names → ccxt timeframes
RESOLUTION_MAP = {
    "MINUTE_1": "1m",
    "MINUTE_5": "5m",
    "MINUTE_15": "15m",
    "MINUTE_30": "30m",
    "HOUR": "1h",
    "HOUR_4": "4h",
    "DAY": "1d",
    "WEEK": "1w",
}

# --- In-memory cache ---
_cache: dict = {}
CACHE_TTL = 10  # seconds


def _get_cached(key: str):
    if key in _cache and time.time() - _cache[key]["ts"] < CACHE_TTL:
        return _cache[key]["data"]
    return None


def _set_cached(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


def _normalize_pair(epic: str) -> str:
    """Convert BTCUSD or BTC/USD → BTC/USD (ccxt format)."""
    clean = epic.replace("/", "").upper()
    # Extract base (everything before USD/EUR/GBP)
    for quote in ("USD", "EUR", "GBP"):
        if clean.endswith(quote):
            base = clean[: -len(quote)]
            # Apply aliases
            for old, new in SYMBOL_ALIASES.items():
                if base == old:
                    base = new
            return f"{base}/{quote}"
    return epic


# --- Routes ---


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "PlatformData"})


@app.route("/api/prices")
def prices():
    """OHLCV candle data — cached, rate-limited, isolated from bots."""
    epic = request.args.get("epic", "BTCUSD")
    resolution = request.args.get("resolution", "HOUR")
    limit = min(int(request.args.get("limit", "200")), 720)

    timeframe = RESOLUTION_MAP.get(resolution)
    if not timeframe:
        return jsonify({"error": f"Invalid resolution: {resolution}"}), 400

    pair = _normalize_pair(epic)
    cache_key = f"ohlcv:{pair}:{timeframe}:{limit}"

    cached = _get_cached(cache_key)
    if cached:
        return jsonify(cached)

    try:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
        candles = [
            {
                "time": int(c[0] / 1000),  # ms → seconds
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
            }
            for c in ohlcv
        ]
        result = {"candles": candles}
        _set_cached(cache_key, result)
        return jsonify(result)
    except Exception as e:
        log.error(f"Kraken OHLCV error for {pair}: {e}")
        return jsonify({"error": "Failed to fetch price data"}), 502


@app.route("/api/ticker")
def ticker():
    """Current price ticker — bid, ask, last, volume, change."""
    epic = request.args.get("epic", "BTCUSD")
    pair = _normalize_pair(epic)
    cache_key = f"ticker:{pair}"

    cached = _get_cached(cache_key)
    if cached:
        return jsonify(cached)

    try:
        t = exchange.fetch_ticker(pair)
        result = {
            "symbol": epic,
            "bid": t.get("bid"),
            "ask": t.get("ask"),
            "last": t.get("last"),
            "high": t.get("high"),
            "low": t.get("low"),
            "volume": t.get("baseVolume"),
            "change_pct": t.get("percentage"),
            "timestamp": t.get("timestamp"),
        }
        _set_cached(cache_key, result)
        return jsonify(result)
    except Exception as e:
        log.error(f"Kraken ticker error for {pair}: {e}")
        return jsonify({"error": "Failed to fetch ticker"}), 502


@app.route("/api/orderbook")
def orderbook():
    """Order book depth — bids and asks."""
    epic = request.args.get("epic", "BTCUSD")
    depth = min(int(request.args.get("depth", "20")), 100)
    pair = _normalize_pair(epic)
    cache_key = f"orderbook:{pair}:{depth}"

    cached = _get_cached(cache_key)
    if cached:
        return jsonify(cached)

    try:
        ob = exchange.fetch_order_book(pair, limit=depth)
        result = {
            "bids": ob["bids"],
            "asks": ob["asks"],
            "timestamp": ob.get("timestamp"),
        }
        _set_cached(cache_key, result)
        return jsonify(result)
    except Exception as e:
        log.error(f"Kraken orderbook error for {pair}: {e}")
        return jsonify({"error": "Failed to fetch orderbook"}), 502


@app.route("/api/markets")
def markets():
    """List available trading pairs."""
    cache_key = "markets"
    cached = _get_cached(cache_key)
    if cached:
        return jsonify(cached)

    try:
        exchange.load_markets()
        pairs = [
            {
                "symbol": m["symbol"],
                "base": m["base"],
                "quote": m["quote"],
                "active": m["active"],
            }
            for m in exchange.markets.values()
            if m["quote"] == "USD" and m["active"]
        ]
        pairs.sort(key=lambda p: p["base"])
        result = {"markets": pairs}
        # Cache markets for 5 minutes
        _cache["markets"] = {"data": result, "ts": time.time() + 290}
        return jsonify(result)
    except Exception as e:
        log.error(f"Kraken markets error: {e}")
        return jsonify({"error": "Failed to fetch markets"}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5100"))
    log.info(f"PlatformData starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
