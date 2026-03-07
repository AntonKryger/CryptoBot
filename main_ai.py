"""
CryptoBot AI - AI-powered crypto trading bot using Claude for analysis.
Runs alongside the original rule-based CryptoBot for A/B comparison.
"""

import logging
import time
import sys
import signal
from datetime import datetime

from src.config import load_config
from src.api.capital_client import CapitalClient
from src.strategy.signals import SignalEngine
from src.strategy.ai_analyst import AIAnalyst
from src.risk.manager import RiskManager
from src.executor.trade_executor import TradeExecutor
from src.notifications.telegram_bot import TelegramNotifier
from src.analysis.reporter import Reporter

# ── Logging setup ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/cryptobot_ai.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("CryptoBot-AI")


class CryptoBotAI:
    def __init__(self, config_path=None):
        self.config = load_config(config_path)
        self.running = False

        # Initialize components
        self.client = CapitalClient(self.config)
        self.signals = SignalEngine(self.config)  # reuse for indicators + sentiment
        self.ai = AIAnalyst(self.config)
        self.risk = RiskManager(self.config)
        self.executor = TradeExecutor(self.client, self.risk, self.config)
        self.notifier = TelegramNotifier(self.config)
        self.reporter = Reporter(self.config)

        self.coins = self.config.get("trading", {}).get("coins", [])
        self.scan_interval = self.config.get("trading", {}).get("scan_interval", 60)
        self.timeframe = self.config.get("trading", {}).get("timeframe", "MINUTE_15")

    def start(self):
        """Start the AI bot."""
        logger.info("=" * 50)
        logger.info("CryptoBot AI starter...")
        logger.info(f"Mode: {'DEMO' if self.config['capital']['demo'] else 'LIVE'}")
        logger.info(f"Konto: {self.config['capital'].get('account_name', 'default')}")
        logger.info(f"AI Model: {self.config.get('ai', {}).get('model', 'claude-haiku-4-5-20251001')}")
        logger.info(f"Coins: {', '.join(self.coins)}")
        logger.info("=" * 50)

        # Connect to Capital.com
        self.client.start_session()
        logger.info("Forbundet til Capital.com")

        # Get initial balance
        balance = self.client.get_account_balance()
        if balance:
            logger.info(f"Balance: EUR {balance['balance']:.2f}")
            self.risk.initialize(balance["balance"])
        else:
            logger.error("Kunne ikke hente balance")
            return

        self.notifier.send(
            f"🧠 <b>CryptoBot AI startet</b>\n"
            f"Mode: {'DEMO' if self.config['capital']['demo'] else 'LIVE'}\n"
            f"Konto: {self.config['capital'].get('account_name', 'default')}\n"
            f"Balance: EUR {balance['balance']:.2f}\n"
            f"AI Model: {self.ai.model}\n"
            f"Min confidence: {self.ai.min_confidence}/10\n"
            f"Coins: {len(self.coins)}\n\n"
            f"Kommandoer: /ai_status /ai_trades /ai_stop /ai_help"
        )

        # Register Telegram commands
        self._register_commands()
        self.notifier.start_command_listener()

        self.running = True
        self._run_loop()

    def _run_loop(self):
        """Main trading loop."""
        while self.running:
            try:
                self._scan_cycle()
                self.executor.check_trailing_stops()
                time.sleep(self.scan_interval)
            except KeyboardInterrupt:
                logger.info("Stop signal modtaget")
                self.stop()
                break
            except Exception as e:
                logger.error(f"Fejl i hovedloop: {e}", exc_info=True)
                time.sleep(10)

    def _scan_cycle(self):
        """Scan all coins using AI analysis."""
        logger.info(f"[AI] Scanner {len(self.coins)} coins...")

        # Check kill switch
        balance = self.client.get_account_balance()
        if balance:
            killed, reason = self.risk.check_kill_switch(balance["balance"])
            if killed:
                self.notifier.send(f"🚨 <b>[AI] KILL SWITCH</b>\n{reason}")
                self.executor.close_all_positions(reason)
                self.running = False
                return

        for epic in self.coins:
            try:
                # Get price data
                prices = self.client.get_prices(epic, resolution=self.timeframe)
                df = self.signals.prepare_dataframe(prices)

                if df is None:
                    logger.warning(f"[AI] Ingen data for {epic}")
                    continue

                # Calculate indicators (reuse existing logic)
                df = self.signals.calculate_indicators(df)

                # Get sentiment data
                sentiment_data = None
                try:
                    sentiment_data = self.signals.reddit.get_sentiment(epic)
                except Exception as e:
                    logger.warning(f"[AI] Sentiment failed for {epic}: {e}")

                # AI analysis
                signal_type, details = self.ai.analyze(epic, df, sentiment_data)

                if signal_type in ("BUY", "SELL"):
                    current_price = details["close"]
                    result, error = self.executor.execute_trade(epic, signal_type, details, current_price)

                    if result:
                        size = self.risk.calculate_position_size(balance["balance"], current_price)
                        stop_loss = self.risk.calculate_stop_loss(current_price, signal_type)
                        take_profit = self.risk.calculate_take_profit(current_price, signal_type)
                        self._notify_ai_trade(signal_type, epic, size, current_price, stop_loss, take_profit, details)
                    elif error and "Cooldown" not in error:
                        logger.info(f"[AI] {epic}: Kunne ikke handle - {error}")
                else:
                    reason = details.get("reason", "")
                    conf = details.get("ai_confidence", "?")
                    logger.info(f"[AI] {epic}: HOLD (confidence: {conf}) {reason[:60]}")

            except Exception as e:
                logger.error(f"[AI] Fejl ved scanning af {epic}: {e}")

    def _notify_ai_trade(self, direction, epic, size, price, stop_loss, take_profit, details):
        """Send AI trade notification with reasoning."""
        emoji = "🟢" if direction == "BUY" else "🔴"
        action = "LONG" if direction == "BUY" else "SHORT"
        confidence = details.get("ai_confidence", "?")
        reasoning = details.get("ai_reasoning", "")[:200]

        msg = (
            f"🧠 {emoji} <b>[AI] {action}: {epic}</b>\n"
            f"Pris: EUR {price:.4f}\n"
            f"Stoerrelse: {size}\n"
            f"Stop-loss: EUR {stop_loss:.4f}\n"
            f"Take-profit: EUR {take_profit:.4f}\n\n"
            f"🤖 <b>AI Analyse (confidence: {confidence}/10):</b>\n"
            f"{reasoning}"
        )
        self.notifier.send(msg)

    def _register_commands(self):
        """Register Telegram command handlers."""
        # /ai_ prefixed commands
        self.notifier.register_command("/ai_status", self._cmd_status)
        self.notifier.register_command("/ai_trades", self._cmd_trades)
        self.notifier.register_command("/ai_scan", self._cmd_scan)
        self.notifier.register_command("/ai_stop", self._cmd_stop)
        self.notifier.register_command("/ai_help", self._cmd_help)
        self.notifier.register_command("/ai_close", self._cmd_close)
        # Short versions (this bot has its own Telegram bot)
        self.notifier.register_command("/start", self._cmd_help)
        self.notifier.register_command("/help", self._cmd_help)
        self.notifier.register_command("/status", self._cmd_status)
        self.notifier.register_command("/trades", self._cmd_trades)
        self.notifier.register_command("/scan", self._cmd_scan)
        self.notifier.register_command("/stop", self._cmd_stop)
        self.notifier.register_command("/close", self._cmd_close)

    def _cmd_status(self, args=None):
        balance = self.client.get_account_balance()
        positions = self.client.get_positions()
        open_pos = positions.get("positions", [])
        stats = self.executor.get_stats()

        daily_pl = 0
        if balance and self.risk.daily_start_balance:
            daily_pl = balance["balance"] - self.risk.daily_start_balance

        msg = f"🧠 <b>CryptoBot AI Status</b>\n\n"
        msg += f"💰 Balance: EUR {balance['balance']:.2f}\n"
        msg += f"📈 Daglig P/L: EUR {daily_pl:+.2f}\n"
        msg += f"🔄 Aabne positioner: {len(open_pos)}\n"
        msg += f"🤖 Model: {self.ai.model}\n\n"

        if open_pos:
            msg += "<b>Aabne positioner:</b>\n"
            for pos in open_pos:
                epic = pos["market"]["epic"]
                direction = pos["position"]["direction"]
                pl = pos["position"].get("profit", 0)
                emoji = "🟢" if direction == "BUY" else "🔴"
                msg += f"  {emoji} {epic} ({direction}) P/L: EUR {pl:+.2f}\n"

        msg += f"\n<b>Statistik:</b>\n"
        msg += f"  Handler: {stats['total_trades']} | Win: {stats['win_rate']}%\n"
        msg += f"  Total P/L: EUR {stats['total_pl']:+.2f}"
        return msg

    def _cmd_trades(self, args=None):
        trades = self.executor.get_trade_history(limit=5)
        if not trades:
            return "🧠 Ingen AI-handler endnu."

        msg = "🧠 <b>Seneste AI-handler:</b>\n\n"
        for t in trades:
            emoji = "🟢" if t["direction"] == "BUY" else "🔴"
            msg += f"{emoji} {t['epic']} {t['direction']} @ EUR {t['entry_price']:.2f}"
            if t.get("profit_loss") is not None:
                msg += f" | P/L: EUR {t['profit_loss']:+.2f}"
            msg += f" | {t['status']}\n"
        return msg

    def _cmd_scan(self, args=None):
        """AI scan - analyze all coins."""
        msg = "🧠 <b>AI Market Scan</b>\n\n"
        for epic in self.coins:
            try:
                prices = self.client.get_prices(epic, resolution=self.timeframe)
                df = self.signals.prepare_dataframe(prices)
                if df is None:
                    msg += f"❓ {epic}: Ingen data\n"
                    continue

                df = self.signals.calculate_indicators(df)
                sentiment = None
                try:
                    sentiment = self.signals.reddit.get_sentiment(epic)
                except Exception:
                    pass

                signal_type, details = self.ai.analyze(epic, df, sentiment)
                confidence = details.get("ai_confidence", "?")
                reasoning = details.get("ai_reasoning", "")[:60]

                if signal_type == "BUY":
                    emoji = "🟢"
                elif signal_type == "SELL":
                    emoji = "🔴"
                else:
                    emoji = "⚪"

                msg += f"{emoji} <b>{epic}</b> (conf: {confidence}/10)\n"
                msg += f"   {reasoning}\n\n"

            except Exception as e:
                msg += f"❓ {epic}: Fejl ({e})\n"
        return msg

    def _cmd_close(self, args=None):
        positions = self.client.get_positions()
        open_pos = positions.get("positions", [])
        if not open_pos:
            return "Ingen aabne positioner."

        if not args:
            msg = "Hvilken position?\n\n"
            for pos in open_pos:
                epic = pos["market"]["epic"]
                msg += f"  /ai_close {epic}\n"
            msg += "\n  /ai_close ALL"
            return msg

        if args[0].upper() == "ALL":
            closed = self.executor.close_all_positions("AI manual close")
            return f"✅ {closed} positioner lukket"

        epic = args[0].upper()
        for pos in open_pos:
            if pos["market"]["epic"] == epic:
                deal_id = pos["position"]["dealId"]
                direction = pos["position"]["direction"]
                size = pos["position"]["size"]
                self.client.close_position(deal_id, direction=direction, size=size)
                return f"✅ Lukket {epic}"
        return f"Ingen position i {epic}"

    def _cmd_stop(self, args=None):
        self.running = False
        return "🧠 <b>CryptoBot AI stopper...</b>"

    def _cmd_help(self, args=None):
        return (
            "🧠 <b>CryptoBot AI Kommandoer</b>\n\n"
            "/ai_status - Status og positioner\n"
            "/ai_trades - Seneste handler\n"
            "/ai_scan - AI-analyse af alle coins\n"
            "/ai_close EPIC - Luk position\n"
            "/ai_close ALL - Luk alle\n"
            "/ai_stop - Stop AI-botten\n"
            "/ai_help - Denne besked"
        )

    def stop(self):
        self.running = False
        self.notifier.stop_command_listener()
        logger.info("CryptoBot AI stopper...")

        balance = self.client.get_account_balance()
        stats = self.executor.get_stats()

        self.notifier.send(
            f"🧠 <b>CryptoBot AI stoppet</b>\n"
            f"Balance: EUR {balance['balance']:.2f}\n"
            f"Handler: {stats['total_trades']} | Win: {stats['win_rate']}%\n"
            f"Total P/L: EUR {stats['total_pl']:.2f}"
        )


def main():
    bot = CryptoBotAI(config_path="config_ai.yaml")

    def signal_handler(sig, frame):
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    bot.start()


if __name__ == "__main__":
    main()
