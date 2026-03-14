"""
Real-time portfolio sync from Capital.com API.
Maintains open_positions table in SQLite and provides
portfolio snapshot for AI decision-making.
"""

import logging
import sqlite3
import os
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionSync:
    """Syncs open positions from Capital.com to SQLite and provides portfolio context."""

    def __init__(self, client, config):
        self.client = client
        self.db_path = config.get("database", {}).get("path", "data_ai/trades.db")
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        self._lock = threading.Lock()
        self._last_sync = 0
        self._sync_interval = 30  # seconds
        self._running = False

        # Cached snapshot (updated on every sync)
        self._portfolio = {
            "positions": [],
            "balance": 0,
            "available": 0,
            "unrealized_pnl": 0,
            "margin_used": 0,
            "open_count": 0,
            "last_sync": None,
        }

        self._init_db()

    def _init_db(self):
        """Create open_positions table."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS open_positions (
                    position_id TEXT PRIMARY KEY,
                    epic TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL,
                    size REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    unrealized_pnl REAL,
                    margin REAL,
                    opened_at TEXT,
                    last_synced TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
            logger.info("[PositionSync] Table initialized")
        except Exception as e:
            logger.error(f"[PositionSync] DB init error: {e}")

    def sync(self):
        """Fetch positions + balance from Capital.com and update SQLite + cache."""
        with self._lock:
            try:
                # Fetch positions from API
                positions_resp = self.client.get_positions()
                api_positions = positions_resp.get("positions", [])

                # Fetch balance
                balance_data = self.client.get_account_balance()

                now = datetime.now().isoformat()
                synced_positions = []

                conn = sqlite3.connect(self.db_path)

                # Clear all existing positions (full refresh)
                conn.execute("DELETE FROM open_positions")

                total_unrealized = 0
                total_margin = 0

                for pos in api_positions:
                    p = pos.get("position", {})
                    m = pos.get("market", {})

                    deal_id = p.get("dealId", "")
                    epic = m.get("epic", "")
                    direction = p.get("direction", "")
                    entry_price = p.get("level", 0)
                    size = p.get("size", 0)
                    stop_loss = p.get("stopLevel")
                    take_profit = p.get("profitLevel")
                    created = p.get("createdDateUTC", "")

                    # Current price depends on direction
                    if direction == "BUY":
                        current_price = m.get("bid", entry_price)
                    else:
                        current_price = m.get("offer", entry_price)

                    # Calculate unrealized P/L
                    if direction == "BUY":
                        unrealized = (current_price - entry_price) * size
                    else:
                        unrealized = (entry_price - current_price) * size

                    # Margin (from API if available, else estimate)
                    margin = p.get("margin", 0) or 0

                    total_unrealized += unrealized
                    total_margin += margin

                    conn.execute("""
                        INSERT OR REPLACE INTO open_positions
                        (position_id, epic, direction, entry_price, current_price,
                         size, stop_loss, take_profit, unrealized_pnl, margin,
                         opened_at, last_synced)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        deal_id, epic, direction, entry_price, current_price,
                        size, stop_loss, take_profit, round(unrealized, 2), margin,
                        created, now,
                    ))

                    synced_positions.append({
                        "position_id": deal_id,
                        "epic": epic,
                        "direction": direction,
                        "entry_price": entry_price,
                        "current_price": current_price,
                        "size": size,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "unrealized_pnl": round(unrealized, 2),
                        "margin": margin,
                        "opened_at": created,
                    })

                conn.commit()
                conn.close()

                # Update cached snapshot
                balance = balance_data.get("balance", 0) if balance_data else 0
                available = balance_data.get("available", 0) if balance_data else 0

                self._portfolio = {
                    "positions": synced_positions,
                    "balance": balance,
                    "available": available,
                    "unrealized_pnl": round(total_unrealized, 2),
                    "margin_used": round(total_margin, 2),
                    "open_count": len(synced_positions),
                    "last_sync": now,
                }

                self._last_sync = time.time()
                logger.debug(
                    f"[PositionSync] Synced {len(synced_positions)} positions | "
                    f"Balance: EUR {balance:.0f} | Available: EUR {available:.0f} | "
                    f"Unrealized: EUR {total_unrealized:+.2f}"
                )

            except Exception as e:
                logger.error(f"[PositionSync] Sync failed: {e}")

    def get_portfolio(self):
        """Get current portfolio snapshot. Auto-syncs if stale (>30s)."""
        if time.time() - self._last_sync > self._sync_interval:
            self.sync()
        return self._portfolio

    def format_for_prompt(self):
        """Format portfolio data for injection into AI prompts.
        This should be the FIRST section in every prompt.
        """
        p = self.get_portfolio()
        lines = [
            "=" * 50,
            "DIN AKTUELLE PORTEFØLJE (LIVE DATA):",
            f"Konto balance: EUR {p['balance']:.2f}",
            f"Tilgængelig kapital: EUR {p['available']:.2f}",
            f"Margin brugt: EUR {p['margin_used']:.2f}",
            f"Samlet urealiseret P/L: EUR {p['unrealized_pnl']:+.2f}",
            f"Åbne positioner: {p['open_count']}/3 (max 3)",
        ]

        if p["positions"]:
            lines.append("")
            lines.append("ÅBNE POSITIONER:")
            for pos in p["positions"]:
                direction_dk = "LONG" if pos["direction"] == "BUY" else "SHORT"
                pl_str = f"EUR {pos['unrealized_pnl']:+.2f}"

                # Calculate P/L percentage
                if pos["entry_price"] and pos["size"]:
                    notional = pos["entry_price"] * pos["size"]
                    pl_pct = (pos["unrealized_pnl"] / notional * 100) if notional else 0
                else:
                    pl_pct = 0

                sl_str = f"{pos['stop_loss']:.4f}" if pos["stop_loss"] else "INGEN"
                tp_str = f"{pos['take_profit']:.4f}" if pos["take_profit"] else "INGEN"

                lines.append(
                    f"  • {pos['epic']} {direction_dk} x{pos['size']} "
                    f"@ {pos['entry_price']:.4f} → {pos['current_price']:.4f} "
                    f"| P/L: {pl_str} ({pl_pct:+.2f}%)"
                )
                lines.append(f"    SL: {sl_str} | TP: {tp_str}")
        else:
            lines.append("")
            lines.append("INGEN ÅBNE POSITIONER — fuld kapital tilgængelig.")

        lines.append("=" * 50)
        return "\n".join(lines)

    def start_background_sync(self):
        """Start background thread that syncs every 30 seconds."""
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._sync_loop, daemon=True)
        t.start()
        logger.info(f"[PositionSync] Background sync started (every {self._sync_interval}s)")

    def stop(self):
        self._running = False

    def _sync_loop(self):
        """Background sync loop."""
        while self._running:
            try:
                self.sync()
            except Exception as e:
                logger.error(f"[PositionSync] Background sync error: {e}")
            time.sleep(self._sync_interval)
