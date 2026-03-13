"""
Coach's own SQLite database for storing analysis reports and recommendations.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CoachDB:
    """Manage the coach's analysis and recommendation database."""

    def __init__(self, db_path="data/coach.db"):
        self.db_path = db_path
        self._init_tables()

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    def _init_tables(self):
        conn = self._get_db()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                trigger TEXT NOT NULL,
                raw_stats TEXT,
                llm_response TEXT,
                model_used TEXT,
                token_count INTEGER,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                bot_id TEXT NOT NULL,
                type TEXT NOT NULL,
                priority TEXT NOT NULL,
                description TEXT NOT NULL,
                config_key TEXT,
                current_value TEXT,
                recommended_value TEXT,
                evidence TEXT,
                expected_impact TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY (report_id) REFERENCES analysis_reports(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendation_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_id INTEGER NOT NULL,
                implemented_at TEXT,
                measured_at TEXT,
                trades_before INTEGER,
                win_rate_before REAL,
                trades_after INTEGER,
                win_rate_after REAL,
                pl_impact REAL,
                verdict TEXT,
                FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"[Coach] Database initialized: {self.db_path}")

    def save_report(self, trigger, period_start, period_end, raw_stats, llm_response, model_used, token_count):
        """Save an analysis report and return its ID."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analysis_reports (timestamp, period_start, period_end, trigger, raw_stats, llm_response, model_used, token_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, period_start, period_end, trigger, json.dumps(raw_stats), json.dumps(llm_response), model_used, token_count, now))
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"[Coach] Saved report #{report_id} ({trigger})")
        return report_id

    def save_recommendation(self, report_id, bot_id, rec):
        """Save a single recommendation from LLM output. Returns recommendation ID."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recommendations (report_id, bot_id, type, priority, description, config_key, current_value, recommended_value, evidence, expected_impact, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            report_id,
            bot_id,
            rec.get("type", "config_change"),
            rec.get("priority", "medium"),
            rec.get("description", ""),
            rec.get("config_key"),
            str(rec.get("current_value", "")) if rec.get("current_value") is not None else None,
            str(rec.get("recommended_value", "")) if rec.get("recommended_value") is not None else None,
            rec.get("evidence"),
            rec.get("expected_impact"),
            now,
        ))
        rec_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return rec_id

    def approve_recommendation(self, rec_id):
        """Mark a recommendation as approved."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        conn.execute("UPDATE recommendations SET status = 'approved', resolved_at = ? WHERE id = ?", (now, rec_id))
        conn.commit()
        conn.close()
        logger.info(f"[Coach] Recommendation #{rec_id} approved")

    def reject_recommendation(self, rec_id):
        """Mark a recommendation as rejected."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        conn.execute("UPDATE recommendations SET status = 'rejected', resolved_at = ? WHERE id = ?", (now, rec_id))
        conn.commit()
        conn.close()
        logger.info(f"[Coach] Recommendation #{rec_id} rejected")

    def get_pending_recommendations(self):
        """Get all pending recommendations."""
        conn = self._get_db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM recommendations WHERE status = 'pending' ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_recommendations_by_bot(self, bot_id):
        """Get all recommendations for a specific bot."""
        conn = self._get_db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM recommendations WHERE bot_id = ? ORDER BY created_at DESC", (bot_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_recommendation(self, rec_id):
        """Get a single recommendation by ID."""
        conn = self._get_db()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM recommendations WHERE id = ?", (rec_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_latest_report(self):
        """Get the most recent analysis report."""
        conn = self._get_db()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM analysis_reports ORDER BY created_at DESC LIMIT 1").fetchone()
        conn.close()
        if not row:
            return None
        report = dict(row)
        report["raw_stats"] = json.loads(report["raw_stats"]) if report["raw_stats"] else {}
        report["llm_response"] = json.loads(report["llm_response"]) if report["llm_response"] else {}
        return report

    def save_outcome(self, recommendation_id, trades_before, win_rate_before, trades_after, win_rate_after, pl_impact, verdict):
        """Save measured outcome for an approved recommendation."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_db()
        conn.execute("""
            INSERT INTO recommendation_outcomes (recommendation_id, implemented_at, measured_at, trades_before, win_rate_before, trades_after, win_rate_after, pl_impact, verdict)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (recommendation_id, now, now, trades_before, win_rate_before, trades_after, win_rate_after, pl_impact, verdict))
        conn.commit()
        conn.close()

    def get_approved_without_outcome(self):
        """Get approved recommendations that haven't been measured yet."""
        conn = self._get_db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT r.* FROM recommendations r
            LEFT JOIN recommendation_outcomes o ON o.recommendation_id = r.id
            WHERE r.status = 'approved' AND o.id IS NULL
            ORDER BY r.resolved_at ASC
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
