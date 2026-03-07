"""
CryptoBot - Automated crypto trading bot for Capital.com
"""

import logging
import time
import sys
import signal
from datetime import datetime

from src.config import load_config
from src.api.capital_client import CapitalClient
from src.strategy.signals import SignalEngine
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
        logging.FileHandler("logs/cryptobot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("CryptoBot")


class CryptoBot:
    def __init__(self, config_path=None):
        self.config = load_config(config_path)
        self.running = False

        # Initialize components
        self.client = CapitalClient(self.config)
        self.signals = SignalEngine(self.config)
        self.risk = RiskManager(self.config)
        self.executor = TradeExecutor(self.client, self.risk, self.config)
        self.notifier = TelegramNotifier(self.config)
        self.reporter = Reporter(self.config)

        self.coins = self.config.get("trading", {}).get("coins", [])
        self.scan_interval = self.config.get("trading", {}).get("scan_interval", 60)
        self.timeframe = self.config.get("trading", {}).get("timeframe", "MINUTE_15")

    def start(self):
        """Start the bot."""
        logger.info("=" * 50)
        logger.info("CryptoBot starter...")
        logger.info(f"Mode: {'DEMO' if self.config['capital']['demo'] else 'LIVE'}")
        logger.info(f"Coins: {', '.join(self.coins)}")
        logger.info(f"Risikoprofil: {self.config['risk'].get('profile', 'custom')}")
        logger.info("=" * 50)

        # Connect to Capital.com
        self.client.start_session()
        logger.info("Forbundet til Capital.com")

        # Get initial balance
        balance = self.client.get_account_balance()
        if balance:
            logger.info(f"Balance: €{balance['balance']:.2f}")
            self.risk.initialize(balance["balance"])
        else:
            logger.error("Kunne ikke hente balance")
            return

        self.notifier.send(
            f"🤖 <b>CryptoBot startet</b>\n"
            f"Mode: {'DEMO' if self.config['capital']['demo'] else 'LIVE'}\n"
            f"Balance: €{balance['balance']:.2f}\n"
            f"Coins: {len(self.coins)}\n"
            f"Profil: {self.config['risk'].get('profile', 'custom')}\n\n"
            f"Kommandoer: /status /trades /stop /help"
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
        """Scan all coins for trading signals."""
        logger.info(f"Scanner {len(self.coins)} coins...")

        # Check kill switch
        balance = self.client.get_account_balance()
        if balance:
            killed, reason = self.risk.check_kill_switch(balance["balance"])
            if killed:
                self.notifier.notify_kill_switch(reason)
                self.executor.close_all_positions(reason)
                self.running = False
                return

        for epic in self.coins:
            try:
                # Get price data
                prices = self.client.get_prices(epic, resolution=self.timeframe)
                df = self.signals.prepare_dataframe(prices)

                if df is None:
                    logger.warning(f"Ingen data for {epic}")
                    continue

                # Get signal
                signal_type, details = self.signals.get_signal(df)

                if signal_type in ("BUY", "SELL"):
                    current_price = details["close"]
                    result, error = self.executor.execute_trade(epic, signal_type, details, current_price)

                    if result:
                        stop_loss = self.risk.calculate_stop_loss(current_price, signal_type)
                        take_profit = self.risk.calculate_take_profit(current_price, signal_type)
                        size = self.risk.calculate_position_size(balance["balance"], current_price)
                        self.notifier.notify_trade(signal_type, epic, size, current_price, stop_loss, take_profit)
                    elif error:
                        logger.info(f"{epic}: Kunne ikke handle - {error}")
                else:
                    logger.info(f"{epic}: HOLD (RSI={details.get('rsi', 0):.1f}, VolumeSpike={details.get('volume_spike', False)})")

            except Exception as e:
                logger.error(f"Fejl ved scanning af {epic}: {e}")

    def _register_commands(self):
        """Register all Telegram command handlers."""
        self.notifier.register_command("/start", self._cmd_help)
        self.notifier.register_command("/status", self._cmd_status)
        self.notifier.register_command("/trades", self._cmd_trades)
        self.notifier.register_command("/buy", self._cmd_buy)
        self.notifier.register_command("/sell", self._cmd_sell)
        self.notifier.register_command("/close", self._cmd_close)
        self.notifier.register_command("/stop", self._cmd_stop)
        self.notifier.register_command("/help", self._cmd_help)

    def _cmd_status(self, args=None):
        """Handle /status command."""
        balance = self.client.get_account_balance()
        positions = self.client.get_positions()
        open_pos = positions.get("positions", [])
        stats = self.executor.get_stats()

        daily_pl = 0
        if balance and self.risk.daily_start_balance:
            daily_pl = balance["balance"] - self.risk.daily_start_balance

        msg = f"📊 <b>CryptoBot Status</b>\n\n"
        msg += f"💰 Balance: €{balance['balance']:.2f}\n"
        msg += f"📈 Daglig P/L: €{daily_pl:+.2f}\n"
        msg += f"🔄 Åbne positioner: {len(open_pos)}/{self.risk.max_open_positions}\n\n"

        if open_pos:
            msg += "<b>Åbne positioner:</b>\n"
            for pos in open_pos:
                epic = pos["market"]["epic"]
                direction = pos["position"]["direction"]
                pl = pos["position"].get("profit", 0)
                emoji = "🟢" if direction == "BUY" else "🔴"
                msg += f"  {emoji} {epic} ({direction}) P/L: €{pl:+.2f}\n"
            msg += "\n"

        msg += f"<b>Statistik:</b>\n"
        msg += f"  Handler i alt: {stats['total_trades']}\n"
        msg += f"  Win rate: {stats['win_rate']}%\n"
        msg += f"  Total P/L: €{stats['total_pl']:+.2f}"

        return msg

    def _cmd_trades(self, args=None):
        """Handle /trades command."""
        trades = self.executor.get_trade_history(limit=5)

        if not trades:
            return "📋 Ingen handler endnu."

        msg = "📋 <b>Seneste handler:</b>\n\n"
        for t in trades:
            direction = t["direction"]
            emoji = "🟢" if direction == "BUY" else "🔴"
            status_emoji = ""
            if t["status"] == "CLOSED":
                status_emoji = "✅" if (t.get("profit_loss") or 0) >= 0 else "❌"
            else:
                status_emoji = "⏳"

            msg += f"{status_emoji} {emoji} {t['epic']} {direction}\n"
            msg += f"   Pris: €{t['entry_price']:.2f}"
            if t.get("profit_loss") is not None:
                msg += f" | P/L: €{t['profit_loss']:+.2f}"
            msg += f" | {t['status']}\n"

        return msg

    def _cmd_buy(self, args=None):
        """Handle /buy EPIC SIZE command."""
        if not args or len(args) < 2:
            return "Brug: /buy SOLUSD 1\nEksempel: /buy BTCUSD 0.5"

        epic = args[0].upper()
        try:
            size = float(args[1])
        except ValueError:
            return f"Ugyldig størrelse: {args[1]}"

        try:
            result = self.client.create_position(epic=epic, direction="BUY", size=size)
            deal_ref = result.get("dealReference", "ukendt")

            # Get current price for notification
            balance = self.client.get_account_balance()
            positions = self.client.get_positions()
            current_price = None
            for pos in positions.get("positions", []):
                if pos["market"]["epic"] == epic:
                    current_price = pos["position"]["level"]
                    break

            price_str = f" @ €{current_price:.2f}" if current_price else ""
            logger.info(f"Manual BUY via Telegram: {epic} x{size}{price_str}")

            return (
                f"🟢 <b>KØBT: {epic}</b>\n"
                f"Størrelse: {size}\n"
                f"Pris: {price_str or 'afventer'}\n"
                f"Deal: {deal_ref}"
            )
        except Exception as e:
            return f"Fejl ved køb: {e}"

    def _cmd_sell(self, args=None):
        """Handle /sell EPIC SIZE command."""
        if not args or len(args) < 2:
            return "Brug: /sell SOLUSD 1\nEksempel: /sell BTCUSD 0.5"

        epic = args[0].upper()
        try:
            size = float(args[1])
        except ValueError:
            return f"Ugyldig størrelse: {args[1]}"

        try:
            result = self.client.create_position(epic=epic, direction="SELL", size=size)
            deal_ref = result.get("dealReference", "ukendt")

            positions = self.client.get_positions()
            current_price = None
            for pos in positions.get("positions", []):
                if pos["market"]["epic"] == epic:
                    current_price = pos["position"]["level"]
                    break

            price_str = f" @ €{current_price:.2f}" if current_price else ""
            logger.info(f"Manual SELL via Telegram: {epic} x{size}{price_str}")

            return (
                f"🔴 <b>SHORTET: {epic}</b>\n"
                f"Størrelse: {size}\n"
                f"Pris: {price_str or 'afventer'}\n"
                f"Deal: {deal_ref}"
            )
        except Exception as e:
            return f"Fejl ved salg: {e}"

    def _cmd_close(self, args=None):
        """Handle /close [EPIC] command. Close specific or all positions."""
        positions = self.client.get_positions()
        open_pos = positions.get("positions", [])

        if not open_pos:
            return "Ingen åbne positioner at lukke."

        # If an epic is specified, close only that one
        if args:
            epic_filter = args[0].upper()
            targets = [p for p in open_pos if p["market"]["epic"] == epic_filter]
            if not targets:
                return f"Ingen åben position i {epic_filter}."
        else:
            # Show positions and ask to specify
            msg = "Hvilken position vil du lukke?\n\n"
            for pos in open_pos:
                epic = pos["market"]["epic"]
                direction = pos["position"]["direction"]
                size = pos["position"]["size"]
                msg += f"  /close {epic}\n"
            msg += "\n  /close ALL - Luk alle"
            return msg

        # Close ALL
        if args and args[0].upper() == "ALL":
            closed = 0
            for pos in open_pos:
                try:
                    deal_id = pos["position"]["dealId"]
                    self.client.close_position(deal_id)
                    closed += 1
                except Exception as e:
                    logger.error(f"Failed to close {pos['market']['epic']}: {e}")
            return f"✅ <b>{closed} positioner lukket</b>"

        # Close specific
        closed_epics = []
        for pos in targets:
            try:
                deal_id = pos["position"]["dealId"]
                epic = pos["market"]["epic"]
                self.client.close_position(deal_id)
                closed_epics.append(epic)
                logger.info(f"Manual close via Telegram: {epic}")
            except Exception as e:
                return f"Fejl ved lukning af {epic}: {e}"

        return f"✅ <b>LUKKET: {', '.join(closed_epics)}</b>"

    def _cmd_stop(self, args=None):
        """Handle /stop command."""
        self.running = False
        return "⏹ <b>CryptoBot stopper...</b>\nBotten lukker ned efter denne scan-cyklus."

    def _cmd_help(self, args=None):
        """Handle /help command."""
        return (
            "🤖 <b>CryptoBot Kommandoer</b>\n\n"
            "<b>Info:</b>\n"
            "/status - Balance, positioner og statistik\n"
            "/trades - Seneste 5 handler\n\n"
            "<b>Handel:</b>\n"
            "/buy EPIC SIZE - Køb (fx /buy SOLUSD 1)\n"
            "/sell EPIC SIZE - Short (fx /sell BTCUSD 0.5)\n"
            "/close EPIC - Luk position (fx /close SOLUSD)\n"
            "/close ALL - Luk alle positioner\n\n"
            "<b>System:</b>\n"
            "/stop - Stop botten\n"
            "/help - Vis denne besked"
        )

    def stop(self):
        """Stop the bot gracefully."""
        self.running = False
        self.notifier.stop_command_listener()
        logger.info("CryptoBot stopper...")

        balance = self.client.get_account_balance()
        stats = self.executor.get_stats()

        self.notifier.send(
            f"⏹ <b>CryptoBot stoppet</b>\n"
            f"Balance: €{balance['balance']:.2f}\n"
            f"Handler i alt: {stats['total_trades']}\n"
            f"Win rate: {stats['win_rate']}%\n"
            f"Total P/L: €{stats['total_pl']:.2f}"
        )

        logger.info("CryptoBot stoppet")

    def status(self):
        """Print current status."""
        print(self.reporter.get_summary())


def main():
    bot = CryptoBot()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        bot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    bot.start()


if __name__ == "__main__":
    main()
