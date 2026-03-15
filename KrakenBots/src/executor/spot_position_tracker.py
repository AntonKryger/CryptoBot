"""
Spot Position Tracker — Local SQLite-based position tracking for Kraken spot.

Kraken spot has no native "positions" concept (only order history).
This tracker maintains a local view of open/closed positions so the
bot system can work the same way as with Capital.com's position API.
"""

import logging
import sqlite3
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class SpotPositionTracker:
    """SQLite-backed position tracker for spot trading.

    Tracks: deal_id, epic, direction, size, entry_price, SL, TP, status.
    Provides get_positions() in adapter-compatible format.
    """

    def __init__(self, db_path: str = "data/positions.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        db = self._get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deal_id TEXT UNIQUE NOT NULL,
                epic TEXT NOT NULL,
                direction TEXT NOT NULL,
                size REAL NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                status TEXT DEFAULT 'OPEN',
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                exit_price REAL,
                profit_loss REAL,
                strategy_type TEXT,
                bot_id TEXT
            )
        """)
        db.commit()
        db.close()

    def open_position(self, deal_id: str, epic: str, direction: str, size: float,
                      entry_price: float, stop_loss: float = None,
                      take_profit: float = None, strategy_type: str = None,
                      bot_id: str = None):
        """Record a new open position."""
        db = self._get_db()
        try:
            db.execute("""
                INSERT INTO positions (deal_id, epic, direction, size, entry_price,
                                       stop_loss, take_profit, status, opened_at,
                                       strategy_type, bot_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
            """, (deal_id, epic, direction, size, entry_price, stop_loss, take_profit,
                  datetime.now().isoformat(), strategy_type, bot_id))
            db.commit()
            logger.info(f"[TRACKER] Opened: {direction} {epic} x{size} @ {entry_price} (id={deal_id})")
        except sqlite3.IntegrityError:
            logger.warning(f"[TRACKER] Position {deal_id} already exists")
        finally:
            db.close()

    def close_position(self, deal_id: str, exit_price: float, profit_loss: float = None):
        """Mark a position as closed."""
        db = self._get_db()

        if profit_loss is None:
            # Calculate P/L from entry/exit
            row = db.execute(
                "SELECT entry_price, direction, size FROM positions WHERE deal_id = ?",
                (deal_id,)
            ).fetchone()
            if row:
                entry_price, direction, size = row
                if direction == "BUY":
                    profit_loss = (exit_price - entry_price) * size
                else:
                    profit_loss = (entry_price - exit_price) * size

        db.execute("""
            UPDATE positions SET status = 'CLOSED', closed_at = ?, exit_price = ?, profit_loss = ?
            WHERE deal_id = ? AND status = 'OPEN'
        """, (datetime.now().isoformat(), exit_price, profit_loss, deal_id))
        db.commit()
        db.close()
        logger.info(f"[TRACKER] Closed: {deal_id} @ {exit_price}, P/L=${profit_loss:.2f}" if profit_loss else f"[TRACKER] Closed: {deal_id}")

    def update_sl_tp(self, deal_id: str, stop_loss: float = None, take_profit: float = None):
        """Update SL/TP for a position."""
        db = self._get_db()
        if stop_loss is not None:
            db.execute("UPDATE positions SET stop_loss = ? WHERE deal_id = ? AND status = 'OPEN'",
                       (stop_loss, deal_id))
        if take_profit is not None:
            db.execute("UPDATE positions SET take_profit = ? WHERE deal_id = ? AND status = 'OPEN'",
                       (take_profit, deal_id))
        db.commit()
        db.close()

    def get_position(self, deal_id: str) -> Optional[dict]:
        """Get a single position by deal_id."""
        db = self._get_db()
        row = db.execute(
            "SELECT deal_id, epic, direction, size, entry_price, stop_loss, take_profit, "
            "status, opened_at FROM positions WHERE deal_id = ?", (deal_id,)
        ).fetchone()
        db.close()
        if row:
            return {
                "deal_id": row[0], "epic": row[1], "direction": row[2],
                "size": row[3], "entry_price": row[4], "stop_loss": row[5],
                "take_profit": row[6], "status": row[7], "opened_at": row[8],
            }
        return None

    def get_open_positions(self) -> list:
        """Get all open positions."""
        db = self._get_db()
        cursor = db.execute(
            "SELECT deal_id, epic, direction, size, entry_price, stop_loss, take_profit, "
            "opened_at, strategy_type, bot_id FROM positions WHERE status = 'OPEN'"
        )
        positions = []
        for row in cursor.fetchall():
            positions.append({
                "deal_id": row[0], "epic": row[1], "direction": row[2],
                "size": row[3], "entry_price": row[4], "stop_loss": row[5],
                "take_profit": row[6], "opened_at": row[7],
                "strategy_type": row[8], "bot_id": row[9],
            })
        db.close()
        return positions

    def get_positions_for_adapter(self, adapter) -> dict:
        """Return positions in adapter-compatible format (same as Capital.com API).

        Fetches current market price from adapter for bid/offer.
        """
        open_positions = self.get_open_positions()
        result = []

        for pos in open_positions:
            # Get current price
            try:
                ticker = adapter.get_market_info(pos["epic"])
                bid = ticker.get("snapshot", {}).get("bid", pos["entry_price"])
                offer = ticker.get("snapshot", {}).get("offer", pos["entry_price"])
            except Exception:
                bid = offer = pos["entry_price"]

            result.append({
                "position": {
                    "dealId": pos["deal_id"],
                    "epic": pos["epic"],
                    "direction": pos["direction"],
                    "size": pos["size"],
                    "level": pos["entry_price"],
                    "stopLevel": pos["stop_loss"],
                    "profitLevel": pos["take_profit"],
                    "createdDateUTC": pos["opened_at"],
                },
                "market": {
                    "epic": pos["epic"],
                    "bid": bid,
                    "offer": offer,
                },
            })

        return {"positions": result}

    def get_open_count(self) -> int:
        db = self._get_db()
        row = db.execute("SELECT COUNT(*) FROM positions WHERE status = 'OPEN'").fetchone()
        db.close()
        return row[0] if row else 0

    def get_open_epics(self) -> set:
        db = self._get_db()
        cursor = db.execute("SELECT DISTINCT epic FROM positions WHERE status = 'OPEN'")
        epics = {row[0] for row in cursor.fetchall()}
        db.close()
        return epics
