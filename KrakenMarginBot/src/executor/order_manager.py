"""
Order Manager — Multi-order tracking for Grid bot.

Handles: batch order placement, fill detection, order lifecycle.
Grid bot needs to track 10-20 limit orders simultaneously.
"""

import logging
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

        # Track all managed orders
        # {order_id: {"epic", "side", "level", "size", "type", "status", "filled", "placed_at"}}
        self._orders = {}
        self._fill_callbacks = []  # [(callback_fn, filter_epic)]

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
                self._orders[order_id] = {
                    "epic": epic,
                    "side": result["side"],
                    "level": result["level"],
                    "size": result.get("size", size_per_level or 0),
                    "type": "grid",
                    "status": "open",
                    "filled": 0,
                    "placed_at": datetime.now().isoformat(),
                }
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
                        info = self._orders[order_id]
                        fill_price = o.get("average", o.get("price", info["level"]))
                        fills.append({
                            "order_id": order_id,
                            "epic": info["epic"],
                            "side": info["side"],
                            "level": info["level"],
                            "size": filled_amount - prev_filled,  # Incremental fill
                            "filled_size": filled_amount,
                            "original_size": info["size"],
                            "fill_price": fill_price,
                            "partial": True,
                        })
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
                            fills.append({
                                "order_id": order_id,
                                "epic": info["epic"],
                                "side": info["side"],
                                "level": info["level"],
                                "size": filled_size,
                                "filled_size": filled_size,
                                "original_size": info["size"],
                                "fill_price": fill_price,
                                "partial": filled_size < info["size"],
                            })
                            self._orders[order_id]["status"] = "filled"
                            self._orders[order_id]["filled"] = filled_size
                            logger.info(
                                f"[ORDER] Grid fill: {info['side']} {info['epic']} "
                                f"{filled_size}/{info['size']} @ {fill_price}"
                            )
                        else:
                            self._orders[order_id]["status"] = "cancelled"
                    except Exception as e:
                        logger.debug(f"Could not confirm order {order_id}: {e}")
                        self._orders[order_id]["status"] = "unknown"

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

        # Update internal tracking
        for order_id, info in self._orders.items():
            if epic is None or info["epic"] == epic:
                info["status"] = "cancelled"

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
            if info["status"] in ("filled", "cancelled", "unknown"):
                try:
                    placed = datetime.fromisoformat(info["placed_at"])
                    if (now - placed).total_seconds() > max_age_hours * 3600:
                        to_remove.append(order_id)
                except (ValueError, KeyError):
                    to_remove.append(order_id)

        for order_id in to_remove:
            del self._orders[order_id]

        if to_remove:
            logger.info(f"[ORDER] Cleaned up {len(to_remove)} old orders")
