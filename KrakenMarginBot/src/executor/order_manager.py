"""
Order Manager — Multi-order tracking for Grid bot.

Handles: batch order placement, fill detection, order lifecycle.
Grid bot needs to track 10-20 limit orders simultaneously.
Orders are persisted to SQLite so fills can be detected after restart.
"""

import logging
import sqlite3
import os
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages multiple orders for strategies that use limit orders (Grid, etc)."""

    def __init__(self, client, config):
        self.client = client
        self.check_interval = config.get("trading", {}).get("order_check_interval", 30)

        # Order timeout: auto-cancel limit orders older than this (minutes)
        self.order_timeout_minutes = config.get("execution", {}).get("order_timeout_minutes", 60)

        # Position tracker reference (set externally after init)
        self.position_tracker = None

        # Track all managed orders (also backed by SQLite)
        # {order_id: {"epic", "side", "level", "size", "type", "status", "filled", "placed_at"}}
        self._orders = {}
        self._fill_callbacks = []  # [(callback_fn, filter_epic)]

        # SQLite persistence for orders
        self._db_path = config.get("database", {}).get("path", "data/trades.db")
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._init_db()
        self._load_orders_from_db()

    def _get_db(self):
        return sqlite3.connect(self._db_path)

    def _init_db(self):
        db = self._get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS managed_orders (
                order_id TEXT PRIMARY KEY,
                epic TEXT NOT NULL,
                side TEXT NOT NULL,
                level REAL NOT NULL,
                size REAL NOT NULL,
                type TEXT DEFAULT 'grid',
                status TEXT DEFAULT 'open',
                filled REAL DEFAULT 0,
                placed_at TEXT NOT NULL
            )
        """)
        db.commit()
        db.close()

    def _load_orders_from_db(self):
        """Load open orders from SQLite at startup."""
        db = self._get_db()
        cursor = db.execute(
            "SELECT order_id, epic, side, level, size, type, status, filled, placed_at "
            "FROM managed_orders WHERE status = 'open'"
        )
        loaded = 0
        for row in cursor.fetchall():
            self._orders[row[0]] = {
                "epic": row[1], "side": row[2], "level": row[3],
                "size": row[4], "type": row[5], "status": row[6],
                "filled": row[7], "placed_at": row[8],
            }
            loaded += 1
        db.close()
        if loaded > 0:
            logger.info(f"[ORDER] Loaded {loaded} open orders from DB")

    def _save_order_to_db(self, order_id: str, info: dict):
        """Persist a single order to SQLite."""
        db = self._get_db()
        try:
            db.execute("""
                INSERT OR REPLACE INTO managed_orders
                    (order_id, epic, side, level, size, type, status, filled, placed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (order_id, info["epic"], info["side"], info["level"],
                  info["size"], info.get("type", "grid"), info["status"],
                  info.get("filled", 0), info["placed_at"]))
            db.commit()
        except Exception as e:
            logger.error(f"[ORDER] DB save failed for {order_id}: {e}")
        finally:
            db.close()

    def _update_order_status_db(self, order_id: str, status: str, filled: float = None):
        """Update order status in SQLite."""
        db = self._get_db()
        try:
            if filled is not None:
                db.execute(
                    "UPDATE managed_orders SET status = ?, filled = ? WHERE order_id = ?",
                    (status, filled, order_id))
            else:
                db.execute(
                    "UPDATE managed_orders SET status = ? WHERE order_id = ?",
                    (status, order_id))
            db.commit()
        except Exception as e:
            logger.error(f"[ORDER] DB status update failed for {order_id}: {e}")
        finally:
            db.close()

    def place_grid_orders(self, epic: str, grid_levels: list, size_per_level: float = None) -> int:
        """Place a batch of grid limit orders.

        Args:
            epic: Trading pair
            grid_levels: List of {"level": float, "side": "BUY"|"SELL", "size": float (optional)}
            size_per_level: Default size (used if level has no "size" key)

        Returns: Number of orders successfully placed
        """
        orders_to_place = []
        for gl in grid_levels:
            level_size = gl.get("size", size_per_level or 0)
            if level_size <= 0:
                continue
            orders_to_place.append({
                "epic": epic,
                "direction": gl["side"],
                "size": level_size,
                "level": gl["level"],
                "type": "limit",
            })

        results = self.client.create_batch_orders(orders_to_place)

        placed = 0
        for result in results:
            if result.get("success"):
                order_id = result["order_id"]
                info = {
                    "epic": epic,
                    "side": result["side"],
                    "level": result["level"],
                    "size": result.get("size", size_per_level or 0),
                    "type": "grid",
                    "status": "open",
                    "filled": 0,
                    "placed_at": datetime.now().isoformat(),
                }
                self._orders[order_id] = info
                self._save_order_to_db(order_id, info)
                placed += 1
            else:
                logger.warning(f"Grid order failed: {result.get('error')}")

        logger.info(f"[ORDER] Placed {placed}/{len(grid_levels)} grid orders for {epic}")
        return placed

    def check_fills(self) -> list:
        """Check for filled orders. Returns list of fill events.

        Each fill: {"order_id", "epic", "side", "level", "size", "filled_size", "original_size", "fill_price", "partial"}
        """
        if not self._orders:
            return []

        # Cancel stale orders first
        self._cancel_stale_orders()

        fills = []
        try:
            open_orders = self.client.fetch_open_orders()
            open_ids = {o["id"] for o in open_orders}

            # Check for partial fills on still-open orders
            for o in open_orders:
                order_id = o["id"]
                if order_id in self._orders and self._orders[order_id]["status"] == "open":
                    filled_amount = o.get("filled", 0)
                    prev_filled = self._orders[order_id].get("filled", 0)
                    if filled_amount > prev_filled:
                        # Partial fill detected
                        self._orders[order_id]["filled"] = filled_amount
                        self._update_order_status_db(order_id, "open", filled_amount)
                        info = self._orders[order_id]
                        fill_price = o.get("average", o.get("price", info["level"]))
                        fill_event = {
                            "order_id": order_id,
                            "epic": info["epic"],
                            "side": info["side"],
                            "level": info["level"],
                            "size": filled_amount - prev_filled,  # Incremental fill
                            "filled_size": filled_amount,
                            "original_size": info["size"],
                            "fill_price": fill_price,
                            "partial": True,
                        }
                        fills.append(fill_event)
                        self._record_fill_position(fill_event)
                        logger.info(
                            f"[ORDER] Partial fill: {info['side']} {info['epic']} "
                            f"{filled_amount}/{info['size']} @ {fill_price}"
                        )

            # Orders that were tracked but are no longer open = fully filled or cancelled
            for order_id, info in list(self._orders.items()):
                if info["status"] != "open":
                    continue

                if order_id not in open_ids:
                    # Order is no longer open — check if filled
                    try:
                        confirm = self.client.get_deal_confirmation(order_id)
                        if confirm.get("dealStatus") == "ACCEPTED":
                            fill_price = confirm.get("level", info["level"])
                            filled_size = confirm.get("size", confirm.get("filled", info["size"]))
                            fill_event = {
                                "order_id": order_id,
                                "epic": info["epic"],
                                "side": info["side"],
                                "level": info["level"],
                                "size": filled_size,
                                "filled_size": filled_size,
                                "original_size": info["size"],
                                "fill_price": fill_price,
                                "partial": filled_size < info["size"],
                            }
                            fills.append(fill_event)
                            self._orders[order_id]["status"] = "filled"
                            self._orders[order_id]["filled"] = filled_size
                            self._update_order_status_db(order_id, "filled", filled_size)
                            self._record_fill_position(fill_event)
                            logger.info(
                                f"[ORDER] Grid fill: {info['side']} {info['epic']} "
                                f"{filled_size}/{info['size']} @ {fill_price}"
                            )
                        else:
                            self._orders[order_id]["status"] = "cancelled"
                            self._update_order_status_db(order_id, "cancelled")
                    except Exception as e:
                        logger.debug(f"Could not confirm order {order_id}: {e}")
                        self._orders[order_id]["status"] = "unknown"
                        self._update_order_status_db(order_id, "unknown")

        except Exception as e:
            logger.error(f"Order fill check failed: {e}")

        # Notify callbacks
        for fill in fills:
            for callback, filter_epic in self._fill_callbacks:
                if filter_epic is None or filter_epic == fill["epic"]:
                    try:
                        callback(fill)
                    except Exception as e:
                        logger.error(f"Fill callback error: {e}")

        return fills

    def _record_fill_position(self, fill_event: dict):
        """Record a grid fill in position tracker so it survives restarts."""
        if not self.position_tracker:
            return
        try:
            self.position_tracker.open_position(
                deal_id=fill_event["order_id"],
                epic=fill_event["epic"],
                direction=fill_event["side"],
                size=fill_event["filled_size"],
                entry_price=fill_event["fill_price"],
                strategy_type="grid",
            )
        except Exception as e:
            logger.error(f"[ORDER] Failed to record fill in position tracker: {e}")

    def _cancel_stale_orders(self):
        """Auto-cancel limit orders that haven't filled within timeout."""
        if self.order_timeout_minutes <= 0:
            return

        now = datetime.now()
        stale_ids = []

        for order_id, info in self._orders.items():
            if info["status"] != "open":
                continue
            try:
                placed = datetime.fromisoformat(info["placed_at"])
                age_seconds = (now - placed).total_seconds()
                if age_seconds > self.order_timeout_minutes * 60:
                    stale_ids.append(order_id)
            except (ValueError, KeyError):
                continue

        for order_id in stale_ids:
            try:
                self.client.cancel_order(order_id)
                self._orders[order_id]["status"] = "timeout"
                self._update_order_status_db(order_id, "timeout")
                info = self._orders[order_id]
                logger.warning(
                    f"[ORDER] Timeout: cancelled {info['side']} {info['epic']} @ {info['level']} "
                    f"(open {self.order_timeout_minutes}min)"
                )
            except Exception as e:
                logger.error(f"Failed to cancel stale order {order_id}: {e}")

    def on_fill(self, callback, epic: str = None):
        """Register a callback for order fills. Optional epic filter."""
        self._fill_callbacks.append((callback, epic))

    def cancel_all(self, epic: str = None) -> int:
        """Cancel all managed orders, optionally for a specific epic."""
        cancelled = self.client.cancel_all_orders(epic)

        # Update internal tracking + DB
        for order_id, info in self._orders.items():
            if epic is None or info["epic"] == epic:
                info["status"] = "cancelled"
                self._update_order_status_db(order_id, "cancelled")

        return cancelled

    def get_open_orders(self, epic: str = None) -> list:
        """Get currently tracked open orders."""
        result = []
        for order_id, info in self._orders.items():
            if info["status"] != "open":
                continue
            if epic and info["epic"] != epic:
                continue
            result.append({"order_id": order_id, **info})
        return result

    def get_stats(self) -> dict:
        """Get order manager statistics."""
        total = len(self._orders)
        by_status = {}
        for info in self._orders.values():
            status = info["status"]
            by_status[status] = by_status.get(status, 0) + 1
        return {"total": total, "by_status": by_status}

    def cleanup_old_orders(self, max_age_hours: int = 24):
        """Remove old filled/cancelled orders from tracking."""
        now = datetime.now()
        to_remove = []
        for order_id, info in self._orders.items():
            if info["status"] in ("filled", "cancelled", "unknown", "timeout"):
                try:
                    placed = datetime.fromisoformat(info["placed_at"])
                    if (now - placed).total_seconds() > max_age_hours * 3600:
                        to_remove.append(order_id)
                except (ValueError, KeyError):
                    to_remove.append(order_id)

        for order_id in to_remove:
            del self._orders[order_id]

        # Clean DB too
        if to_remove:
            db = self._get_db()
            try:
                db.execute(
                    f"DELETE FROM managed_orders WHERE status IN ('filled','cancelled','unknown','timeout') "
                    f"AND placed_at < datetime('now', '-{max_age_hours} hours')"
                )
                db.commit()
            except Exception as e:
                logger.error(f"[ORDER] DB cleanup failed: {e}")
            finally:
                db.close()
            logger.info(f"[ORDER] Cleaned up {len(to_remove)} old orders")
