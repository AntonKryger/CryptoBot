"""
Trade Executor for KrakenBots — handles order execution and SQLite logging.

Adapted for spot trading with position tracker integration.
"""

import json
import logging
import sqlite3
import os
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)


def _safe_json(obj):
    try:
        return json.dumps(obj, default=_numpy_encoder)
    except (TypeError, ValueError):
        return str(obj)


def _numpy_encoder(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o)} is not JSON serializable")


class TradeExecutor:
    """Executes trades and logs them to SQLite database."""

    def __init__(self, client, risk_manager, config):
        self.client = client
        self.risk = risk_manager
        self.config = config

        self._recently_traded = {}
        self._trade_cooldown = config.get("trading", {}).get("trade_cooldown", 300)

        # Spread/slippage guard (ChatGPT: check spread before executing)
        exec_cfg = config.get("execution", {})
        self.max_spread_pct = exec_cfg.get("max_spread_pct", 0.15)  # Default fallback
        self.use_limit_orders = exec_cfg.get("use_limit_orders", False)  # Aggressive limit instead of market
        self.limit_offset_pct = exec_cfg.get("limit_offset_pct", 0.01)  # Limit price offset

        # Strategy-specific spread limits (override max_spread_pct per strategy type)
        self.strategy_spread_limits = exec_cfg.get("strategy_spread_limits", {
            "grid": 0.15,           # Tight — grid profits are small
            "mean_reversion": 0.30,
            "trend": 0.50,          # Loose — trend profits absorb spread
            "volatility": 0.50,     # Loose — volatility events have wide spreads
        })

        # Liquidity guard: require orderbook depth >= position_size * multiplier
        self.liquidity_check = exec_cfg.get("liquidity_check", True)
        self.liquidity_multiplier = exec_cfg.get("liquidity_multiplier", 5.0)
        self.liquidity_depth_pct = exec_cfg.get("liquidity_depth_pct", 0.3)  # Sum within 0.3% of mid
        self.liquidity_fail_reduce = exec_cfg.get("liquidity_fail_reduce", 0.5)  # Reduce size by 50% on API fail

        # Order slicing: split large orders into chunks to reduce market impact
        self.slice_enabled = exec_cfg.get("order_slicing", False)
        self.slice_max_pct = exec_cfg.get("slice_max_pct", 0.25)  # Max 25% of orderbook depth per slice
        self.slice_delay_ms = exec_cfg.get("slice_delay_ms", 500)  # Delay between slices

        self.db_path = config.get("database", {}).get("path", "data/trades.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        db = self._get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                epic TEXT NOT NULL,
                direction TEXT NOT NULL,
                size REAL NOT NULL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                deal_id TEXT,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL,
                exit_timestamp TEXT,
                profit_loss REAL,
                signal_details TEXT,
                balance_after REAL,
                source TEXT DEFAULT 'bot',
                exit_reason TEXT,
                strategy_type TEXT,
                account_snapshot TEXT,
                risk_snapshot TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                balance REAL NOT NULL,
                available REAL,
                profit_loss REAL,
                bot_name TEXT DEFAULT 'kraken'
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS circuit_breaker_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                epic TEXT NOT NULL,
                move_pct REAL NOT NULL,
                tier_threshold REAL NOT NULL,
                pause_minutes INTEGER NOT NULL,
                bot_name TEXT
            )
        """)
        db.commit()
        db.close()

    def execute_signal(self, signal: dict, balance_info: dict, open_count: int) -> tuple:
        """Execute a trade from a strategy signal.

        Args:
            signal: Dict from strategy.scan() with direction, epic, stop_loss, etc.
            balance_info: Current account balance dict
            open_count: Number of currently open positions

        Returns:
            (result, error_msg) — result is None on failure
        """
        epic = signal["epic"]
        direction = signal["direction"]

        # Skip non-tradeable signals (e.g., GRID_SETUP handled separately)
        if direction not in ("BUY", "SELL"):
            return None, f"Non-tradeable direction: {direction}"

        # Check cooldown
        now = datetime.now()
        if epic in self._recently_traded:
            elapsed = (now - self._recently_traded[epic]).total_seconds()
            if elapsed < self._trade_cooldown:
                return None, f"Cooldown active ({int(self._trade_cooldown - elapsed)}s remaining)"

        # Check risk limits
        current_balance = balance_info.get("balance", 0)
        can_trade, reason = self.risk.can_open_position(open_count, current_balance, current_balance)
        if not can_trade:
            return None, reason

        entry_price = signal["entry_price"]
        stop_loss = signal.get("stop_loss")
        take_profit = signal.get("take_profit")
        confidence = signal.get("confidence", 5)
        strategy_type = signal.get("signal_type", "unknown")

        # Spread/slippage guard: check spread before executing (strategy-specific limits)
        effective_spread_limit = self.strategy_spread_limits.get(strategy_type, self.max_spread_pct)
        _orderbook_cache = None  # Cache for liquidity check after size calculation
        _orderbook_failed = False  # Track if orderbook fetch failed
        try:
            orderbook = self.client.fetch_order_book(epic, limit=20)
            if orderbook and orderbook.get("bids") and orderbook.get("asks"):
                best_bid = orderbook["bids"][0][0]
                best_ask = orderbook["asks"][0][0]
                mid_price = (best_bid + best_ask) / 2
                spread_pct = (best_ask - best_bid) / mid_price * 100 if mid_price > 0 else 0
                if spread_pct > effective_spread_limit:
                    return None, (f"Spread too wide: {spread_pct:.3f}% > {effective_spread_limit}% "
                                  f"({strategy_type}) — delaying trade")
                _orderbook_cache = orderbook  # Save for liquidity check
            else:
                _orderbook_failed = True
                logger.warning(f"Orderbook empty for {epic} — proceeding with reduced size (soft fallback)")
        except Exception as e:
            _orderbook_failed = True
            logger.warning(f"Orderbook fetch failed for {epic}: {e} — proceeding with reduced size (soft fallback)")

        # Calculate size if not provided by strategy
        size = signal.get("size")
        if size is None:
            allocations = self.risk.allocate_capital(
                [(epic, direction, confidence, signal.get("details", {}))],
                balance_info.get("available", current_balance)
            )
            if not allocations:
                return None, "Capital allocation rejected"
            _, _, allocated_amount, _ = allocations[0]
            size = self.risk.calculate_position_size(allocated_amount, entry_price)

        # Soft fallback: reduce size if orderbook fetch failed (no liquidity data)
        if _orderbook_failed and self.liquidity_fail_reduce > 0 and size and size > 0:
            original_size = size
            size = size * self.liquidity_fail_reduce
            logger.warning(f"Size reduced {original_size:.6f} → {size:.6f} (orderbook unavailable, "
                           f"{self.liquidity_fail_reduce:.0%} fallback)")

        # Liquidity guard: check orderbook depth after size is known
        if self.liquidity_check and _orderbook_cache and size and size > 0:
            try:
                ob = _orderbook_cache
                best_bid = ob["bids"][0][0]
                best_ask = ob["asks"][0][0]
                mid_price = (best_bid + best_ask) / 2
                if mid_price > 0:
                    depth_range = mid_price * self.liquidity_depth_pct / 100
                    bid_depth = sum(
                        amount for price, amount in ob["bids"]
                        if price >= mid_price - depth_range
                    )
                    ask_depth = sum(
                        amount for price, amount in ob["asks"]
                        if price <= mid_price + depth_range
                    )
                    relevant_depth = bid_depth if direction == "BUY" else ask_depth
                    required_depth = size * self.liquidity_multiplier
                    if relevant_depth < required_depth:
                        return None, (f"Insufficient liquidity: {relevant_depth:.4f} < "
                                      f"{required_depth:.4f} (need {self.liquidity_multiplier}x size)")
            except Exception as e:
                logger.debug(f"Liquidity check skipped: {e}")

        # Execute — with optional order slicing for large trades
        try:
            # Determine if order should be sliced
            slices = self._calculate_slices(size, _orderbook_cache, direction)

            if len(slices) > 1:
                logger.info(f"Order slicing: {direction} {epic} x{size} → {len(slices)} slices")

            # Execute first (or only) slice with SL/TP
            result = self.client.create_position(
                epic=epic,
                direction=direction,
                size=slices[0],
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            # Execute remaining slices without SL/TP (will be managed by watchdog)
            if len(slices) > 1:
                import time as _time
                for i, slice_size in enumerate(slices[1:], 2):
                    _time.sleep(self.slice_delay_ms / 1000)
                    try:
                        self.client.create_position(
                            epic=epic, direction=direction, size=slice_size,
                        )
                        logger.info(f"Slice {i}/{len(slices)} filled: {slice_size}")
                    except Exception as e:
                        logger.warning(f"Slice {i}/{len(slices)} failed: {e} — {sum(slices[i-1:]):.6f} unfilled")
                        break

            deal_ref = result.get("dealReference", "unknown")
            fill_price = result.get("fillPrice", entry_price)

            # Log to database
            db = self._get_db()
            existing = db.execute("SELECT id FROM trades WHERE deal_id = ?", (deal_ref,)).fetchone()
            if not existing:
                db.execute("""
                    INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                                        stop_loss, take_profit, deal_id, status, signal_details,
                                        source, strategy_type, account_snapshot, risk_snapshot)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, 'bot', ?, ?, ?)
                """, (
                    now.isoformat(),
                    epic,
                    direction,
                    size,
                    fill_price,
                    stop_loss,
                    take_profit,
                    deal_ref,
                    _safe_json(signal.get("details", {})),
                    strategy_type,
                    _safe_json({"balance": current_balance, "open_positions": open_count}),
                    _safe_json({"confidence": confidence, "reasons": signal.get("reasons", [])}),
                ))
                db.commit()
            db.close()

            self._recently_traded[epic] = now
            logger.info(f"Trade executed: {direction} {epic} x{size} @ {fill_price} | SL: {stop_loss} | TP: {take_profit}")
            return result, None

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            self._recently_traded[epic] = now
            return None, str(e)

    def _calculate_slices(self, total_size: float, orderbook: dict, direction: str) -> list:
        """Split order into slices based on orderbook depth.

        Returns list of sizes. Single-element list = no slicing needed.
        """
        if not self.slice_enabled or not orderbook or total_size <= 0:
            return [total_size]

        try:
            # Calculate available depth on the relevant side
            if direction == "BUY":
                depth = sum(amount for _, amount in orderbook.get("asks", []))
            else:
                depth = sum(amount for _, amount in orderbook.get("bids", []))

            if depth <= 0:
                return [total_size]

            # Max slice = slice_max_pct of visible depth
            max_slice = depth * self.slice_max_pct

            if total_size <= max_slice:
                return [total_size]  # Small enough — no slicing needed

            # Split into roughly equal chunks, each <= max_slice
            import math
            n_slices = math.ceil(total_size / max_slice)
            n_slices = min(n_slices, 4)  # Cap at 4 slices to limit complexity
            slice_size = total_size / n_slices

            slices = [round(slice_size, 8)] * (n_slices - 1)
            slices.append(round(total_size - sum(slices), 8))  # Last slice gets remainder
            return slices

        except Exception as e:
            logger.debug(f"Slice calculation failed: {e}")
            return [total_size]

    def update_trade_close(self, deal_id, exit_price, profit_loss, epic=None, exit_reason=None):
        """Update trade record when position is closed."""
        try:
            db = self._get_db()
            exit_ts = datetime.now().isoformat()
            rows = db.execute(
                "UPDATE trades SET exit_price = ?, exit_timestamp = ?, profit_loss = ?, "
                "status = 'CLOSED', exit_reason = COALESCE(?, exit_reason) "
                "WHERE deal_id = ? AND status = 'OPEN'",
                (exit_price, exit_ts, profit_loss, exit_reason, deal_id)
            ).rowcount

            if rows == 0 and epic:
                cursor = db.execute(
                    "SELECT id FROM trades WHERE epic = ? AND status = 'OPEN' "
                    "ORDER BY timestamp DESC LIMIT 1", (epic,)
                )
                row = cursor.fetchone()
                if row:
                    db.execute(
                        "UPDATE trades SET exit_price = ?, exit_timestamp = ?, profit_loss = ?, "
                        "status = 'CLOSED', exit_reason = COALESCE(?, exit_reason) WHERE id = ?",
                        (exit_price, exit_ts, profit_loss, exit_reason, row[0])
                    )

            db.commit()
            db.close()
            logger.info(f"Trade closed: {deal_id} exit={exit_price} P/L=${profit_loss:.2f} reason={exit_reason}")
        except Exception as e:
            logger.error(f"Failed to update trade close: {e}")

    def log_circuit_breaker(self, epic: str, move_pct: float, tier_threshold: float,
                               pause_minutes: int, bot_name: str = "kraken"):
        """Log a circuit breaker trigger event to SQLite."""
        try:
            db = self._get_db()
            db.execute("""
                INSERT INTO circuit_breaker_events (timestamp, epic, move_pct, tier_threshold, pause_minutes, bot_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), epic, round(move_pct, 2), tier_threshold, pause_minutes, bot_name))
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Circuit breaker log failed: {e}")

    def get_circuit_breaker_stats(self, hours: int = 24) -> dict:
        """Get circuit breaker trigger stats for the last N hours."""
        try:
            db = self._get_db()
            cutoff = datetime.now().isoformat()[:10]  # Simple date cutoff
            cursor = db.execute("""
                SELECT epic, tier_threshold, COUNT(*) as triggers
                FROM circuit_breaker_events
                WHERE timestamp > datetime('now', ?)
                GROUP BY epic, tier_threshold
                ORDER BY triggers DESC
            """, (f"-{hours} hours",))
            results = [{"epic": r[0], "tier": r[1], "triggers": r[2]} for r in cursor.fetchall()]
            db.close()
            return {"events": results, "hours": hours}
        except Exception as e:
            logger.error(f"Circuit breaker stats failed: {e}")
            return {"events": [], "hours": hours}

    def snapshot_balance(self, balance_data, bot_name="kraken"):
        try:
            db = self._get_db()
            db.execute("""
                INSERT INTO balance_snapshots (timestamp, balance, available, profit_loss, bot_name)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                balance_data.get("balance", 0),
                balance_data.get("available", 0),
                balance_data.get("profit_loss", 0),
                bot_name,
            ))
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Balance snapshot failed: {e}")

    def get_trade_history(self, limit=50):
        db = self._get_db()
        cursor = db.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        db.close()
        return results

    def get_stats(self):
        db = self._get_db()
        cursor = db.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(profit_loss), 0) as total_pl,
                COALESCE(AVG(profit_loss), 0) as avg_pl
            FROM trades WHERE status = 'CLOSED'
        """)
        row = cursor.fetchone()
        db.close()
        return {
            "total_trades": row[0],
            "wins": row[1] or 0,
            "losses": row[2] or 0,
            "total_pl": round(row[3], 2),
            "avg_pl": round(row[4], 2),
            "win_rate": round((row[1] or 0) / max(row[0], 1) * 100, 1),
        }
