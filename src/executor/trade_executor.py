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
                signal_details TEXT,
                balance_after REAL
            )
        """)
        # Add balance_after column if missing (migration for existing DBs)
        try:
            db.execute("ALTER TABLE trades ADD COLUMN balance_after REAL")
        except Exception:
            pass  # Column already exists
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

    def update_trade_close(self, deal_id, exit_price, profit_loss, partial=False, epic=None):
        """Update a trade record when position is closed by watchdog.

        Matches by deal_id first, then falls back to epic + OPEN status.
        This handles the mismatch between Capital.com's dealId (used by watchdog)
        and dealReference (stored in DB by _log_trade).
        """
        try:
            db = self._get_db()
            if partial:
                # Try deal_id match first, then epic match
                rows = db.execute(
                    "UPDATE trades SET signal_details = signal_details || ' | partial_pl=' || ? "
                    "WHERE deal_id = ? AND status = 'OPEN'",
                    (str(round(profit_loss, 2)), deal_id)
                ).rowcount
                if rows == 0 and epic:
                    db.execute(
                        "UPDATE trades SET signal_details = signal_details || ' | partial_pl=' || ? "
                        "WHERE epic = ? AND status = 'OPEN' "
                        "ORDER BY timestamp DESC LIMIT 1",
                        (str(round(profit_loss, 2)), epic)
                    )
            else:
                # Try deal_id match first
                rows = db.execute(
                    "UPDATE trades SET exit_price = ?, exit_timestamp = ?, profit_loss = ?, status = 'CLOSED' "
                    "WHERE deal_id = ? AND status = 'OPEN'",
                    (exit_price, datetime.now().isoformat(), profit_loss, deal_id)
                ).rowcount
                # Fallback: match by epic + OPEN (most recent)
                if rows == 0 and epic:
                    cursor = db.execute(
                        "SELECT id FROM trades WHERE epic = ? AND status = 'OPEN' "
                        "ORDER BY timestamp DESC LIMIT 1", (epic,)
                    )
                    row = cursor.fetchone()
                    if row:
                        db.execute(
                            "UPDATE trades SET exit_price = ?, exit_timestamp = ?, profit_loss = ?, status = 'CLOSED' "
                            "WHERE id = ?",
                            (exit_price, datetime.now().isoformat(), profit_loss, row[0])
                        )
                        rows = 1
                if rows == 0:
                    logger.warning(f"Trade DB: no matching OPEN trade for deal_id={deal_id} epic={epic}")
            db.commit()
            db.close()
            action = "partial update" if partial else "closed"
            logger.info(f"Trade DB {action}: {deal_id} epic={epic} exit={exit_price} P/L={profit_loss:.2f}")
        except Exception as e:
            logger.error(f"Failed to update trade close in DB: {e}")

    def reconcile_closed_trades(self):
        """Background sync: find OPEN trades in DB that are actually closed on Capital.com.
        Also backfills P/L for closed trades that are missing exit data."""
        try:
            positions = self.client.get_positions()
            active_deal_ids = set()
            for pos in positions.get("positions", []):
                active_deal_ids.add(pos["position"]["dealId"])
                ref = pos["position"].get("dealReference")
                if ref:
                    active_deal_ids.add(ref)

            db = self._get_db()
            cursor = db.execute("SELECT id, deal_id, entry_price, direction, size FROM trades WHERE status = 'OPEN'")
            open_trades = cursor.fetchall()

            # Fetch activity history to get actual P/L for closed trades
            activity_map = self._fetch_activity_pl()

            reconciled = 0
            for trade_id, deal_id, entry_price, direction, size in open_trades:
                if deal_id not in active_deal_ids:
                    # Look up actual P/L from Capital.com activity history
                    activity = activity_map.get(deal_id)
                    exit_price = None
                    profit_loss = None
                    if activity:
                        profit_loss = activity.get("profit_loss")
                        exit_price = activity.get("exit_price")
                    db.execute("""
                        UPDATE trades SET status = 'CLOSED', exit_timestamp = ?,
                        exit_price = COALESCE(?, exit_price),
                        profit_loss = COALESCE(?, profit_loss)
                        WHERE id = ? AND status = 'OPEN'
                    """, (datetime.now().isoformat(), exit_price, profit_loss, trade_id))
                    reconciled += 1
                    pl_str = f"P/L: EUR {profit_loss:+.2f}" if profit_loss is not None else "P/L: unknown"
                    logger.info(f"Reconciled trade {deal_id} as CLOSED ({pl_str})")

            # Backfill: update closed trades that are missing P/L
            if activity_map:
                cursor2 = db.execute(
                    "SELECT id, deal_id FROM trades WHERE status = 'CLOSED' AND profit_loss IS NULL"
                )
                missing_pl = cursor2.fetchall()
                backfilled = 0
                for trade_id, deal_id in missing_pl:
                    activity = activity_map.get(deal_id)
                    if activity and activity.get("profit_loss") is not None:
                        db.execute("""
                            UPDATE trades SET profit_loss = ?, exit_price = COALESCE(?, exit_price)
                            WHERE id = ?
                        """, (activity["profit_loss"], activity.get("exit_price"), trade_id))
                        backfilled += 1
                if backfilled > 0:
                    logger.info(f"Backfilled P/L for {backfilled} trades from activity history")

            if reconciled > 0 or (activity_map and missing_pl):
                db.commit()
                if reconciled > 0:
                    logger.info(f"Reconciled {reconciled} trades")
            db.close()
        except Exception as e:
            logger.error(f"Trade reconciliation failed: {e}")

    def _fetch_activity_pl(self):
        """Fetch recent activity/transaction history from Capital.com to get actual P/L.
        Returns dict: {deal_id: {"profit_loss": float, "exit_price": float}}
        """
        result = {}
        try:
            # Get transaction history (contains actual P/L per deal)
            from datetime import timedelta
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
            transactions = self.client.get_transaction_history(from_date=from_date)

            for tx in transactions.get("transactions", []):
                ref = tx.get("reference")
                if not ref:
                    continue
                pl = tx.get("profitAndLoss")
                if pl is None:
                    continue
                # Parse P/L string like "E-12.50" or "E45.30"
                try:
                    pl_str = str(pl).replace("E", "").replace(",", "").strip()
                    profit_loss = float(pl_str)
                except (ValueError, TypeError):
                    profit_loss = None

                if profit_loss is not None:
                    result[ref] = {
                        "profit_loss": profit_loss,
                        "exit_price": None,  # Transaction history doesn't include exit price
                    }
        except Exception as e:
            logger.debug(f"Transaction history fetch failed: {e}")

        try:
            # Get activity history (contains exit levels)
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
            activities = self.client.get_activity_history(from_date=from_date)

            for act in activities.get("activities", []):
                deal_id = act.get("dealId", "")
                details = act.get("details", {})
                actions = details.get("actions", [])

                for action in actions:
                    action_type = action.get("actionType", "")
                    if action_type in ("POSITION_CLOSED", "STOP_LIMIT_AMENDED"):
                        level = details.get("level")
                        if deal_id and level:
                            if deal_id in result:
                                result[deal_id]["exit_price"] = float(level)
                            else:
                                result[deal_id] = {"profit_loss": None, "exit_price": float(level)}
        except Exception as e:
            logger.debug(f"Activity history fetch failed: {e}")

        if result:
            logger.info(f"Fetched P/L data for {len(result)} deals from Capital.com history")
        return result

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
