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
        self._breakeven_done = set()  # deal_ids where break-even stop already set

        self.db_path = config.get("database", {}).get("path", "data/trades.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_db(self):
        """Get a thread-safe database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Create trades and balance_snapshots tables if they don't exist."""
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
        db.execute("""
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                balance REAL NOT NULL,
                available REAL,
                profit_loss REAL,
                bot_name TEXT DEFAULT 'rule'
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
        take_profit = self.risk.calculate_take_profit(current_price, signal, sl_price=stop_loss)

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

    def update_trade_close(self, deal_id, exit_price, profit_loss, partial=False):
        """Update a trade record when position is closed by watchdog."""
        try:
            db = self._get_db()
            if partial:
                # For partial closes, just log the P&L but keep status OPEN
                db.execute("""
                    UPDATE trades SET signal_details = signal_details || ' | partial_pl=' || ?
                    WHERE deal_id = ? AND status = 'OPEN'
                """, (str(round(profit_loss, 2)), deal_id))
            else:
                db.execute("""
                    UPDATE trades SET exit_price = ?, exit_timestamp = ?, profit_loss = ?, status = 'CLOSED'
                    WHERE deal_id = ? AND status = 'OPEN'
                """, (exit_price, datetime.now().isoformat(), profit_loss, deal_id))
            db.commit()
            db.close()
            action = "partial update" if partial else "closed"
            logger.info(f"Trade DB {action}: {deal_id} exit={exit_price} P/L={profit_loss:.2f}")
        except Exception as e:
            logger.error(f"Failed to update trade close in DB: {e}")

    def reconcile_closed_trades(self):
        """Background sync: find OPEN trades in DB that are actually closed on Capital.com."""
        try:
            positions = self.client.get_positions()
            active_deal_ids = set()
            for pos in positions.get("positions", []):
                active_deal_ids.add(pos["position"]["dealId"])
                # Also check dealReference
                ref = pos["position"].get("dealReference")
                if ref:
                    active_deal_ids.add(ref)

            db = self._get_db()
            cursor = db.execute("SELECT id, deal_id, entry_price, direction FROM trades WHERE status = 'OPEN'")
            open_trades = cursor.fetchall()

            reconciled = 0
            for trade_id, deal_id, entry_price, direction in open_trades:
                if deal_id not in active_deal_ids:
                    # Trade is closed on Capital.com but still OPEN in DB
                    db.execute("""
                        UPDATE trades SET status = 'CLOSED', exit_timestamp = ?
                        WHERE id = ? AND status = 'OPEN'
                    """, (datetime.now().isoformat(), trade_id))
                    reconciled += 1
                    logger.info(f"Reconciled trade {deal_id} as CLOSED (no longer on Capital.com)")

            if reconciled > 0:
                db.commit()
                logger.info(f"Reconciled {reconciled} trades")
            db.close()
        except Exception as e:
            logger.error(f"Trade reconciliation failed: {e}")

    def snapshot_balance(self, balance_data, bot_name="rule"):
        """Save a balance snapshot for the dashboard."""
        try:
            db = self._get_db()
            db.execute("""
                INSERT INTO balance_snapshots (timestamp, balance, available, profit_loss, bot_name)
                VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                balance_data.get("balance", 0),
                balance_data.get("available", 0),
                balance_data.get("profitLoss", 0),
                bot_name,
            ))
            db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Balance snapshot failed: {e}")

    def check_trailing_stops(self):
        """Check and update trailing stops for open positions."""
        positions = self.client.get_positions()

        # Clean up tracking for closed positions
        active_ids = {p["position"]["dealId"] for p in positions.get("positions", [])}
        closed = self._breakeven_done - active_ids
        self._breakeven_done -= closed

        for pos in positions.get("positions", []):
            deal_id = pos["position"]["dealId"]
            direction = pos["position"]["direction"]
            entry_price = pos["position"]["level"]
            current_price = pos["market"]["bid"] if direction == "BUY" else pos["market"]["offer"]

            # Skip if break-even already set for this position
            if deal_id in self._breakeven_done:
                continue

            if self.risk.should_move_trailing_stop(entry_price, current_price, direction):
                try:
                    self.client.update_position(deal_id, stop_loss=round(entry_price, 5))
                    self._breakeven_done.add(deal_id)
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

    def get_trade_feedback(self, epic=None, limit=20):
        """Get detailed trade feedback for AI learning.

        Returns closed trades with P&L and signal_details for analysis.
        If epic is provided, filters to that instrument.
        """
        db = self._get_db()
        if epic:
            cursor = db.execute(
                """SELECT epic, direction, entry_price, exit_price, stop_loss, take_profit,
                          profit_loss, signal_details, timestamp, exit_timestamp
                   FROM trades
                   WHERE profit_loss IS NOT NULL AND epic = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (epic, limit),
            )
        else:
            cursor = db.execute(
                """SELECT epic, direction, entry_price, exit_price, stop_loss, take_profit,
                          profit_loss, signal_details, timestamp, exit_timestamp
                   FROM trades
                   WHERE profit_loss IS NOT NULL
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            )
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        db.close()
        return results

    def get_cross_bot_winners(self, rule_db_path, limit=10):
        """Get winning trades from the rule-based bot for AI to learn from."""
        try:
            db = sqlite3.connect(rule_db_path)
            cursor = db.execute(
                """SELECT epic, direction, entry_price, exit_price, stop_loss, take_profit,
                          profit_loss, signal_details, timestamp
                   FROM trades
                   WHERE profit_loss > 0
                   ORDER BY profit_loss DESC LIMIT ?""",
                (limit,),
            )
            columns = [desc[0] for desc in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            db.close()
            return results
        except Exception as e:
            logger.error(f"Failed to read rule bot trades: {e}")
            return []

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
