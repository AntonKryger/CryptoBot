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
            f"Profil: {self.config['risk'].get('profile', 'custom')}"
        )

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

    def stop(self):
        """Stop the bot gracefully."""
        self.running = False
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
