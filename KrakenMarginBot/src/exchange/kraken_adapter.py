"""
Kraken exchange adapter using ccxt — extended for KrakenBots multi-strategy system.

Adds: orderbook depth, batch orders, cancel-all, open orders fetch.
Adds: spot position tracker integration (Kraken spot has no native positions).
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt

from .base_adapter import BaseExchangeAdapter

logger = logging.getLogger(__name__)

# Symbol mapping: Capital.com epic → ccxt symbol
SYMBOL_MAP = {
    "BTCUSD": "BTC/USD",
    "ETHUSD": "ETH/USD",
    "SOLUSD": "SOL/USD",
    "AVAXUSD": "AVAX/USD",
    "LINKUSD": "LINK/USD",
    "LTCUSD": "LTC/USD",
}
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
    if "/" in epic:
        return epic
    if epic in SYMBOL_MAP:
        return SYMBOL_MAP[epic]
    if epic.endswith("USD"):
        return f"{epic[:-3]}/USD"
    return epic


def _to_epic(symbol: str) -> str:
    if symbol in EPIC_MAP:
        return EPIC_MAP[symbol]
    return symbol.replace("/", "")


def _to_timeframe(resolution: str) -> str:
    return RESOLUTION_MAP.get(resolution, "15m")


class KrakenAdapter(BaseExchangeAdapter):
    """Kraken exchange adapter via ccxt — extended for multi-bot portfolio system.

    Config:
        exchange:
          provider: kraken
          api_key: "..."
          api_secret: "..."
          mode: spot              # spot | spot_margin | futures
          margin_mode: cross      # cross | isolated (for spot_margin)
          leverage: 2             # 1-5 for spot margin
          demo: false
    """

    def __init__(self, config):
        exchange_cfg = config.get("exchange", {})
        self.api_key = exchange_cfg.get("api_key")
        self.api_secret = exchange_cfg.get("api_secret")
        self.demo = exchange_cfg.get("demo", False)
        self.mode = exchange_cfg.get("mode", "spot").lower()

        # Margin settings (spot_margin mode)
        self.leverage = exchange_cfg.get("leverage", 1)
        self.margin_mode = exchange_cfg.get("margin_mode", "cross")  # cross or isolated
        self.is_margin = self.mode == "spot_margin"

        self.exchange = None
        self._last_request_time = 0
        self._min_request_interval = 0.2  # Kraken rate limit: ~15 req/s private

        # Track open SL/TP orders linked to positions
        self._linked_orders = {}

        # Spot position tracker (set externally after init)
        self.position_tracker = None

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _margin_params(self, extra: dict = None) -> dict:
        """Build margin order params. Returns {} for spot mode, leverage params for margin."""
        params = {}
        if self.is_margin and self.leverage > 1:
            params["leverage"] = self.leverage
        if extra:
            params.update(extra)
        return params

    def _create_exchange(self):
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
            # Both spot and spot_margin use the same ccxt.kraken class
            exchange = ccxt.kraken({
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
            })
            if self.is_margin:
                logger.info(f"Kraken Spot Margin: leverage={self.leverage}x, mode={self.margin_mode}")
        return exchange

    # ── Session management ────────────────────────────────────────

    def start_session(self) -> bool:
        try:
            self.exchange = self._create_exchange()
            self.exchange.load_markets()

            try:
                self.exchange.fetch_balance()
                logger.info("Kraken auth verified via balance check")
            except ccxt.PermissionDenied:
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
            usd_total = total.get("USD", 0) or 0
            usd_free = free.get("USD", 0) or 0

            result = {
                "balance": float(usd_total),
                "deposit": float(usd_total),
                "profit_loss": 0.0,
                "available": float(usd_free),
            }

            # Margin mode: fetch extended margin info
            if self.is_margin:
                try:
                    self._rate_limit()
                    # Kraken private API: TradeBalance gives margin equity info
                    margin_info = self.exchange.private_post_tradebalance()
                    margin_result = margin_info.get("result", {})

                    equity = float(margin_result.get("e", usd_total) or usd_total)  # Equivalent balance (equity)
                    trade_balance = float(margin_result.get("tb", usd_total) or usd_total)  # Trade balance
                    margin_used = float(margin_result.get("m", 0) or 0)  # Used margin
                    free_margin = float(margin_result.get("mf", usd_free) or usd_free)  # Free margin
                    unrealized_pl = float(margin_result.get("n", 0) or 0)  # Unrealized P/L
                    margin_level = float(margin_result.get("ml", 0) or 0)  # Margin level (%)
                    cost_basis = float(margin_result.get("c", 0) or 0)  # Cost basis of open positions

                    result.update({
                        "balance": equity,  # Use equity (includes unrealized P/L)
                        "equity": equity,
                        "trade_balance": trade_balance,
                        "margin_used": margin_used,
                        "free_margin": free_margin,
                        "available": free_margin,  # Override: free margin is what we can use
                        "unrealized_pl": unrealized_pl,
                        "margin_level": margin_level,  # % — 0 means no open positions
                        "cost_basis": cost_basis,
                        "leverage": self.leverage,
                        "is_margin": True,
                    })

                    logger.debug(
                        f"Margin balance: equity=${equity:.2f}, used=${margin_used:.2f}, "
                        f"free=${free_margin:.2f}, unrealized_pl=${unrealized_pl:.2f}, "
                        f"margin_level={margin_level:.0f}%"
                    )
                except Exception as e:
                    logger.warning(f"Margin balance fetch failed, using spot balance: {e}")

            return result
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

    def get_margin_status(self) -> Optional[dict]:
        """Get margin-specific status: margin level, used margin, liquidation proximity."""
        if not self.is_margin:
            return None
        try:
            self._rate_limit()
            margin_info = self.exchange.private_post_tradebalance()
            r = margin_info.get("result", {})
            margin_level = float(r.get("ml", 0) or 0)
            return {
                "equity": float(r.get("e", 0) or 0),
                "margin_used": float(r.get("m", 0) or 0),
                "free_margin": float(r.get("mf", 0) or 0),
                "margin_level": margin_level,
                "unrealized_pl": float(r.get("n", 0) or 0),
                "cost_basis": float(r.get("c", 0) or 0),
            }
        except Exception as e:
            logger.warning(f"get_margin_status failed: {e}")
            return None

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
                "marketStatus": "TRADEABLE",
                "percentageChange": ticker.get("percentage", 0),
            },
        }

    def is_market_open(self, epic: str) -> tuple:
        try:
            symbol = _to_symbol(epic)
            if symbol in self.exchange.markets:
                return True, "TRADEABLE"
            return False, "UNKNOWN_MARKET"
        except Exception as e:
            return False, f"ERROR: {e}"

    def are_crypto_markets_open(self) -> tuple:
        return True, "TRADEABLE"

    def get_prices(self, epic: str, resolution: str = "MINUTE_15", max_count: int = 200) -> dict:
        symbol = _to_symbol(epic)
        timeframe = _to_timeframe(resolution)
        self._rate_limit()

        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=max_count)

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

    # ── Extended Market Data (KrakenBots) ─────────────────────────

    def get_orderbook(self, epic: str, depth: int = 20) -> dict:
        """Get orderbook with specified depth for Grid/Volatility bots."""
        symbol = _to_symbol(epic)
        self._rate_limit()
        ob = self.exchange.fetch_order_book(symbol, limit=depth)
        return {
            "bids": ob.get("bids", []),  # [[price, amount], ...]
            "asks": ob.get("asks", []),
            "timestamp": ob.get("timestamp"),
            "epic": epic,
        }

    # ── Trading ───────────────────────────────────────────────────

    def get_positions(self) -> dict:
        """Get open positions.

        Spot mode: uses SpotPositionTracker (SQLite-based local tracking).
        Futures mode: uses ccxt fetch_positions.
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
            # Spot and spot_margin: use position tracker if available
            if self.position_tracker:
                return self.position_tracker.get_positions_for_adapter(self)
            return {"positions": []}

    def create_position(self, epic: str, direction: str, size: float,
                        stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        symbol = _to_symbol(epic)
        side = "buy" if direction == "BUY" else "sell"

        margin_tag = f" [margin {self.leverage}x]" if self.is_margin else ""
        logger.info(f"Opening {direction} position: {epic} ({symbol}) x{size}{margin_tag}")
        self._rate_limit()

        # Market order — with leverage for margin mode
        order = self.exchange.create_order(
            symbol, "market", side, size, params=self._margin_params()
        )
        deal_ref = order.get("id", "")
        fill_price = float(order.get("average", order.get("price", 0)) or 0)

        # Create linked SL/TP orders
        opposite_side = "sell" if side == "buy" else "buy"
        if stop_loss:
            try:
                sl_extra = {"stopPrice": stop_loss}
                if self.mode == "futures":
                    sl_extra["reduceOnly"] = True
                sl_order = self.exchange.create_order(
                    symbol, "stop-loss", opposite_side, size,
                    price=None, params=self._margin_params(sl_extra)
                )
                self._linked_orders.setdefault(deal_ref, {})["sl_order_id"] = sl_order["id"]
            except Exception as e:
                logger.warning(f"Failed to set SL for {epic}: {e}")

        if take_profit:
            try:
                tp_extra = {"stopPrice": take_profit}
                if self.mode == "futures":
                    tp_extra["reduceOnly"] = True
                tp_order = self.exchange.create_order(
                    symbol, "take-profit", opposite_side, size,
                    price=None, params=self._margin_params(tp_extra)
                )
                self._linked_orders.setdefault(deal_ref, {})["tp_order_id"] = tp_order["id"]
            except Exception as e:
                logger.warning(f"Failed to set TP for {epic}: {e}")

        # Track in position tracker (both spot and spot_margin use local tracker)
        if self.position_tracker and self.mode in ("spot", "spot_margin"):
            self.position_tracker.open_position(
                deal_id=deal_ref,
                epic=epic,
                direction=direction,
                size=size,
                entry_price=fill_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

        return {"dealReference": deal_ref, "fillPrice": fill_price, "size": size}

    def close_position(self, position_id: str, direction: Optional[str] = None,
                       size: Optional[float] = None, epic: Optional[str] = None) -> dict:
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

        # Resolve symbol from epic or position tracker
        symbol = None
        if epic:
            symbol = _to_symbol(epic)
        elif self.position_tracker:
            pos_info = self.position_tracker.get_position(position_id)
            if pos_info:
                symbol = _to_symbol(pos_info["epic"])
                if not direction:
                    direction = pos_info["direction"]
                if not size:
                    size = pos_info["size"]

        if symbol and direction and size:
            close_side = "sell" if direction == "BUY" else "buy"
            try:
                close_extra = {"reduceOnly": True} if self.mode == "futures" else {}
                order = self.exchange.create_order(
                    symbol, "market", close_side, size, params=self._margin_params(close_extra)
                )
                fill_price = float(order.get("average", order.get("price", 0)) or 0)

                # Update position tracker
                if self.position_tracker:
                    self.position_tracker.close_position(position_id, fill_price)

                return {"dealReference": order.get("id", ""), "fillPrice": fill_price}
            except Exception as e:
                logger.error(f"Failed to close position {position_id}: {e}")
                raise

        logger.warning(f"Insufficient info to close position {position_id}")
        return {"dealReference": position_id}

    def update_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> dict:
        """Update SL/TP by cancelling old linked orders and creating new ones."""
        self._rate_limit()
        linked = self._linked_orders.get(position_id, {})

        # Get position info for creating new orders
        pos_info = None
        if self.position_tracker:
            pos_info = self.position_tracker.get_position(position_id)

        # Cancel and recreate SL
        if stop_loss is not None:
            old_sl = linked.get("sl_order_id")
            if old_sl:
                try:
                    self.exchange.cancel_order(old_sl)
                except Exception as e:
                    logger.debug(f"Could not cancel old SL order: {e}")

            if pos_info:
                symbol = _to_symbol(pos_info["epic"])
                opposite_side = "sell" if pos_info["direction"] == "BUY" else "buy"
                size = pos_info["size"]
                try:
                    sl_extra = {"stopPrice": stop_loss}
                    if self.mode == "futures":
                        sl_extra["reduceOnly"] = True
                    sl_order = self.exchange.create_order(
                        symbol, "stop-loss", opposite_side, size,
                        price=None, params=self._margin_params(sl_extra)
                    )
                    self._linked_orders.setdefault(position_id, {})["sl_order_id"] = sl_order["id"]
                except Exception as e:
                    logger.warning(f"Failed to create new SL order: {e}")

        # Cancel and recreate TP
        if take_profit is not None:
            old_tp = linked.get("tp_order_id")
            if old_tp:
                try:
                    self.exchange.cancel_order(old_tp)
                except Exception as e:
                    logger.debug(f"Could not cancel old TP order: {e}")

            if pos_info:
                symbol = _to_symbol(pos_info["epic"])
                opposite_side = "sell" if pos_info["direction"] == "BUY" else "buy"
                size = pos_info["size"]
                try:
                    tp_extra = {"stopPrice": take_profit}
                    if self.mode == "futures":
                        tp_extra["reduceOnly"] = True
                    tp_order = self.exchange.create_order(
                        symbol, "take-profit", opposite_side, size,
                        price=None, params=self._margin_params(tp_extra)
                    )
                    self._linked_orders.setdefault(position_id, {})["tp_order_id"] = tp_order["id"]
                except Exception as e:
                    logger.warning(f"Failed to create new TP order: {e}")

        # Update position tracker
        if self.position_tracker:
            self.position_tracker.update_sl_tp(position_id, stop_loss, take_profit)

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
                    "level": float(order.get("price", 0) or 0),
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
        order = self.exchange.create_limit_order(
            symbol, side, size, level, params=self._margin_params()
        )
        deal_ref = order.get("id", "")

        opposite_side = "sell" if side == "buy" else "buy"
        if stop_loss:
            try:
                sl_order = self.exchange.create_order(
                    symbol, "stop-loss", opposite_side, size,
                    price=None, params=self._margin_params({"stopPrice": stop_loss})
                )
                self._linked_orders.setdefault(deal_ref, {})["sl_order_id"] = sl_order["id"]
            except Exception as e:
                logger.warning(f"Failed to set SL for limit order {epic}: {e}")

        if take_profit:
            try:
                tp_order = self.exchange.create_order(
                    symbol, "take-profit", opposite_side, size,
                    price=None, params=self._margin_params({"stopPrice": take_profit})
                )
                self._linked_orders.setdefault(deal_ref, {})["tp_order_id"] = tp_order["id"]
            except Exception as e:
                logger.warning(f"Failed to set TP for limit order {epic}: {e}")

        return {"dealReference": deal_ref}

    # ── Extended Orders (KrakenBots) ──────────────────────────────

    def create_batch_orders(self, orders: list) -> list:
        """Create multiple orders sequentially with rate limiting.

        Each order dict: {"epic", "direction", "size", "level", "type": "limit"|"stop-loss"|"take-profit"}
        Returns list of order results.
        """
        results = []
        for order_spec in orders:
            try:
                symbol = _to_symbol(order_spec["epic"])
                side = "buy" if order_spec["direction"] == "BUY" else "sell"
                order_type = order_spec.get("type", "limit")
                level = order_spec["level"]
                size = order_spec["size"]

                self._rate_limit()

                if order_type == "limit":
                    result = self.exchange.create_limit_order(
                        symbol, side, size, level, params=self._margin_params()
                    )
                elif order_type in ("stop-loss", "take-profit"):
                    result = self.exchange.create_order(
                        symbol, order_type, side, size,
                        price=None, params=self._margin_params({"stopPrice": level})
                    )
                else:
                    result = self.exchange.create_order(
                        symbol, order_type, side, size, level, params=self._margin_params()
                    )

                results.append({
                    "success": True,
                    "order_id": result.get("id", ""),
                    "epic": order_spec["epic"],
                    "level": level,
                    "side": order_spec["direction"],
                })
            except Exception as e:
                logger.error(f"Batch order failed for {order_spec.get('epic')}: {e}")
                results.append({
                    "success": False,
                    "error": str(e),
                    "epic": order_spec.get("epic"),
                })
        return results

    def cancel_all_orders(self, epic: str = None) -> int:
        """Cancel all open orders, optionally filtered by epic."""
        self._rate_limit()
        if epic:
            symbol = _to_symbol(epic)
            orders = self.exchange.fetch_open_orders(symbol)
        else:
            orders = self.exchange.fetch_open_orders()

        cancelled = 0
        for order in orders:
            try:
                self._rate_limit()
                self.exchange.cancel_order(order["id"], order.get("symbol"))
                cancelled += 1
            except Exception as e:
                logger.warning(f"Failed to cancel order {order['id']}: {e}")

        # Clean up linked orders tracking
        if not epic:
            self._linked_orders.clear()

        logger.info(f"Cancelled {cancelled} orders" + (f" for {epic}" if epic else ""))
        return cancelled

    def fetch_open_orders(self, epic: str = None) -> list:
        """Fetch open orders with fill detection info."""
        self._rate_limit()
        if epic:
            symbol = _to_symbol(epic)
            orders = self.exchange.fetch_open_orders(symbol)
        else:
            orders = self.exchange.fetch_open_orders()

        return [{
            "id": o.get("id"),
            "epic": _to_epic(o.get("symbol", "")),
            "side": "BUY" if o.get("side") == "buy" else "SELL",
            "type": o.get("type", ""),
            "price": float(o.get("price", 0) or 0),
            "amount": float(o.get("amount", 0)),
            "filled": float(o.get("filled", 0)),
            "remaining": float(o.get("remaining", 0)),
            "status": o.get("status", ""),
            "timestamp": o.get("timestamp"),
            "datetime": o.get("datetime", ""),
        } for o in orders]

    # ── Deal confirmation ─────────────────────────────────────────

    def get_deal_confirmation(self, deal_reference: str) -> dict:
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
                "level": float(order.get("average", order.get("price", 0)) or 0),
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
