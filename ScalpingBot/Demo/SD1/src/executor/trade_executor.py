import json
import logging
import sqlite3
import os
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)


def _safe_json(obj):
    """JSON-serialize with numpy type support."""
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
        # Add source column for tracking trade origin (bot vs api_reconcile)
        try:
            db.execute("ALTER TABLE trades ADD COLUMN source TEXT DEFAULT 'bot'")
        except Exception:
            pass  # Column already exists
        # Migration columns
        for col, col_type in [
            ("journal_why", "TEXT"),
            ("journal_expected_target", "REAL"),
            ("journal_market_condition", "TEXT"),
            ("post_analysis", "TEXT"),
            ("post_analysis_timestamp", "TEXT"),
            ("alignment_score", "INTEGER"),
            # v2: comprehensive trade logging
            ("exit_reason", "TEXT"),
            ("account_snapshot", "TEXT"),
            ("risk_snapshot", "TEXT"),
            ("gates_snapshot", "TEXT"),
            ("ai_raw_response", "TEXT"),
        ]:
            try:
                db.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
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

    def build_snapshots(self, balance_info, open_count, current_price, stop_loss, take_profit, size, direction):
        """Build account/risk snapshots for comprehensive trade logging."""
        balance = balance_info.get("balance", 0)
        risk_eur = abs(current_price - stop_loss) * size
        sl_dist = abs(current_price - stop_loss)
        tp_dist = abs(take_profit - current_price)
        rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0
        account_snap = {
            "balance": balance,
            "available": balance_info.get("available", balance),
            "open_positions": open_count,
            "profit_loss": balance_info.get("profitLoss", 0),
        }
        risk_snap = {
            "size": size,
            "risk_eur": round(risk_eur, 2),
            "risk_pct": round(risk_eur / balance * 100, 2) if balance > 0 else 0,
            "rr_ratio": rr_ratio,
            "sl_distance_pct": round(sl_dist / current_price * 100, 2),
            "tp_distance_pct": round(tp_dist / current_price * 100, 2),
        }
        return account_snap, risk_snap

    def execute_trade(self, epic, signal, signal_details, current_price, gates_snapshot=None):
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

        # Build snapshots for comprehensive logging
        account_snap = _safe_json({
            "balance": current_balance,
            "available": balance_info.get("available", current_balance),
            "open_positions": open_count,
            "profit_loss": balance_info.get("profitLoss", 0),
        })
        risk_eur = abs(current_price - stop_loss) * size
        sl_dist = abs(current_price - stop_loss)
        tp_dist = abs(take_profit - current_price)
        rr_ratio = round(tp_dist / sl_dist, 2) if sl_dist > 0 else 0
        risk_snap = _safe_json({
            "size": size,
            "risk_eur": round(risk_eur, 2),
            "risk_pct": round(risk_eur / current_balance * 100, 2) if current_balance > 0 else 0,
            "rr_ratio": rr_ratio,
            "sl_distance_pct": round(sl_dist / current_price * 100, 2),
            "tp_distance_pct": round(tp_dist / current_price * 100, 2),
        })
        gates_json = _safe_json(gates_snapshot) if gates_snapshot else None

        # Execute the trade
        try:
            result = self.client.create_position(
                epic=epic,
                direction=signal,
                size=size,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            deal_ref = result.get("dealReference", "unknown")

            # Fetch the actual Capital.com dealId via confirms endpoint
            deal_id = deal_ref  # fallback
            try:
                confirm = self.client.get_deal_confirmation(deal_ref)
                affected = confirm.get("affectedDeals", [])
                if affected:
                    deal_id = affected[0].get("dealId", deal_ref)
                    logger.info(f"Deal confirmed: {deal_ref} -> dealId {deal_id}")
            except Exception as e:
                logger.warning(f"Could not fetch deal confirmation for {deal_ref}: {e}")

            # Log to database (with duplicate guard)
            db = self._get_db()
            existing = db.execute(
                "SELECT id FROM trades WHERE deal_id = ?", (deal_id,)
            ).fetchone()
            if existing:
                logger.warning(f"Trade DB: deal_id {deal_id} already exists, skipping duplicate")
                db.close()
                self._recently_traded[epic] = datetime.now()
                return result, None
            db.execute("""
                INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                                    stop_loss, take_profit, deal_id, status, signal_details, source,
                                    account_snapshot, risk_snapshot, gates_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, 'bot', ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                epic,
                signal,
                size,
                current_price,
                stop_loss,
                take_profit,
                deal_id,
                _safe_json(signal_details) if isinstance(signal_details, dict) else str(signal_details),
                account_snap,
                risk_snap,
                gates_json,
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

    def _log_trade(self, epic, signal, size, price, stop_loss, take_profit, result, details,
                   journal_data=None, account_snapshot=None, risk_snapshot=None,
                   gates_snapshot=None, ai_raw_response=None):
        """Log a trade to the database. Checks for duplicate deal_id before insert."""
        deal_ref = result.get("dealReference", "unknown")
        deal_id = deal_ref
        try:
            confirm = self.client.get_deal_confirmation(deal_ref)
            affected = confirm.get("affectedDeals", [])
            if affected:
                deal_id = affected[0].get("dealId", deal_ref)
        except Exception:
            pass
        db = self._get_db()
        # Duplicate guard: skip if deal_id already exists
        existing = db.execute(
            "SELECT id FROM trades WHERE deal_id = ?", (deal_id,)
        ).fetchone()
        if existing:
            logger.warning(f"Trade DB: deal_id {deal_id} already exists, skipping duplicate insert")
            db.close()
            return
        # Extract journal fields
        j_why = journal_data.get("why", "") if journal_data else None
        j_target = journal_data.get("expected_target") if journal_data else None
        j_condition = journal_data.get("market_condition") if journal_data else None
        # Extract alignment score from details
        alignment_score = details.get("alignment_score") if isinstance(details, dict) else None
        # Serialize snapshots
        acct_json = _safe_json(account_snapshot) if isinstance(account_snapshot, dict) else account_snapshot
        risk_json = _safe_json(risk_snapshot) if isinstance(risk_snapshot, dict) else risk_snapshot
        gates_json = _safe_json(gates_snapshot) if isinstance(gates_snapshot, dict) else gates_snapshot
        db.execute("""
            INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                                stop_loss, take_profit, deal_id, status, signal_details, source,
                                journal_why, journal_expected_target, journal_market_condition,
                                alignment_score, account_snapshot, risk_snapshot, gates_snapshot,
                                ai_raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, 'bot', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            epic,
            signal,
            size,
            price,
            stop_loss,
            take_profit,
            deal_id,
            _safe_json(details) if isinstance(details, dict) else str(details),
            j_why,
            j_target,
            j_condition,
            alignment_score,
            acct_json,
            risk_json,
            gates_json,
            ai_raw_response,
        ))
        db.commit()
        db.close()
        logger.info(f"Trade logged: {signal} {epic} x{size} @ {price} (alignment: {alignment_score})")

    def update_trade_close(self, deal_id, exit_price, profit_loss, partial=False, epic=None, exit_reason=None):
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
                exit_ts = datetime.now().isoformat()
                # Try deal_id match first
                rows = db.execute(
                    "UPDATE trades SET exit_price = ?, exit_timestamp = ?, profit_loss = ?, "
                    "status = 'CLOSED', exit_reason = COALESCE(?, exit_reason) "
                    "WHERE deal_id = ? AND status = 'OPEN'",
                    (exit_price, exit_ts, profit_loss, exit_reason, deal_id)
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
                            "UPDATE trades SET exit_price = ?, exit_timestamp = ?, profit_loss = ?, "
                            "status = 'CLOSED', exit_reason = COALESCE(?, exit_reason) "
                            "WHERE id = ?",
                            (exit_price, exit_ts, profit_loss, exit_reason, row[0])
                        )
                        rows = 1
                if rows == 0:
                    logger.warning(f"Trade DB: no matching OPEN trade for deal_id={deal_id} epic={epic}")
            db.commit()
            db.close()
            action = "partial update" if partial else "closed"
            reason_str = f" reason={exit_reason}" if exit_reason else ""
            logger.info(f"Trade DB {action}: {deal_id} epic={epic} exit={exit_price} P/L={profit_loss:.2f}{reason_str}")
        except Exception as e:
            logger.error(f"Failed to update trade close in DB: {e}")

    def reconcile_closed_trades(self):
        """Sync DB with Capital.com: close OPEN trades and backfill missing P/L.

        Uses transaction history ('Trade closed' entries) matched by epic + timestamp
        to get actual P/L in EUR from Capital.com.
        """
        from datetime import timedelta
        try:
            # Get currently active positions on Capital.com
            positions = self.client.get_positions()
            active_epics = set()
            active_deal_ids = set()
            for pos in positions.get("positions", []):
                active_epics.add(pos["market"]["epic"])
                active_deal_ids.add(pos["position"]["dealId"])

            # Fetch transaction history (contains actual P/L for closed trades)
            closes_by_epic = self._fetch_transaction_closes()

            db = self._get_db()

            # --- Step 1: Close OPEN trades that are no longer on Capital.com ---
            cursor = db.execute(
                "SELECT id, deal_id, epic, entry_price, direction, size, timestamp "
                "FROM trades WHERE status = 'OPEN' ORDER BY timestamp"
            )
            open_trades = cursor.fetchall()

            reconciled = 0
            for trade_id, deal_id, epic, entry_price, direction, size, ts in open_trades:
                if deal_id in active_deal_ids or epic in active_epics:
                    continue  # Still active

                # Find matching close transaction (dealId-based primary match)
                profit_loss, exit_ts, new_deal_id = self._match_close(
                    epic, ts, closes_by_epic, deal_id=deal_id
                )

                db.execute("""
                    UPDATE trades SET status = 'CLOSED',
                    exit_timestamp = COALESCE(?, ?),
                    profit_loss = ?,
                    deal_id = COALESCE(?, deal_id),
                    source = 'api_reconcile',
                    exit_reason = COALESCE(exit_reason, 'server_sl_tp')
                    WHERE id = ?
                """, (exit_ts, datetime.now().isoformat(), profit_loss, new_deal_id, trade_id))
                reconciled += 1
                pl_str = f"P/L: EUR {profit_loss:+.2f}" if profit_loss is not None else "P/L: unknown"
                logger.info(f"Reconciled {epic} (id={trade_id}) as CLOSED ({pl_str})")

            # --- Step 2: Backfill/correct P/L for CLOSED trades ---
            # Include NULL P/L AND recently-closed trades (within 48h)
            # that may have estimated P/L from watchdog (not actual from Capital.com)
            cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
            cursor2 = db.execute(
                "SELECT id, epic, timestamp, profit_loss FROM trades "
                "WHERE status = 'CLOSED' AND (profit_loss IS NULL OR exit_timestamp > ?) "
                "ORDER BY timestamp",
                (cutoff,)
            )
            missing = cursor2.fetchall()
            backfilled = 0

            for trade_id, epic, ts, existing_pl in missing:
                profit_loss, exit_ts, new_deal_id = self._match_close(
                    epic, ts, closes_by_epic
                )
                if profit_loss is not None:
                    db.execute("""
                        UPDATE trades SET profit_loss = ?,
                        exit_timestamp = COALESCE(?, exit_timestamp),
                        deal_id = COALESCE(?, deal_id)
                        WHERE id = ?
                    """, (profit_loss, exit_ts, new_deal_id, trade_id))
                    backfilled += 1
                    if existing_pl is not None and abs(profit_loss - existing_pl) > 0.01:
                        logger.info(
                            f"P/L corrected {epic} (id={trade_id}): "
                            f"estimated {existing_pl:+.2f} -> actual {profit_loss:+.2f}"
                        )

            if reconciled > 0 or backfilled > 0:
                self._update_balance_after(db)
                db.commit()
                logger.info(f"Reconciliation: {reconciled} closed, {backfilled} backfilled")
            db.close()
        except Exception as e:
            logger.error(f"Trade reconciliation failed: {e}")

    def _fetch_transaction_closes(self):
        """Fetch 'Trade closed' transactions from Capital.com, grouped by epic.
        Returns: {epic: [{"pl": float, "date": str, "dealId": str, "used": bool}]}
        """
        from datetime import timedelta
        result = {}
        try:
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
            to_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            resp = self.client._request("GET", "/api/v1/history/transactions", params={
                "from": from_date, "to": to_date, "maxSpanSeconds": "2592000"
            })
            for tx in resp.get("transactions", []):
                if tx.get("note") != "Trade closed" or tx.get("transactionType") != "TRADE":
                    continue
                epic = tx.get("instrumentName")
                if not epic:
                    continue
                pl = float(tx.get("size", 0))
                date = tx.get("dateUtc", "")
                deal_id = tx.get("dealId", "")
                if epic not in result:
                    result[epic] = []
                result[epic].append({"pl": pl, "date": date, "dealId": deal_id, "used": False})
            # Sort by date so we match chronologically
            for epic in result:
                result[epic].sort(key=lambda x: x["date"])
            total = sum(len(v) for v in result.values())
            if total:
                logger.info(f"Fetched {total} trade closes from transaction history")
        except Exception as e:
            logger.error(f"Transaction history fetch failed: {e}")
        return result

    def _match_close(self, epic, open_timestamp, closes_by_epic, deal_id=None):
        """Find matching close transaction. Primary: dealId match. Fallback: epic + timestamp.
        Returns: (profit_loss, exit_timestamp, deal_id) or (None, None, None)
        """
        epic_closes = closes_by_epic.get(epic, [])

        # Primary match: by dealId (most accurate)
        if deal_id:
            for close in epic_closes:
                if close["used"]:
                    continue
                if close["dealId"] == deal_id:
                    close["used"] = True
                    return close["pl"], close["date"], close["dealId"]

        # Fallback: earliest unused close after open timestamp (legacy matching)
        for close in epic_closes:
            if close["used"]:
                continue
            if close["date"] >= open_timestamp[:19]:
                close["used"] = True
                return close["pl"], close["date"], close["dealId"]
        return None, None, None

    def _update_balance_after(self, db):
        """Update balance_after for closed trades using current account balance."""
        try:
            balance_data = self.client.get_account_balance()
            current_balance = balance_data.get("balance", 0)
            db.execute("""
                UPDATE trades SET balance_after = ?
                WHERE status = 'CLOSED' AND balance_after IS NULL AND profit_loss IS NOT NULL
            """, (current_balance,))
        except Exception as e:
            logger.debug(f"Balance update failed: {e}")

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
