import logging
import sqlite3
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class TradeExecutor:
    """Executes trades and logs them to SQLite database."""

    def __init__(self, client, risk_manager, config):
        self.client = client
        self.risk = risk_manager
        self.config = config

        # Local tracking to prevent duplicate trades (API has delay)
        self._recently_traded = {}  # {epic: timestamp}
        self._trade_cooldown = 300  # 5 minutes cooldown per coin

        self.db_path = config.get("database", {}).get("path", "data/trades.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_db(self):
        """Get a thread-safe database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Create trades table if it doesn't exist."""
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
                signal_details TEXT
            )
        """)
        db.commit()
        db.close()

    def execute_trade(self, epic, signal, signal_details, current_price):
        """Execute a BUY or SELL trade with risk management."""
        # Check local cooldown first (prevents rapid-fire duplicates)
        now = datetime.now()
        if epic in self._recently_traded:
            last_trade = self._recently_traded[epic]
            seconds_ago = (now - last_trade).total_seconds()
            if seconds_ago < self._trade_cooldown:
                remaining = int(self._trade_cooldown - seconds_ago)
                return None, f"Cooldown aktiv for {epic} ({remaining}s tilbage)"

        # Check if we can open a new position
        positions = self.client.get_positions()
        open_count = len(positions.get("positions", []))
        balance_info = self.client.get_account_balance()
        current_balance = balance_info["balance"]

        can_trade, reason = self.risk.can_open_position(open_count, current_balance, current_balance)
        if not can_trade:
            logger.warning(f"Cannot open position: {reason}")
            return None, reason

        # Check if we already have a position in this epic (API check)
        for pos in positions.get("positions", []):
            if pos["market"]["epic"] == epic:
                logger.info(f"Already have position in {epic}, skipping")
                self._recently_traded[epic] = now  # also set cooldown
                return None, f"Allerede en åben position i {epic}"

        # Calculate position size and risk levels
        size = self.risk.calculate_position_size(current_balance, current_price)
        stop_loss = self.risk.calculate_stop_loss(current_price, signal)
        take_profit = self.risk.calculate_take_profit(current_price, signal)

        # Execute the trade
        try:
            result = self.client.create_position(
                epic=epic,
                direction=signal,
                size=size,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            deal_id = result.get("dealReference", "unknown")

            # Log to database
            db = self._get_db()
            db.execute("""
                INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                                    stop_loss, take_profit, deal_id, status, signal_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
            """, (
                datetime.now().isoformat(),
                epic,
                signal,
                size,
                current_price,
                stop_loss,
                take_profit,
                deal_id,
                str(signal_details),
            ))
            db.commit()
            db.close()

            logger.info(f"Trade executed: {signal} {epic} x{size} @ {current_price} | SL: {stop_loss} | TP: {take_profit}")
            # Mark as recently traded to prevent duplicates
            self._recently_traded[epic] = datetime.now()
            return result, None

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            # Also set cooldown on failure to prevent spam
            self._recently_traded[epic] = datetime.now()
            return None, str(e)

    def _log_trade(self, epic, signal, size, price, stop_loss, take_profit, result, details):
        """Log a trade to the database."""
        deal_id = result.get("dealReference", "unknown")
        db = self._get_db()
        db.execute("""
            INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                                stop_loss, take_profit, deal_id, status, signal_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (
            datetime.now().isoformat(),
            epic,
            signal,
            size,
            price,
            stop_loss,
            take_profit,
            deal_id,
            str(details),
        ))
        db.commit()
        db.close()
        logger.info(f"Trade logged: {signal} {epic} x{size} @ {price}")

    def check_trailing_stops(self):
        """Check and update trailing stops for open positions."""
        positions = self.client.get_positions()

        for pos in positions.get("positions", []):
            deal_id = pos["position"]["dealId"]
            direction = pos["position"]["direction"]
            entry_price = pos["position"]["level"]
            current_price = pos["market"]["bid"] if direction == "BUY" else pos["market"]["offer"]

            if self.risk.should_move_trailing_stop(entry_price, current_price, direction):
                # Move stop-loss to break-even
                try:
                    self.client.update_position(deal_id, stop_loss=entry_price)
                    logger.info(f"Trailing stop moved to break-even for {deal_id} ({pos['market']['epic']})")
                except Exception as e:
                    logger.warning(f"Failed to update trailing stop: {e}")

    def close_all_positions(self, reason="Manual close"):
        """Emergency: close all open positions."""
        positions = self.client.get_positions()
        closed = 0

        for pos in positions.get("positions", []):
            deal_id = pos["position"]["dealId"]
            direction = pos["position"]["direction"]
            size = pos["position"]["size"]
            try:
                self.client.close_position(deal_id, direction=direction, size=size)
                closed += 1
                logger.info(f"Closed position {deal_id}: {reason}")
            except Exception as e:
                logger.error(f"Failed to close {deal_id}: {e}")

        return closed

    def get_trade_history(self, limit=50):
        """Get recent trades from the database."""
        db = self._get_db()
        cursor = db.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        db.close()
        return results

    def get_stats(self):
        """Get trading statistics."""
        db = self._get_db()
        cursor = db.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN profit_loss = 0 OR profit_loss IS NULL THEN 1 ELSE 0 END) as open_or_even,
                COALESCE(SUM(profit_loss), 0) as total_pl,
                COALESCE(AVG(profit_loss), 0) as avg_pl
            FROM trades
        """)
        row = cursor.fetchone()
        db.close()
        return {
            "total_trades": row[0],
            "wins": row[1] or 0,
            "losses": row[2] or 0,
            "open_or_even": row[3] or 0,
            "total_pl": round(row[4], 2),
            "avg_pl": round(row[5], 2),
            "win_rate": round((row[1] or 0) / max(row[0], 1) * 100, 1),
        }
