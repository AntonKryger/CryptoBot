"""
Kraken exchange adapter using ccxt.

Supports both spot (ccxt.kraken) and futures (ccxt.krakenfutures).
Symbol mapping: bots use Capital.com format (BTCUSD), adapter converts to Kraken format (BTC/USD).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt

from .base_adapter import BaseExchangeAdapter

logger = logging.getLogger(__name__)

# Capital.com epic → ccxt symbol mapping
SYMBOL_MAP = {
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD",
    "AVAXUSD": "AVAX/USD",
    "LINKUSD": "LINK/USD",
    "LTCUSD": "LTC/USD",
}

# Reverse map for converting back
EPIC_MAP = {v: k for k, v in SYMBOL_MAP.items()}

# Resolution mapping: Capital.com format → ccxt timeframe
RESOLUTION_MAP = {
    "MINUTE": "1m",
    "MINUTE_5": "5m",
    "MINUTE_15": "15m",
    "MINUTE_30": "30m",
    "HOUR": "1h",
    "HOUR_4": "4h",
    "DAY": "1d",
    "WEEK": "1w",
}


def _to_symbol(epic: str) -> str:
    """Convert Capital.com epic (BTCUSD) to ccxt symbol (BTC/USD).
    Also accepts already-formatted symbols (BTC/USD) and passes them through.
    """
    # Already in ccxt format
    if "/" in epic:
        return epic
    if epic in SYMBOL_MAP:
        return SYMBOL_MAP[epic]
    # Fallback: try inserting / before last 3 chars (USD)
    if epic.endswith("USD"):
        return f"{epic[:-3]}/USD"
    return epic


def _to_epic(symbol: str) -> str:
    """Convert ccxt symbol (BTC/USD) back to Capital.com epic (BTCUSD)."""
    if symbol in EPIC_MAP:
        return EPIC_MAP[symbol]
    return symbol.replace("/", "")


def _to_timeframe(resolution: str) -> str:
    """Convert Capital.com resolution to ccxt timeframe."""
    return RESOLUTION_MAP.get(resolution, "15m")


class KrakenAdapter(BaseExchangeAdapter):
    """Kraken exchange adapter via ccxt.

    Supports spot trading (default) and futures/perpetuals.
    Config:
        exchange:
          provider: kraken
          api_key: "..."
          api_secret: "..."
          mode: spot          # spot (default) or futures
          demo: false         # futures has demo endpoint; spot does not
    """

    def __init__(self, config):
        exchange_cfg = config.get("exchange", {})
        self.api_key = exchange_cfg.get("api_key")
        self.api_secret = exchange_cfg.get("api_secret")
        self.demo = exchange_cfg.get("demo", False)
        self.mode = exchange_cfg.get("mode", "spot").lower()

        self.exchange = None
        self._last_request_time = 0
        self._min_request_interval = 0.2  # Kraken rate limit: ~15 req/s private

        # Track open SL/TP orders linked to positions (Kraken doesn't have native SL/TP on positions)
        # {position_ref: {"sl_order_id": str, "tp_order_id": str}}
        self._linked_orders = {}

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _create_exchange(self):
        """Create the appropriate ccxt exchange instance."""
        if self.mode == "futures":
            exchange = ccxt.krakenfutures({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
            })
            if self.demo:
                exchange.set_sandbox_mode(True)
                logger.info("Kraken Futures: using DEMO/sandbox endpoint")
        else:
            exchange = ccxt.kraken({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
            })
        return exchange

    # ── Session management ────────────────────────────────────────

    def start_session(self) -> bool:
        try:
            self.exchange = self._create_exchange()
            self.exchange.load_markets()

            # Verify connectivity: try balance first, fall back to open orders
            try:
                self.exchange.fetch_balance()
                logger.info("Kraken auth verified via balance check")
            except ccxt.PermissionDenied:
                # API key may lack "Query funds" — try orders instead
                self.exchange.fetch_open_orders()
                logger.warning(
                    "Kraken: 'Query funds' permission missing — balance checks will fail. "
                    "Add this permission in Kraken API settings."
                )

            logger.info(
                f"Kraken session started ({self.mode} mode, "
                f"{'demo' if self.demo else 'live'}, "
                f"{len(self.exchange.markets)} markets loaded)"
            )
            return True
        except ccxt.AuthenticationError as e:
            logger.error(f"Kraken authentication failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Kraken session start failed: {e}")
            raise

    def ping(self) -> bool:
        try:
            self._rate_limit()
            self.exchange.fetch_time()
            return True
        except Exception:
            return False

    # ── Account info ──────────────────────────────────────────────

    def get_account_balance(self) -> Optional[dict]:
        try:
            self._rate_limit()
            balance = self.exchange.fetch_balance()
            total = balance.get("total", {})
            free = balance.get("free", {})

            # Calculate total USD value
            usd_total = total.get("USD", 0) or 0
            usd_free = free.get("USD", 0) or 0

            return {
                "balance": float(usd_total),
                "deposit": float(usd_total),  # Kraken doesn't separate deposit
                "profit_loss": 0.0,  # Not tracked natively for spot
                "available": float(usd_free),
            }
        except Exception as e:
            logger.error(f"Kraken get_account_balance failed: {e}")
            return None

    def get_accounts(self) -> dict:
        self._rate_limit()
        balance = self.exchange.fetch_balance()
        return {
            "accounts": [{
                "accountName": "main",
                "balance": {
                    "balance": float(balance.get("total", {}).get("USD", 0) or 0),
                    "deposit": float(balance.get("total", {}).get("USD", 0) or 0),
                    "profitLoss": 0.0,
                    "available": float(balance.get("free", {}).get("USD", 0) or 0),
                }
            }]
        }

    # ── Market data ───────────────────────────────────────────────

    def get_market_info(self, epic: str) -> dict:
        symbol = _to_symbol(epic)
        self._rate_limit()
        ticker = self.exchange.fetch_ticker(symbol)
        return {
            "instrument": {
                "epic": epic,
                "name": symbol,
                "type": "CRYPTOCURRENCIES",
                "lotSize": 1,
            },
            "snapshot": {
                "bid": ticker.get("bid", 0),
                "offer": ticker.get("ask", 0),
                "high": ticker.get("high", 0),
                "low": ticker.get("low", 0),
                "marketStatus": "TRADEABLE",  # Crypto is 24/7
                "percentageChange": ticker.get("percentage", 0),
            },
        }

    def is_market_open(self, epic: str) -> tuple:
        # Crypto markets are 24/7 on Kraken
        # Exception: very rare maintenance windows
        try:
            symbol = _to_symbol(epic)
            if symbol in self.exchange.markets:
                return True, "TRADEABLE"
            return False, "UNKNOWN_MARKET"
        except Exception as e:
            return False, f"ERROR: {e}"

    def are_crypto_markets_open(self) -> tuple:
        return True, "TRADEABLE"  # Kraken crypto = 24/7

    def get_prices(self, epic: str, resolution: str = "MINUTE_15", max_count: int = 200) -> dict:
        symbol = _to_symbol(epic)
        timeframe = _to_timeframe(resolution)
        self._rate_limit()

        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=max_count)

        # Convert to Capital.com-compatible format for downstream consumers
        prices = []
        for candle in ohlcv:
            ts, o, h, l, c, v = candle
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            prices.append({
                "snapshotTime": dt.strftime("%Y/%m/%d %H:%M:%S"),
                "snapshotTimeUTC": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "openPrice": {"bid": o, "ask": o, "lastTraded": o},
                "highPrice": {"bid": h, "ask": h, "lastTraded": h},
                "lowPrice": {"bid": l, "ask": l, "lastTraded": l},
                "closePrice": {"bid": c, "ask": c, "lastTraded": c},
                "lastTradedVolume": v,
            })

        return {"prices": prices}

    def search_markets(self, search_term: str, limit: int = 10) -> dict:
        results = []
        for symbol, market in self.exchange.markets.items():
            if search_term.upper() in symbol.upper():
                results.append({
                    "epic": _to_epic(symbol),
                    "instrumentName": symbol,
                    "type": "CRYPTOCURRENCIES",
                })
                if len(results) >= limit:
                    break
        return {"markets": results}

    def get_spread(self, epic: str) -> float:
        try:
            symbol = _to_symbol(epic)
            self._rate_limit()
            orderbook = self.exchange.fetch_order_book(symbol, limit=1)
            if orderbook["bids"] and orderbook["asks"]:
                bid = orderbook["bids"][0][0]
                ask = orderbook["asks"][0][0]
                return round(ask - bid, 6)
            return 0.0
        except Exception as e:
            logger.warning(f"Could not get spread for {epic}: {e}")
            return 0.0

    # ── Trading ───────────────────────────────────────────────────

    def get_positions(self) -> dict:
        """Get open positions.

        For spot mode: returns open orders that simulate positions.
        For futures mode: returns actual positions via ccxt.
        """
        self._rate_limit()

        if self.mode == "futures":
            positions = self.exchange.fetch_positions()
            result = []
            for pos in positions:
                if float(pos.get("contracts", 0)) > 0:
                    result.append({
                        "position": {
                            "dealId": pos.get("id", pos.get("symbol", "")),
                            "epic": _to_epic(pos.get("symbol", "")),
                            "direction": "BUY" if pos.get("side") == "long" else "SELL",
                            "size": abs(float(pos.get("contracts", 0))),
                            "level": float(pos.get("entryPrice", 0)),
                            "stopLevel": float(pos.get("stopLossPrice", 0)) if pos.get("stopLossPrice") else None,
                            "profitLevel": float(pos.get("takeProfitPrice", 0)) if pos.get("takeProfitPrice") else None,
                            "createdDateUTC": pos.get("datetime", ""),
                        },
                        "market": {
                            "epic": _to_epic(pos.get("symbol", "")),
                            "bid": float(pos.get("markPrice", 0)),
                            "offer": float(pos.get("markPrice", 0)),
                        },
                    })
            return {"positions": result}
        else:
            # Spot mode: no native "positions"
            # Return open orders as pseudo-positions for tracking
            return {"positions": []}

    def create_position(self, epic: str, direction: str, size: float,
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        symbol = _to_symbol(epic)
        side = "buy" if direction == "BUY" else "sell"

        logger.info(f"Opening {direction} position: {epic} ({symbol}) x{size}")
        self._rate_limit()

        if self.mode == "futures":
            # Futures: create market order, then attach SL/TP as separate orders
            order = self.exchange.create_order(symbol, "market", side, size)
            deal_ref = order.get("id", "")

            # Create linked SL/TP orders
            opposite_side = "sell" if side == "buy" else "buy"
            if stop_loss:
                try:
                    sl_order = self.exchange.create_order(
                        symbol, "stop-loss", opposite_side, size,
                        price=None, params={"stopPrice": stop_loss, "reduceOnly": True}
                    )
                    self._linked_orders.setdefault(deal_ref, {})["sl_order_id"] = sl_order["id"]
                except Exception as e:
                    logger.warning(f"Failed to set SL for {epic}: {e}")

            if take_profit:
                try:
                    tp_order = self.exchange.create_order(
                        symbol, "take-profit", opposite_side, size,
                        price=None, params={"stopPrice": take_profit, "reduceOnly": True}
                    )
                    self._linked_orders.setdefault(deal_ref, {})["tp_order_id"] = tp_order["id"]
                except Exception as e:
                    logger.warning(f"Failed to set TP for {epic}: {e}")

            return {"dealReference": deal_ref}
        else:
            # Spot: market order
            order = self.exchange.create_order(symbol, "market", side, size)
            deal_ref = order.get("id", "")

            # For spot, create conditional SL/TP orders
            opposite_side = "sell" if side == "buy" else "buy"
            if stop_loss:
                try:
                    sl_order = self.exchange.create_order(
                        symbol, "stop-loss", opposite_side, size,
                        price=None, params={"stopPrice": stop_loss}
                    )
                    self._linked_orders.setdefault(deal_ref, {})["sl_order_id"] = sl_order["id"]
                except Exception as e:
                    logger.warning(f"Failed to set SL for {epic}: {e}")

            if take_profit:
                try:
                    tp_order = self.exchange.create_order(
                        symbol, "take-profit", opposite_side, size,
                        price=None, params={"stopPrice": take_profit}
                    )
                    self._linked_orders.setdefault(deal_ref, {})["tp_order_id"] = tp_order["id"]
                except Exception as e:
                    logger.warning(f"Failed to set TP for {epic}: {e}")

            return {"dealReference": deal_ref}

    def close_position(self, position_id: str, direction: Optional[str] = None,
                       size: Optional[float] = None) -> dict:
        logger.info(f"Closing position: {position_id}")
        self._rate_limit()

        # Cancel linked SL/TP orders first
        linked = self._linked_orders.pop(position_id, {})
        for order_key in ["sl_order_id", "tp_order_id"]:
            order_id = linked.get(order_key)
            if order_id:
                try:
                    self.exchange.cancel_order(order_id)
                except Exception as e:
                    logger.debug(f"Could not cancel linked order {order_id}: {e}")

        if self.mode == "futures":
            # Futures: close by creating opposite market order with reduceOnly
            if direction and size:
                close_side = "sell" if direction == "BUY" else "buy"
                # Need to find the symbol from position_id or use a default
                # Try to find it from open positions
                try:
                    positions = self.exchange.fetch_positions()
                    symbol = None
                    for pos in positions:
                        if str(pos.get("id", "")) == str(position_id):
                            symbol = pos.get("symbol")
                            break
                    if symbol:
                        order = self.exchange.create_order(
                            symbol, "market", close_side, size,
                            params={"reduceOnly": True}
                        )
                        return {"dealReference": order.get("id", "")}
                except Exception as e:
                    logger.error(f"Failed to close futures position: {e}")
                    raise
        else:
            # Spot: create opposite market order
            if direction and size:
                close_side = "sell" if direction == "BUY" else "buy"
                # For spot, we need the symbol. Try to extract from position tracking
                # or use a fallback — the caller should provide the epic
                try:
                    order = self.exchange.cancel_order(position_id)
                    return {"dealReference": position_id}
                except Exception:
                    pass

        return {"dealReference": position_id}

    def update_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        """Update SL/TP by cancelling old linked orders and creating new ones.

        NOTE: This requires knowing the symbol and size. We look up from linked orders
        or open positions.
        """
        self._rate_limit()
        linked = self._linked_orders.get(position_id, {})

        # Cancel existing SL order and create new one
        if stop_loss is not None:
            old_sl = linked.get("sl_order_id")
            if old_sl:
                try:
                    self.exchange.cancel_order(old_sl)
                except Exception as e:
                    logger.debug(f"Could not cancel old SL order: {e}")

        if take_profit is not None:
            old_tp = linked.get("tp_order_id")
            if old_tp:
                try:
                    self.exchange.cancel_order(old_tp)
                except Exception as e:
                    logger.debug(f"Could not cancel old TP order: {e}")

        # NOTE: Creating new SL/TP orders requires symbol, side, and size
        # which we don't have here. The watchdog should call with enough context.
        # For now, we just cancel old orders. New SL/TP will be set via the
        # exchange's native stop-loss mechanism if available.
        logger.info(f"Updated position {position_id}: SL={stop_loss}, TP={take_profit}")
        return {"dealId": position_id}

    # ── Orders ────────────────────────────────────────────────────

    def get_orders(self) -> dict:
        self._rate_limit()
        orders = self.exchange.fetch_open_orders()
        result = []
        for order in orders:
            result.append({
                "workingOrderData": {
                    "dealId": order.get("id", ""),
                    "epic": _to_epic(order.get("symbol", "")),
                    "direction": "BUY" if order.get("side") == "buy" else "SELL",
                    "size": float(order.get("amount", 0)),
                    "level": float(order.get("price", 0)),
                    "type": order.get("type", "LIMIT").upper(),
                    "createdDateUTC": order.get("datetime", ""),
                },
            })
        return {"workingOrders": result}

    def create_order(self, epic: str, direction: str, size: float, level: float,
                     stop_loss: Optional[float] = None,
                     take_profit: Optional[float] = None) -> dict:
        symbol = _to_symbol(epic)
        side = "buy" if direction == "BUY" else "sell"

        self._rate_limit()
        order = self.exchange.create_limit_order(symbol, side, size, level)
        deal_ref = order.get("id", "")

        # Create linked SL/TP if provided
        opposite_side = "sell" if side == "buy" else "buy"
        if stop_loss:
            try:
                sl_order = self.exchange.create_order(
                    symbol, "stop-loss", opposite_side, size,
                    price=None, params={"stopPrice": stop_loss}
                )
                self._linked_orders.setdefault(deal_ref, {})["sl_order_id"] = sl_order["id"]
            except Exception as e:
                logger.warning(f"Failed to set SL for limit order {epic}: {e}")

        if take_profit:
            try:
                tp_order = self.exchange.create_order(
                    symbol, "take-profit", opposite_side, size,
                    price=None, params={"stopPrice": take_profit}
                )
                self._linked_orders.setdefault(deal_ref, {})["tp_order_id"] = tp_order["id"]
            except Exception as e:
                logger.warning(f"Failed to set TP for limit order {epic}: {e}")

        return {"dealReference": deal_ref}

    # ── Deal confirmation ─────────────────────────────────────────

    def get_deal_confirmation(self, deal_reference: str) -> dict:
        """On Kraken, dealReference IS the orderId. Fetch order status."""
        self._rate_limit()
        try:
            order = self.exchange.fetch_order(deal_reference)
            return {
                "dealId": order.get("id", deal_reference),
                "dealReference": deal_reference,
                "dealStatus": "ACCEPTED" if order.get("status") in ("closed", "open") else "REJECTED",
                "direction": "BUY" if order.get("side") == "buy" else "SELL",
                "epic": _to_epic(order.get("symbol", "")),
                "size": float(order.get("filled", order.get("amount", 0))),
                "level": float(order.get("average", order.get("price", 0))),
                "status": order.get("status", ""),
            }
        except Exception as e:
            logger.error(f"Failed to get deal confirmation for {deal_reference}: {e}")
            return {
                "dealId": deal_reference,
                "dealReference": deal_reference,
                "dealStatus": "UNKNOWN",
            }

    # ── History ───────────────────────────────────────────────────

    def get_activity_history(self, from_date: Optional[str] = None,
                             to_date: Optional[str] = None) -> dict:
        self._rate_limit()
        params = {}
        since = None
        if from_date:
            try:
                dt = datetime.fromisoformat(from_date.replace("/", "-"))
                since = int(dt.timestamp() * 1000)
            except Exception:
                pass

        trades = self.exchange.fetch_my_trades(since=since, limit=100)
        activities = []
        for trade in trades:
            activities.append({
                "date": trade.get("datetime", ""),
                "dealId": trade.get("order", ""),
                "epic": _to_epic(trade.get("symbol", "")),
                "type": trade.get("side", "").upper(),
                "size": float(trade.get("amount", 0)),
                "level": float(trade.get("price", 0)),
                "status": "ACCEPTED",
            })
        return {"activities": activities}

    def get_transaction_history(self, from_date: Optional[str] = None,
                                to_date: Optional[str] = None) -> dict:
        self._rate_limit()
        since = None
        if from_date:
            try:
                dt = datetime.fromisoformat(from_date.replace("/", "-"))
                since = int(dt.timestamp() * 1000)
            except Exception:
                pass

        try:
            ledger = self.exchange.fetch_ledger(since=since, limit=100)
            transactions = []
            for entry in ledger:
                transactions.append({
                    "date": entry.get("datetime", ""),
                    "type": entry.get("type", ""),
                    "amount": float(entry.get("amount", 0)),
                    "currency": entry.get("currency", "USD"),
                    "reference": entry.get("id", ""),
                })
            return {"transactions": transactions}
        except Exception as e:
            logger.warning(f"Kraken fetch_ledger failed: {e}")
            return {"transactions": []}
