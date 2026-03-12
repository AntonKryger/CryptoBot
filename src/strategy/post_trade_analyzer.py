"""
Post-Trade Analyzer - AI reflection on every closed trade.
Blocks next trade until analysis is complete.
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class PostTradeAnalyzer:
    """Analyzes closed trades using Claude and blocks trading until done."""

    def __init__(self, ai_analyst, trade_executor, notifier, config):
        self.ai = ai_analyst
        self.executor = trade_executor
        self.notifier = notifier
        self.db_path = config.get("database", {}).get("path", "data_ai/trades.db")
        self._blocked = False
        self._block_time = None
        self._block_timeout = 300  # 5 min max block

    def is_blocked(self):
        """Check if trading is blocked pending post-trade analysis."""
        if not self._blocked:
            return False
        # Auto-unblock after timeout to prevent permanent lockout
        if self._block_time and (datetime.now() - self._block_time).total_seconds() > self._block_timeout:
            logger.warning("[PostAnalysis] Block timeout exceeded, auto-unblocking")
            self._blocked = False
            return False
        return True

    def mark_pending(self, deal_id):
        """Block trading until this trade has been analyzed."""
        self._blocked = True
        self._block_time = datetime.now()
        logger.info(f"[PostAnalysis] Trading blocked until analysis of {deal_id} complete")

    def analyze_closed_trade(self, deal_id, epic):
        """Run post-trade analysis in background thread."""
        thread = threading.Thread(
            target=self._analyze_async,
            args=(deal_id, epic),
            daemon=True,
        )
        thread.start()

    def _analyze_async(self, deal_id, epic):
        """Fetch trade data and ask AI for analysis."""
        try:
            # Small delay to let DB update settle
            time.sleep(2)

            # Fetch the trade
            trade = self._get_trade(deal_id, epic)
            if not trade:
                logger.warning(f"[PostAnalysis] Trade not found: {deal_id} / {epic}")
                self._blocked = False
                return

            entry_price = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price", 0)
            pl_eur = trade.get("profit_loss", 0) or 0
            direction = trade.get("direction", "?")
            journal_why = trade.get("journal_why", "")
            expected_target = trade.get("journal_expected_target", 0)
            market_condition = trade.get("journal_market_condition", "unknown")

            # Calculate P/L %
            if entry_price and exit_price:
                if direction == "BUY":
                    pl_pct = (exit_price - entry_price) / entry_price * 100
                else:
                    pl_pct = (entry_price - exit_price) / entry_price * 100
            else:
                pl_pct = 0

            # Did it reach target?
            did_it_happen = "no"
            if expected_target and exit_price:
                if direction == "BUY" and exit_price >= expected_target:
                    did_it_happen = "yes"
                elif direction == "SELL" and exit_price <= expected_target:
                    did_it_happen = "yes"

            # Ask AI for reflection
            prompt = f"""Analyser denne lukkede trade og giv en ærlig vurdering.

TRADE DATA:
- Asset: {epic}
- Retning: {direction}
- Entry: {entry_price:.4f}
- Exit: {exit_price:.4f}
- P/L: EUR {pl_eur:+.2f} ({pl_pct:+.2f}%)
- Markedstilstand: {market_condition}
- Forventet mål: {expected_target:.4f if expected_target else 'ikke sat'}
- Nåede mål: {did_it_happen}

ORIGINAL BEGRUNDELSE:
{journal_why or 'Ingen journal tilgængelig'}

Svar KUN med valid JSON:
{{"did_it_happen": "yes|no", "my_error_or_success": "1 konkret ting", "next_time": "hvad gøres anderledes næste gang"}}"""

            self.ai._rate_limit()
            response = self.ai.client.messages.create(
                model=self.ai.model,
                max_tokens=300,
                system="Du er en trading-analytiker. Vær ærlig og konkret. Svar KUN med JSON.",
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3].strip()

            analysis = json.loads(result_text)

            # Build full analysis record
            full_analysis = {
                "exit_price": exit_price,
                "pl_eur": pl_eur,
                "pl_pct": round(pl_pct, 2),
                "did_it_happen": analysis.get("did_it_happen", did_it_happen),
                "my_error_or_success": analysis.get("my_error_or_success", ""),
                "next_time": analysis.get("next_time", ""),
            }

            # Save to DB
            self._save_analysis(deal_id, epic, full_analysis)

            # Send to Telegram
            self._send_telegram(epic, direction, full_analysis)

            logger.info(f"[PostAnalysis] {epic} analysis complete: {full_analysis.get('my_error_or_success', '')[:60]}")

        except Exception as e:
            logger.error(f"[PostAnalysis] Failed for {deal_id}: {e}")
        finally:
            self._blocked = False

    def _get_trade(self, deal_id, epic):
        """Fetch trade row from DB."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM trades WHERE deal_id = ? ORDER BY id DESC LIMIT 1",
                (deal_id,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM trades WHERE epic = ? AND status = 'CLOSED' ORDER BY id DESC LIMIT 1",
                    (epic,)
                ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[PostAnalysis] DB read error: {e}")
            return None

    def _save_analysis(self, deal_id, epic, analysis):
        """Save post-trade analysis to DB."""
        try:
            conn = sqlite3.connect(self.db_path)
            # Try by deal_id first
            conn.execute(
                "UPDATE trades SET post_analysis = ?, post_analysis_timestamp = ? WHERE deal_id = ?",
                (json.dumps(analysis), datetime.now().isoformat(), deal_id)
            )
            if conn.total_changes == 0:
                conn.execute(
                    "UPDATE trades SET post_analysis = ?, post_analysis_timestamp = ? "
                    "WHERE epic = ? AND status = 'CLOSED' ORDER BY id DESC LIMIT 1",
                    (json.dumps(analysis), datetime.now().isoformat(), epic)
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[PostAnalysis] DB save error: {e}")

    def _send_telegram(self, epic, direction, analysis):
        """Send post-trade analysis to Telegram."""
        emoji = "✅" if analysis["pl_eur"] >= 0 else "❌"
        hit_target = "✅ Ja" if analysis["did_it_happen"] == "yes" else "❌ Nej"
        label = "MIN SUCCES" if analysis["pl_eur"] >= 0 else "MIN FEJL"

        msg = (
            f"📝 <b>POST-TRADE ANALYSE: {epic}</b>\n\n"
            f"{emoji} P/L: EUR {analysis['pl_eur']:+.2f} ({analysis['pl_pct']:+.1f}%)\n"
            f"Nåede mål: {hit_target}\n\n"
            f"<b>{label}:</b> {analysis['my_error_or_success']}\n\n"
            f"<b>NÆSTE GANG:</b> {analysis['next_time']}"
        )
        self.notifier.send(msg)
