"""
Weekly Evaluator - Sunday 08:00 CET evaluation of trading performance.
Haiku analyzes the week, suggests improvements, user approves/rejects via Telegram.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Copenhagen")


class WeeklyEvaluator:
    """Weekly performance evaluation with AI suggestions and user approval."""

    def __init__(self, ai_analyst, trade_executor, notifier, config):
        self.ai = ai_analyst
        self.executor = trade_executor
        self.notifier = notifier
        self.db_path = config.get("database", {}).get("path", "data_ai/trades.db")
        self._approval_pending = None  # evaluation ID awaiting approval
        self._init_tables()

    def _init_tables(self):
        """Create weekly evaluation and strategy config tables."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_start TEXT NOT NULL,
                    evaluation TEXT NOT NULL,
                    suggestion TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    approved_at TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule TEXT NOT NULL,
                    source TEXT DEFAULT 'weekly_eval',
                    week TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[WeeklyEval] Table init error: {e}")

    def start_scheduler(self):
        """Schedule weekly evaluation for Sunday 08:00 CET."""
        def _schedule_next():
            now = datetime.now(CET)
            # Find next Sunday 08:00 CET
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour >= 8:
                days_until_sunday = 7
            target = (now + timedelta(days=days_until_sunday)).replace(
                hour=8, minute=0, second=0, microsecond=0
            )
            delay = (target - now).total_seconds()

            logger.info(f"[WeeklyEval] Next evaluation: {target.strftime('%Y-%m-%d %H:%M')} CET ({delay / 3600:.1f}h)")
            timer = threading.Timer(delay, _run_eval)
            timer.daemon = True
            timer.start()

        def _run_eval():
            self.run_weekly_evaluation()
            _schedule_next()

        # Check if we missed this week's evaluation
        now = datetime.now(CET)
        if now.weekday() == 6 and now.hour >= 8:
            week_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")
            if not self._has_evaluation(week_start):
                logger.info("[WeeklyEval] Missed this week's eval, running now")
                threading.Thread(target=self.run_weekly_evaluation, daemon=True).start()

        _schedule_next()

    def run_weekly_evaluation(self):
        """Run the weekly performance evaluation."""
        try:
            now = datetime.now(CET)
            week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
            week_end = now.strftime("%Y-%m-%d")

            # Fetch closed trades from last 7 days
            trades = self._get_week_trades()

            if not trades:
                self.notifier.send("📊 <b>Ugentlig evaluering</b>\n\nIngen handler denne uge.")
                return

            # Calculate stats
            total = len(trades)
            wins = [t for t in trades if (t["profit_loss"] or 0) > 0]
            losses = [t for t in trades if (t["profit_loss"] or 0) < 0]
            win_rate = len(wins) / total * 100 if total > 0 else 0
            total_pl = sum(t["profit_loss"] or 0 for t in trades)

            best = max(trades, key=lambda t: t["profit_loss"] or 0)
            worst = min(trades, key=lambda t: t["profit_loss"] or 0)

            # Group by market condition
            conditions = {}
            for t in trades:
                cond = t.get("journal_market_condition") or "unknown"
                if cond not in conditions:
                    conditions[cond] = {"trades": 0, "pl": 0, "wins": 0}
                conditions[cond]["trades"] += 1
                conditions[cond]["pl"] += t["profit_loss"] or 0
                if (t["profit_loss"] or 0) > 0:
                    conditions[cond]["wins"] += 1

            # Build AI prompt
            conditions_text = ""
            for cond, data in conditions.items():
                wr = data["wins"] / data["trades"] * 100 if data["trades"] > 0 else 0
                conditions_text += f"  {cond}: {data['trades']} trades, EUR {data['pl']:+.2f}, {wr:.0f}% win rate\n"

            # Include post-trade analysis lessons
            lessons = self._get_post_analyses(trades)
            lessons_text = ""
            if lessons:
                lessons_text = "\nPOST-TRADE ANALYSER FRA UGEN:\n"
                for l in lessons[:5]:
                    lessons_text += f"  - {l.get('my_error_or_success', 'N/A')}\n"

            prompt = f"""Evaluér denne uges trading-performance og giv ÉT konkret forslag til næste uge.

UGE: {week_start} til {week_end}

STATS:
- Antal trades: {total}
- Wins: {len(wins)} | Losses: {len(losses)}
- Win rate: {win_rate:.0f}%
- Total P/L: EUR {total_pl:+.2f}

BEDSTE TRADE: {best['epic']} {best['direction']} EUR {best['profit_loss'] or 0:+.2f}
VÆRSTE TRADE: {worst['epic']} {worst['direction']} EUR {worst['profit_loss'] or 0:+.2f}

MARKEDSFORHOLD:
{conditions_text}
{lessons_text}

Svar KUN med valid JSON:
{{"summary": "2-3 sætninger om ugen", "what_worked": "hvad virkede", "what_failed": "hvad fejlede", "suggestion": "ÉT konkret og specifikt forslag til næste uge"}}"""

            self.ai._rate_limit()
            response = self.ai.client.messages.create(
                model=self.ai.model,
                max_tokens=500,
                system="Du er en trading-coach. Vær ærlig, konkret og handlingsorienteret. Svar KUN med JSON.",
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3].strip()

            evaluation = json.loads(result_text)

            # Store evaluation
            eval_data = {
                "total_trades": total,
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(win_rate, 1),
                "total_pl": round(total_pl, 2),
                "best_trade": {"epic": best["epic"], "direction": best["direction"], "pl": best["profit_loss"] or 0},
                "worst_trade": {"epic": worst["epic"], "direction": worst["direction"], "pl": worst["profit_loss"] or 0},
                "conditions": conditions,
                "summary": evaluation.get("summary", ""),
                "what_worked": evaluation.get("what_worked", ""),
                "what_failed": evaluation.get("what_failed", ""),
            }
            suggestion = evaluation.get("suggestion", "Ingen forslag")

            eval_id = self._save_evaluation(week_start, eval_data, suggestion)
            self._approval_pending = eval_id

            # Send to Telegram
            msg = (
                f"📊 <b>UGENTLIG EVALUERING</b>\n"
                f"Uge: {week_start}\n\n"
                f"<b>Stats:</b>\n"
                f"  Trades: {total} | Win rate: {win_rate:.0f}%\n"
                f"  Total P/L: EUR {total_pl:+.2f}\n"
                f"  Bedste: {best['epic']} EUR {best['profit_loss'] or 0:+.2f}\n"
                f"  Værste: {worst['epic']} EUR {worst['profit_loss'] or 0:+.2f}\n\n"
                f"<b>Hvad virkede:</b> {evaluation.get('what_worked', '-')}\n"
                f"<b>Hvad fejlede:</b> {evaluation.get('what_failed', '-')}\n\n"
                f"<b>Opsummering:</b> {evaluation.get('summary', '-')}\n\n"
                f"💡 <b>FORSLAG TIL NÆSTE UGE:</b>\n"
                f"{suggestion}\n\n"
                f"Skriv <b>godkend</b> eller <b>afvis</b>"
            )
            self.notifier.send(msg)

            logger.info(f"[WeeklyEval] Evaluation sent: {total} trades, {win_rate:.0f}% WR, EUR {total_pl:+.2f}")

        except Exception as e:
            logger.error(f"[WeeklyEval] Evaluation failed: {e}")
            self.notifier.send(f"❌ Ugentlig evaluering fejlede: {e}")

    def handle_approval(self, text):
        """Check if message is an approval/rejection of pending evaluation."""
        if not self._approval_pending:
            return None

        lower = text.strip().lower()
        if lower == "godkend":
            return self._approve(self._approval_pending)
        elif lower == "afvis":
            return self._reject(self._approval_pending)
        return None

    def get_active_strategies(self):
        """Get all active strategy rules from approved evaluations."""
        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute(
                "SELECT rule FROM strategy_config WHERE active = 1 ORDER BY id DESC LIMIT 10"
            ).fetchall()
            conn.close()
            return [r[0] for r in rows]
        except Exception as e:
            logger.debug(f"[WeeklyEval] Load strategies error: {e}")
            return []

    # ── Private methods ───────────────────────────────────────────

    def _get_week_trades(self):
        """Get closed trades from the last 7 days."""
        try:
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'CLOSED' AND timestamp >= ? ORDER BY timestamp",
                (cutoff,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[WeeklyEval] Fetch trades error: {e}")
            return []

    def _get_post_analyses(self, trades):
        """Extract post-trade analyses from trades."""
        results = []
        for t in trades:
            if t.get("post_analysis"):
                try:
                    analysis = json.loads(t["post_analysis"]) if isinstance(t["post_analysis"], str) else t["post_analysis"]
                    results.append(analysis)
                except (json.JSONDecodeError, TypeError):
                    pass
        return results

    def _has_evaluation(self, week_start):
        """Check if evaluation for this week already exists."""
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT id FROM weekly_evaluations WHERE week_start = ?", (week_start,)
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def _save_evaluation(self, week_start, eval_data, suggestion):
        """Save weekly evaluation to DB. Returns evaluation ID."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "INSERT INTO weekly_evaluations (week_start, evaluation, suggestion, created_at) VALUES (?, ?, ?, ?)",
                (week_start, json.dumps(eval_data), suggestion, datetime.now().isoformat())
            )
            eval_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return eval_id
        except Exception as e:
            logger.error(f"[WeeklyEval] Save error: {e}")
            return None

    def _approve(self, eval_id):
        """Approve weekly suggestion and add to strategy config."""
        try:
            conn = sqlite3.connect(self.db_path)
            # Get suggestion
            row = conn.execute(
                "SELECT suggestion, week_start FROM weekly_evaluations WHERE id = ?", (eval_id,)
            ).fetchone()
            if not row:
                conn.close()
                return "Evaluering ikke fundet."

            suggestion, week = row

            # Update evaluation status
            conn.execute(
                "UPDATE weekly_evaluations SET status = 'approved', approved_at = ? WHERE id = ?",
                (datetime.now().isoformat(), eval_id)
            )

            # Add to strategy config
            conn.execute(
                "INSERT INTO strategy_config (rule, source, week, created_at) VALUES (?, 'weekly_eval', ?, ?)",
                (suggestion, week, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()

            self._approval_pending = None
            logger.info(f"[WeeklyEval] Suggestion approved: {suggestion[:60]}")
            return f"✅ <b>Godkendt!</b>\n\nNy regel tilføjet:\n\"{suggestion}\"\n\nDenne regel påvirker nu AI'ens handelsbeslutninger."

        except Exception as e:
            logger.error(f"[WeeklyEval] Approve error: {e}")
            return f"Fejl: {e}"

    def _reject(self, eval_id):
        """Reject weekly suggestion."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE weekly_evaluations SET status = 'rejected' WHERE id = ?", (eval_id,)
            )
            conn.commit()
            conn.close()

            self._approval_pending = None
            logger.info(f"[WeeklyEval] Suggestion rejected (eval_id={eval_id})")
            return "❌ <b>Afvist.</b> Forslaget vil ikke påvirke handelsstrategien."

        except Exception as e:
            logger.error(f"[WeeklyEval] Reject error: {e}")
            return f"Fejl: {e}"
