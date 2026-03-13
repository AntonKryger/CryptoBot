"""
CryptoBot AI Coach — Analyzes all bots' trade data and provides optimization recommendations.
No trading, no Capital.com connection. Read-only access to bot databases.
"""

import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.config import load_config
from src.coach.data_collector import discover_bots, load_trades, get_bot_type
from src.coach.analyzer import full_bot_analysis, cross_bot_comparison
from src.coach.coach_db import CoachDB
from src.coach.llm_advisor import LLMAdvisor
from src.coach.market_data import CoachMarketData
from src.coach.formatters import (
    format_report_summary,
    format_recommendations,
    format_bot_report,
    format_status,
)
from src.notifications.telegram_bot import TelegramNotifier

CET = ZoneInfo("Europe/Copenhagen")

logger = logging.getLogger("Coach")


def setup_logging(bot_id="COACH"):
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{bot_id}] [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"logs/cryptobot_{bot_id.lower()}.log", encoding="utf-8"),
        ],
    )


class Coach:
    """Main coach orchestrator: collects data, runs analysis, sends reports."""

    def __init__(self, config):
        self.config = config
        coach_cfg = config.get("coach", {})

        # Data directories
        self.bot_data_dir = coach_cfg.get("bot_data_dir", os.environ.get("BOT_DATA_DIR", "bot_data"))
        self.analysis_days = coach_cfg.get("analysis_days", 30)

        # Components
        self.db = CoachDB(config.get("database", {}).get("path", "data/coach.db"))
        self.advisor = LLMAdvisor(config)
        self.market_data = CoachMarketData(config)
        self.advisor.set_market_data(self.market_data)
        self.notifier = TelegramNotifier(config)

        # Discover bots
        self.bots = discover_bots(self.bot_data_dir)

        # Register Telegram commands
        self._register_commands()

    def _register_commands(self):
        """Register all coach Telegram commands."""
        self.notifier.register_command("/coach_status", self._cmd_status)
        self.notifier.register_command("/coach_analyze", self._cmd_analyze)
        self.notifier.register_command("/coach_recs", self._cmd_recs)
        self.notifier.register_command("/coach_approve", self._cmd_approve)
        self.notifier.register_command("/coach_reject", self._cmd_reject)
        self.notifier.register_command("/coach_bot", self._cmd_bot)
        self.notifier.register_command("/coach_market", self._cmd_market)
        self.notifier.register_command("/help", self._cmd_help)
        self.notifier.register_command("/start", self._cmd_help)

    # ── Telegram command handlers ─────────────────────────────────

    def _cmd_status(self, args):
        pending = self.db.get_pending_recommendations()
        latest = self.db.get_latest_report()
        return format_status(self.bots, latest, len(pending))

    def _cmd_analyze(self, args):
        """Trigger manual analysis."""
        self.notifier.send("⏳ Kører analyse...")
        thread = threading.Thread(target=self._run_analysis, args=("manual",), daemon=True)
        thread.start()
        return None  # Response sent async

    def _cmd_recs(self, args):
        pending = self.db.get_pending_recommendations()
        return format_recommendations(pending)

    def _cmd_approve(self, args):
        if not args:
            return "Brug: /coach_approve {id}"
        try:
            rec_id = int(args[0])
        except ValueError:
            return "Ugyldigt ID. Brug: /coach_approve {id}"

        rec = self.db.get_recommendation(rec_id)
        if not rec:
            return f"Anbefaling #{rec_id} ikke fundet."
        if rec["status"] != "pending":
            return f"Anbefaling #{rec_id} er allerede {rec['status']}."

        self.db.approve_recommendation(rec_id)
        return f"✅ Anbefaling #{rec_id} godkendt.\n\n⚠️ Husk at ændre config manuelt:\n  {rec.get('config_key', '?')}: {rec.get('recommended_value', '?')}"

    def _cmd_reject(self, args):
        if not args:
            return "Brug: /coach_reject {id}"
        try:
            rec_id = int(args[0])
        except ValueError:
            return "Ugyldigt ID. Brug: /coach_reject {id}"

        rec = self.db.get_recommendation(rec_id)
        if not rec:
            return f"Anbefaling #{rec_id} ikke fundet."
        if rec["status"] != "pending":
            return f"Anbefaling #{rec_id} er allerede {rec['status']}."

        self.db.reject_recommendation(rec_id)
        return f"❌ Anbefaling #{rec_id} afvist."

    def _cmd_bot(self, args):
        if not args:
            return f"Brug: /coach_bot {{id}}\nTilgængelige: {', '.join(sorted(self.bots.keys()))}"

        bot_id = args[0].lower()
        if bot_id not in self.bots:
            return f"Bot '{bot_id}' ikke fundet. Tilgængelige: {', '.join(sorted(self.bots.keys()))}"

        # Run quick analysis
        df = load_trades(bot_id, self.bots[bot_id], days=self.analysis_days)
        if df.empty:
            return f"Ingen trades fundet for {bot_id}."

        bot_type = get_bot_type(bot_id)
        stats = full_bot_analysis(df, bot_type)
        return format_bot_report(bot_id, stats)

    def _cmd_market(self, args):
        """Show current market conditions."""
        if not self.market_data.enabled:
            return "⚠️ Capital.com credentials ikke konfigureret for coach."
        try:
            snapshots = self.market_data.get_all_snapshots()
            if not snapshots:
                return "⚠️ Kunne ikke hente markedsdata."

            lines = ["📊 <b>MARKEDSOVERSIGT</b>\n"]
            for epic, snap in snapshots.items():
                change = snap.get("change_pct", 0) or 0
                bid = snap.get("bid", 0) or 0
                emoji = "🟢" if change > 0.5 else "🔴" if change < -0.5 else "⚪"
                coin = epic.replace("USD", "")
                lines.append(f"{emoji} <b>{coin}</b>: ${bid:,.2f} ({change:+.2f}%)")

            changes = [s.get("change_pct", 0) or 0 for s in snapshots.values()]
            avg = sum(changes) / len(changes) if changes else 0
            lines.append(f"\n📈 Gennemsnit: {avg:+.2f}%")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Markedsdata fejl: {e}"

    def _cmd_help(self, args):
        return (
            "🏋️ <b>AI Coach Kommandoer</b>\n\n"
            "/coach_status — Vis coach status\n"
            "/coach_analyze — Kør fuld analyse nu\n"
            "/coach_recs — Vis ventende anbefalinger\n"
            "/coach_approve {id} — Godkend anbefaling\n"
            "/coach_reject {id} — Afvis anbefaling\n"
            "/coach_bot {id} — Detaljer for en specifik bot\n"
            "/coach_market — Vis aktuelle markedspriser"
        )

    # ── Analysis engine ───────────────────────────────────────────

    def _run_analysis(self, trigger="scheduled"):
        """Run full analysis across all bots."""
        try:
            logger.info(f"[Coach] Starting analysis (trigger: {trigger})")

            # Re-discover bots (volumes may have changed)
            self.bots = discover_bots(self.bot_data_dir)
            if not self.bots:
                self.notifier.send("⚠️ Ingen bots fundet. Tjek bot_data mounts.")
                return

            now = datetime.now(CET)
            period_end = now.strftime("%Y-%m-%d")
            period_start = (now - timedelta(days=self.analysis_days)).strftime("%Y-%m-%d")

            # Load data and analyze each bot
            all_data = {}
            all_stats = {}
            bot_results = {}
            total_tokens = 0

            for bot_id, db_path in self.bots.items():
                df = load_trades(bot_id, db_path, days=self.analysis_days)
                if df.empty:
                    logger.info(f"[Coach] No trades for {bot_id}, skipping")
                    continue

                all_data[bot_id] = df
                bot_type = get_bot_type(bot_id)
                closed = df[df["status"] == "CLOSED"]
                trade_count = len(closed[closed["profit_loss"].notna()])

                if trade_count < 3:
                    logger.info(f"[Coach] Too few trades for {bot_id} ({trade_count}), skipping LLM")
                    continue

                # Pure stats
                stats = full_bot_analysis(df, bot_type)
                all_stats[bot_id] = stats

                # LLM analysis
                llm_result, tokens = self.advisor.analyze_bot(bot_id, bot_type, stats, trade_count)
                total_tokens += tokens

                if llm_result:
                    bot_results[bot_id] = llm_result

            # Cross-bot comparison (stats only, no LLM)
            cross_bot = {}
            if len(all_data) > 1:
                cross_bot = cross_bot_comparison(all_data)

            # Save report
            raw_stats = {"per_bot": all_stats, "cross_bot": cross_bot}
            report_id = self.db.save_report(
                trigger=trigger,
                period_start=period_start,
                period_end=period_end,
                raw_stats=raw_stats,
                llm_response=bot_results,
                model_used=self.advisor.model,
                token_count=total_tokens,
            )

            # Save recommendations
            rec_count = 0
            for bot_id, result in bot_results.items():
                for rec in result.get("recommendations", []):
                    self.db.save_recommendation(report_id, bot_id, rec)
                    rec_count += 1

            # Send Telegram report
            report_data = {
                "trigger": trigger,
                "bot_results": bot_results,
                "cross_bot": cross_bot,
            }
            msg = format_report_summary(report_data)
            self.notifier.send(msg)

            logger.info(f"[Coach] Analysis complete: {len(bot_results)} bots, {rec_count} recommendations, {total_tokens} tokens")

        except Exception as e:
            logger.error(f"[Coach] Analysis failed: {e}", exc_info=True)
            self.notifier.send(f"❌ Coach analyse fejlede: {e}")

    # ── Scheduling ────────────────────────────────────────────────

    def start_scheduler(self):
        """Schedule daily (23:30 CET) and weekly (Sunday 09:00 CET) analyses."""
        self._schedule_daily()
        self._schedule_weekly()

    def _schedule_daily(self):
        """Schedule next daily analysis at 23:30 CET."""
        def _schedule_next():
            now = datetime.now(CET)
            target = now.replace(hour=23, minute=30, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            delay = (target - now).total_seconds()
            logger.info(f"[Coach] Next daily: {target.strftime('%Y-%m-%d %H:%M')} CET ({delay/3600:.1f}h)")

            timer = threading.Timer(delay, _run)
            timer.daemon = True
            timer.start()

        def _run():
            self._run_analysis("daily")
            _schedule_next()

        _schedule_next()

    def _schedule_weekly(self):
        """Schedule weekly deep analysis for Sunday 09:00 CET."""
        def _schedule_next():
            now = datetime.now(CET)
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour >= 9:
                days_until_sunday = 7
            target = (now + timedelta(days=days_until_sunday)).replace(
                hour=9, minute=0, second=0, microsecond=0,
            )
            delay = (target - now).total_seconds()
            logger.info(f"[Coach] Next weekly: {target.strftime('%Y-%m-%d %H:%M')} CET ({delay/3600:.1f}h)")

            timer = threading.Timer(delay, _run)
            timer.daemon = True
            timer.start()

        def _run():
            self._run_analysis("weekly")
            _schedule_next()

        _schedule_next()


def main():
    parser = argparse.ArgumentParser(description="CryptoBot AI Coach")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    setup_logging()

    config = load_config(args.config)
    coach = Coach(config)

    logger.info(f"[Coach] Starting with {len(coach.bots)} bots: {list(coach.bots.keys())}")

    # Start Telegram listener
    coach.notifier.start_command_listener()

    # Start schedulers
    coach.start_scheduler()

    # Send startup message
    coach.notifier.send(
        f"🏋️ <b>AI Coach startet</b>\n"
        f"Bots: {', '.join(sorted(coach.bots.keys())) if coach.bots else 'Ingen fundet'}\n"
        f"Analyse: daglig 23:30 + ugentlig søndag 09:00 CET\n"
        f"Brug /coach_status for info"
    )

    # Keep alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("[Coach] Shutting down")
        coach.notifier.stop_command_listener()


if __name__ == "__main__":
    main()
