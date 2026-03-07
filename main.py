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

                # Get signal (with Reddit sentiment)
                signal_type, details = self.signals.get_signal(df, epic=epic)

                if signal_type in ("BUY", "SELL"):
                    current_price = details["close"]
                    result, error = self.executor.execute_trade(epic, signal_type, details, current_price)

                    if result:
                        # Use actual values from executor (already calculated there)
                        size = self.risk.calculate_position_size(balance["balance"], current_price)
                        stop_loss = self.risk.calculate_stop_loss(current_price, signal_type)
                        take_profit = self.risk.calculate_take_profit(current_price, signal_type)
                        self.notifier.notify_trade(signal_type, epic, size, current_price, stop_loss, take_profit, details)
                    elif error:
                        # Only log, don't spam - executor handles cooldown
                        if "Cooldown" not in error:
                            logger.info(f"{epic}: Kunne ikke handle - {error}")
                else:
                    logger.info(f"{epic}: HOLD ({details.get('reason', 'RSI=' + str(round(details.get('rsi', 0), 1)))})")

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
        self.notifier.register_command("/scan", self._cmd_scan)
        self.notifier.register_command("/sentiment", self._cmd_sentiment)
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

        # Check for duplicate position
        positions = self.client.get_positions()
        for pos in positions.get("positions", []):
            if pos["market"]["epic"] == epic:
                return f"⚠️ Du har allerede en åben position i {epic}.\nBrug /close {epic} først."

        try:
            # Get current price for stop-loss/take-profit
            prices = self.client.get_prices(epic, resolution="MINUTE_15", max_count=5)
            candles = prices.get("prices", [])
            if candles:
                last = candles[-1]
                current_price = (last["closePrice"]["bid"] + last["closePrice"]["ask"]) / 2
            else:
                current_price = None

            stop_loss = self.risk.calculate_stop_loss(current_price, "BUY") if current_price else None
            take_profit = self.risk.calculate_take_profit(current_price, "BUY") if current_price else None

            result = self.client.create_position(
                epic=epic, direction="BUY", size=size,
                stop_loss=stop_loss, take_profit=take_profit
            )
            deal_ref = result.get("dealReference", "ukendt")

            price_str = f"€{current_price:.2f}" if current_price else "afventer"
            sl_str = f"€{stop_loss:.2f}" if stop_loss else "N/A"
            tp_str = f"€{take_profit:.2f}" if take_profit else "N/A"
            logger.info(f"Manual BUY via Telegram: {epic} x{size} @ {price_str}")

            return (
                f"🟢 <b>KØBT: {epic}</b>\n"
                f"Størrelse: {size}\n"
                f"Pris: {price_str}\n"
                f"Stop-loss: {sl_str}\n"
                f"Take-profit: {tp_str}\n"
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

        # Check for duplicate position
        positions = self.client.get_positions()
        for pos in positions.get("positions", []):
            if pos["market"]["epic"] == epic:
                return f"⚠️ Du har allerede en åben position i {epic}.\nBrug /close {epic} først."

        try:
            # Get current price for stop-loss/take-profit
            prices = self.client.get_prices(epic, resolution="MINUTE_15", max_count=5)
            candles = prices.get("prices", [])
            if candles:
                last = candles[-1]
                current_price = (last["closePrice"]["bid"] + last["closePrice"]["ask"]) / 2
            else:
                current_price = None

            stop_loss = self.risk.calculate_stop_loss(current_price, "SELL") if current_price else None
            take_profit = self.risk.calculate_take_profit(current_price, "SELL") if current_price else None

            result = self.client.create_position(
                epic=epic, direction="SELL", size=size,
                stop_loss=stop_loss, take_profit=take_profit
            )
            deal_ref = result.get("dealReference", "ukendt")

            price_str = f"€{current_price:.2f}" if current_price else "afventer"
            sl_str = f"€{stop_loss:.2f}" if stop_loss else "N/A"
            tp_str = f"€{take_profit:.2f}" if take_profit else "N/A"
            logger.info(f"Manual SELL via Telegram: {epic} x{size} @ {price_str}")

            return (
                f"🔴 <b>SHORTET: {epic}</b>\n"
                f"Størrelse: {size}\n"
                f"Pris: {price_str}\n"
                f"Stop-loss: {sl_str}\n"
                f"Take-profit: {tp_str}\n"
                f"Deal: {deal_ref}"
            )
        except Exception as e:
            return f"Fejl ved salg: {e}"

    def _cmd_close(self, args=None):
        """Handle /close [EPIC|ALL] command. Close specific or all positions."""
        positions = self.client.get_positions()
        open_pos = positions.get("positions", [])

        if not open_pos:
            return "Ingen åbne positioner at lukke."

        # No args - show menu
        if not args:
            msg = "Hvilken position vil du lukke?\n\n"
            for pos in open_pos:
                epic = pos["market"]["epic"]
                direction = pos["position"]["direction"]
                size = pos["position"]["size"]
                emoji = "🟢" if direction == "BUY" else "🔴"
                msg += f"  {emoji} /close {epic} ({direction} x{size})\n"
            msg += "\n  /close ALL - Luk alle"
            return msg

        # Close ALL
        if args[0].upper() == "ALL":
            closed = 0
            errors = []
            for pos in open_pos:
                try:
                    deal_id = pos["position"]["dealId"]
                    direction = pos["position"]["direction"]
                    size = pos["position"]["size"]
                    self.client.close_position(deal_id, direction=direction, size=size)
                    closed += 1
                except Exception as e:
                    errors.append(f"{pos['market']['epic']}: {e}")
                    logger.error(f"Failed to close {pos['market']['epic']}: {e}")
            msg = f"✅ <b>{closed} positioner lukket</b>"
            if errors:
                msg += f"\n\n⚠️ Fejl:\n" + "\n".join(errors)
            return msg

        # Close specific epic
        epic_filter = args[0].upper()
        targets = [p for p in open_pos if p["market"]["epic"] == epic_filter]
        if not targets:
            return f"Ingen åben position i {epic_filter}."

        closed_epics = []
        for pos in targets:
            try:
                deal_id = pos["position"]["dealId"]
                direction = pos["position"]["direction"]
                size = pos["position"]["size"]
                epic = pos["market"]["epic"]
                self.client.close_position(deal_id, direction=direction, size=size)
                closed_epics.append(epic)
                logger.info(f"Manual close via Telegram: {epic}")
            except Exception as e:
                return f"Fejl ved lukning af {epic}: {e}"

        return f"✅ <b>LUKKET: {', '.join(closed_epics)}</b>"

    def _cmd_scan(self, args=None):
        """Handle /scan command - show signal analysis for all coins."""
        msg = "🔍 <b>Market Scan</b>\n\n"
        for epic in self.coins:
            try:
                prices = self.client.get_prices(epic, resolution=self.timeframe)
                df = self.signals.prepare_dataframe(prices)
                if df is None:
                    msg += f"❓ {epic}: Ingen data\n"
                    continue

                signal_type, details = self.signals.get_signal(df, epic=epic)
                range_pos = details.get("range_position", 0)
                rsi = details.get("rsi", 0)
                zone = details.get("zone", "?")
                range_pct = details.get("range_pct", 0)

                if signal_type == "BUY":
                    emoji = "🟢"
                elif signal_type == "SELL":
                    emoji = "🔴"
                else:
                    emoji = "⚪"

                # Zone indicator bar
                if range_pos <= 20:
                    bar = "▓░░░░"
                elif range_pos <= 40:
                    bar = "░▓░░░"
                elif range_pos <= 60:
                    bar = "░░▓░░"
                elif range_pos <= 80:
                    bar = "░░░▓░"
                else:
                    bar = "░░░░▓"

                # Sentiment indicator
                sentiment = details.get("sentiment")
                sent_str = ""
                if sentiment and sentiment.get("total_posts", 0) > 0:
                    s = sentiment["score"]
                    sent_emoji = "🐂" if s >= 55 else "🐻" if s <= 45 else "😐"
                    sent_str = f" | {sent_emoji}{s:.0f}"

                msg += f"{emoji} <b>{epic}</b> {bar}\n"
                msg += f"   Pos: {range_pos:.0f}% | RSI: {rsi:.0f} | Range: {range_pct:.1f}%{sent_str}\n"

                if signal_type != "HOLD":
                    strength = details.get("signal_strength", 0)
                    msg += f"   → {signal_type} (styrke: {strength})\n"

            except Exception as e:
                msg += f"❓ {epic}: Fejl ({e})\n"

        return msg

    def _cmd_sentiment(self, args=None):
        """Handle /sentiment [EPIC] command - show Reddit sentiment."""
        coins_to_check = [args[0].upper()] if args else self.coins

        msg = "📰 <b>Reddit Sentiment</b>\n\n"
        for epic in coins_to_check:
            try:
                sentiment = self.signals.reddit.get_sentiment(epic)
                score = sentiment["score"]
                label = sentiment["label"]
                posts = sentiment["total_posts"]

                # Sentiment bar
                filled = int(score / 10)
                bar = "🟢" * filled + "⚪" * (10 - filled)
                if score < 40:
                    bar = "🔴" * (10 - filled) + "⚪" * filled

                emoji = "🐂" if score >= 55 else "🐻" if score <= 45 else "😐"

                msg += f"{emoji} <b>{epic}</b>\n"
                msg += f"   {bar} {score}/100\n"
                msg += f"   {label} ({posts} posts)\n"

                # Top mentions
                if sentiment["top_bullish"]:
                    msg += f"   🟢 {sentiment['top_bullish'][0][:50]}\n"
                if sentiment["top_bearish"]:
                    msg += f"   🔴 {sentiment['top_bearish'][0][:50]}\n"
                msg += "\n"

            except Exception as e:
                msg += f"❓ {epic}: Fejl ({e})\n"

        return msg

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
            "/trades - Seneste 5 handler\n"
            "/scan - Scan alle coins (vis signaler)\n"
            "/sentiment - Reddit sentiment (alle coins)\n"
            "/sentiment BTCUSD - Sentiment for specifik coin\n\n"
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
