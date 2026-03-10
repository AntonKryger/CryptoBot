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
from src.strategy.regime_detector import RegimeDetector
from src.strategy.time_bias import TimeBias
from src.risk.manager import RiskManager
from src.executor.trade_executor import TradeExecutor
from src.executor.position_watchdog import PositionWatchdog
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
        self.regime = RegimeDetector(self.client, self.config)
        self.time_bias = TimeBias(self.client)
        self.signals.regime_detector = self.regime
        self.signals.time_bias = self.time_bias
        self.risk = RiskManager(self.config)
        self.executor = TradeExecutor(self.client, self.risk, self.config)
        self.notifier = TelegramNotifier(self.config)
        self.watchdog = PositionWatchdog(self.client, self.risk, self.notifier, self.config)
        self.reporter = Reporter(self.config)

        # Connect watchdog to AI/signals for cycle trading, scale-in, and cooldown
        self.watchdog.ai_analyst = self.ai
        self.watchdog.signal_engine = self.signals
        self.watchdog.executor = self.executor
        self.watchdog.time_bias = self.time_bias  # For sentiment-based night mode
        # Give AI access to trade history for feedback loop
        self.ai.trade_executor = self.executor
        self.watchdog._cycle_callback = self._handle_cycle_trade
        self.watchdog._scale_in_callback = self._handle_scale_in

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
            f"Watchdog: hver {self.watchdog.check_interval}s\n"
            f"Break-even: +{self.watchdog.breakeven_trigger_pct}%\n"
            f"Trailing: +{self.watchdog.trailing_trigger_pct}% @ {self.watchdog.trailing_atr_mult}x ATR\n"
            f"Delvis profit: {self.watchdog.partial_profit_pct}% -> luk {self.watchdog.partial_close_ratio*100:.0f}%\n\n"
            f"Kommandoer: /ai_status /ai_trades /ai_stop /ai_debug /ai_help"
        )

        # Register Telegram commands
        self._register_commands()
        self.notifier.start_command_listener()

        # Start position watchdog (fast monitoring every 10-15 sec)
        self.watchdog.start()

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
        """Scan all coins using AI analysis. Two-pass system:
        Pass 1: Analyze all coins, collect signals
        Pass 2: Allocate capital by confidence, execute trades
        """
        logger.info(f"[AI] Scanner {len(self.coins)} coins...")

        # Check kill switch
        balance = self.client.get_account_balance()
        if not balance:
            logger.error("[AI] Kunne ikke hente balance")
            return

        current_balance = balance["balance"]
        killed, reason = self.risk.check_kill_switch(current_balance)
        if killed:
            self.notifier.send(f"🚨 <b>[AI] KILL SWITCH</b>\n{reason}")
            self.executor.close_all_positions(reason)
            self.running = False
            return

        # Check if markets are open
        markets_open, market_status = self.client.are_crypto_markets_open()
        if not markets_open:
            logger.info(f"[AI] Crypto markeder er lukket ({market_status}) - springer scan over")
            return

        # Check how many positions are already open
        positions = self.client.get_positions()
        open_positions = positions.get("positions", [])
        open_epics = {p["market"]["epic"] for p in open_positions}

        can_trade, reason = self.risk.can_open_position(len(open_positions), current_balance, current_balance)
        if not can_trade:
            logger.info(f"[AI] Kan ikke åbne flere positioner: {reason}")
            return

        # Calculate available margin (total - used)
        available = balance.get("available", current_balance)
        logger.info(f"[AI] Balance: EUR {current_balance:.0f} | Available: EUR {available:.0f} | Open: {len(open_positions)}")

        # Snapshot balance for dashboard + reconcile stale trades
        self.executor.snapshot_balance(balance, bot_name="ai")
        self.executor.reconcile_closed_trades()

        # ── PASS 1: Analyze all coins, collect trade signals ──
        trade_signals = []

        for epic in self.coins:
            try:
                # Skip if already have position
                if epic in open_epics:
                    logger.info(f"[AI] {epic}: Allerede åben position, springer over")
                    continue

                # Skip if on cooldown (recently traded or cycle trade pending)
                if epic in self.executor._recently_traded:
                    last = self.executor._recently_traded[epic]
                    elapsed = (datetime.now() - last).total_seconds()
                    if elapsed < self.executor._trade_cooldown:
                        logger.info(f"[AI] {epic}: Cooldown ({int(self.executor._trade_cooldown - elapsed)}s)")
                        continue

                # Get price data
                prices = self.client.get_prices(epic, resolution=self.timeframe)
                df = self.signals.prepare_dataframe(prices)

                if df is None:
                    logger.warning(f"[AI] Ingen data for {epic}")
                    continue

                # Calculate indicators
                df = self.signals.calculate_indicators(df)

                # Feed ATR to watchdog
                latest_atr = df.iloc[-1].get("atr_pct", 2.0)
                self.watchdog.update_atr(epic, latest_atr)

                # Get regime and time bias
                regime, adx = self.regime.get_regime(epic)
                time_bias_label, time_bias_return, _ = self.time_bias.get_bias(epic)
                regime_data = {
                    "regime": regime, "adx": adx,
                    "time_bias": time_bias_label, "time_bias_return": time_bias_return,
                }

                # Get sentiment data
                sentiment_data = None
                try:
                    sentiment_data = self.signals.reddit.get_sentiment(epic)
                except Exception as e:
                    logger.warning(f"[AI] Sentiment failed for {epic}: {e}")

                # Run rule-based signal engine first
                rule_signal_type, rule_details = self.signals.get_signal(df, epic=epic)
                rule_score = rule_details.get("buy_score") or rule_details.get("sell_score") or 0
                rule_reasons = rule_details.get("buy_reasons") or rule_details.get("sell_reasons") or rule_details.get("reasons", [])
                if not rule_reasons and rule_details.get("reason"):
                    rule_reasons = [rule_details["reason"]]

                rule_signal = {
                    "signal": rule_signal_type,
                    "score": rule_score,
                    "reasons": rule_reasons,
                }
                logger.info(f"[AI] {epic}: Rule-based bot says {rule_signal_type} (score={rule_score}) | Regime: {regime} (ADX: {adx:.1f})")

                # AI analysis with regime data
                signal_type, details = self.ai.analyze(epic, df, sentiment_data, rule_signal=rule_signal, regime_data=regime_data)

                if signal_type in ("BUY", "SELL"):
                    confidence = details.get("ai_confidence", 5)
                    trade_signals.append((epic, signal_type, confidence, details))
                    logger.info(f"[AI] {epic}: {signal_type} (confidence: {confidence}) -> til allokering")
                else:
                    reason = details.get("reason", "")
                    conf = details.get("ai_confidence", "?")
                    logger.info(f"[AI] {epic}: HOLD (confidence: {conf}) {reason[:60]}")

            except Exception as e:
                logger.error(f"[AI] Fejl ved scanning af {epic}: {e}")

        # ── PASS 2: Allocate capital and execute trades ──
        if not trade_signals:
            logger.info("[AI] Ingen trade-signaler denne runde")
            return

        logger.info(f"[AI] {len(trade_signals)} signaler fundet, allokerer kapital...")
        allocations = self.risk.allocate_capital(trade_signals, available)

        for epic, signal_type, allocated_amount, details in allocations:
            try:
                current_price = details["close"]
                size = self.risk.calculate_position_size(allocated_amount, current_price)

                # Use ATR-based SL
                atr_pct = details.get("atr_pct", 0)
                if atr_pct > 0:
                    stop_loss = self.risk.calculate_atr_stop_loss(current_price, signal_type, atr_pct)
                else:
                    stop_loss = self.risk.calculate_stop_loss(current_price, signal_type)
                take_profit = self.risk.calculate_take_profit(current_price, signal_type, atr_pct)

                cat = self.risk.get_coin_category(epic)
                logger.info(
                    f"[AI] Executing {signal_type} {epic} ({cat}): "
                    f"size={size}, alloc=EUR {allocated_amount:.0f}"
                )

                result = self.client.create_position(
                    epic=epic,
                    direction=signal_type,
                    size=size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

                if result:
                    # Log to database
                    self.executor._log_trade(epic, signal_type, size, current_price,
                                             stop_loss, take_profit, result, details)
                    self.executor._recently_traded[epic] = __import__('datetime').datetime.now()

                    # Track in watchdog for max hold time and scale-in
                    deal_id = result.get("dealReference") or result.get("dealId", "")
                    confidence = details.get("ai_confidence", 5)
                    self.watchdog.track_entry(deal_id, epic, confidence)

                    self._notify_ai_trade(signal_type, epic, size, current_price,
                                          stop_loss, take_profit, details, allocated_amount)

            except Exception as e:
                logger.error(f"[AI] Trade execution failed for {epic}: {e}")

    def _handle_cycle_trade(self, epic, opposite_direction):
        """Called by watchdog when a position closes - check for reversal trade."""
        try:
            # Set cooldown immediately to prevent scan cycle from also opening
            self.executor._recently_traded[epic] = datetime.now()

            logger.info(f"[Cycle] Analyzing {epic} for {opposite_direction} reversal...")

            prices = self.client.get_prices(epic, resolution=self.timeframe)
            df = self.signals.prepare_dataframe(prices)
            if df is None:
                return

            df = self.signals.calculate_indicators(df)

            # Get regime
            regime, adx = self.regime.get_regime(epic)
            regime_data = {"regime": regime, "adx": adx}

            # Get sentiment
            sentiment_data = None
            try:
                sentiment_data = self.signals.reddit.get_sentiment(epic)
            except Exception:
                pass

            # AI analysis for reversal
            signal_type, details = self.ai.analyze(epic, df, sentiment_data, regime_data=regime_data)
            confidence = details.get("ai_confidence", 0)

            if signal_type != opposite_direction:
                logger.info(f"[Cycle] {epic}: AI says {signal_type}, not {opposite_direction}. Skipping.")
                return

            if confidence < 7:
                logger.info(f"[Cycle] {epic}: Confidence {confidence} < 7. Skipping reversal.")
                return

            # Execute cycle trade
            balance = self.client.get_account_balance()
            if not balance:
                return

            available = balance.get("available", balance["balance"])
            current_price = details["close"]
            atr_pct = details.get("atr_pct", 0)

            # Max-sized for confidence >= 9
            if confidence >= 9:
                allocated = available * 0.25  # 25% for max confidence cycle trade
            else:
                allocated = available * 0.15  # 15% for standard cycle trade

            size = self.risk.calculate_position_size(allocated, current_price)
            if atr_pct > 0:
                stop_loss = self.risk.calculate_atr_stop_loss(current_price, signal_type, atr_pct)
            else:
                stop_loss = self.risk.calculate_stop_loss(current_price, signal_type)
            take_profit = self.risk.calculate_take_profit(current_price, signal_type, atr_pct)

            result = self.client.create_position(
                epic=epic, direction=signal_type, size=size,
                stop_loss=stop_loss, take_profit=take_profit,
            )

            if result:
                self.executor._log_trade(epic, signal_type, size, current_price,
                                         stop_loss, take_profit, result, details)
                deal_id = result.get("dealReference") or result.get("dealId", "")
                self.watchdog.track_entry(deal_id, epic, confidence)

                self.notifier.send(
                    f"🔄 <b>Cycle trade: {epic}</b>\n"
                    f"{'🟢 LONG' if signal_type == 'BUY' else '🔴 SHORT'}\n"
                    f"Confidence: {confidence}/10\n"
                    f"Pris: EUR {current_price:.4f}\n"
                    f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}"
                )
                logger.info(f"[Cycle] {epic}: {signal_type} executed (conf={confidence})")

        except Exception as e:
            logger.error(f"[Cycle] Error for {epic}: {e}")

    def _handle_scale_in(self, epic, direction, deal_id, entry_confidence, pos):
        """Called by watchdog to check if scale-in is appropriate."""
        try:
            # Re-evaluate with AI
            prices = self.client.get_prices(epic, resolution=self.timeframe)
            df = self.signals.prepare_dataframe(prices)
            if df is None:
                return

            df = self.signals.calculate_indicators(df)

            regime, adx = self.regime.get_regime(epic)
            regime_data = {"regime": regime, "adx": adx}

            signal_type, details = self.ai.analyze(epic, df, regime_data=regime_data)
            new_confidence = details.get("ai_confidence", 0)

            # Only scale-in if new confidence >= entry confidence + 2
            if signal_type != direction or new_confidence < entry_confidence + 2:
                return

            # Scale-in: 50% of original position
            original_size = pos["position"]["size"]
            scale_size = round(original_size * 0.5, 4)
            if scale_size <= 0:
                return

            current_price = details["close"]
            atr_pct = details.get("atr_pct", 0)
            if atr_pct > 0:
                stop_loss = self.risk.calculate_atr_stop_loss(current_price, direction, atr_pct)
            else:
                stop_loss = self.risk.calculate_stop_loss(current_price, direction)
            take_profit = self.risk.calculate_take_profit(current_price, direction, atr_pct)

            result = self.client.create_position(
                epic=epic, direction=direction, size=scale_size,
                stop_loss=stop_loss, take_profit=take_profit,
            )

            if result:
                self.watchdog.mark_scale_in_done(deal_id)
                new_deal_id = result.get("dealReference") or result.get("dealId", "")
                self.watchdog.track_entry(new_deal_id, epic, new_confidence)
                self.executor._log_trade(epic, direction, scale_size, current_price,
                                         stop_loss, take_profit, result, details)

                self.notifier.send(
                    f"📈 <b>Scale-in: {epic}</b>\n"
                    f"Original conf: {entry_confidence} -> Ny conf: {new_confidence}\n"
                    f"Tilføjet: {scale_size} (50% af original)\n"
                    f"Pris: EUR {current_price:.4f}\n"
                    f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}"
                )
                logger.info(f"[Scale-in] {epic}: +{scale_size} (conf {entry_confidence}->{new_confidence})")

        except Exception as e:
            logger.error(f"[Scale-in] Error for {epic}: {e}")

    def _notify_ai_trade(self, direction, epic, size, price, stop_loss, take_profit, details, allocated_amount=None):
        """Send AI trade notification with reasoning."""
        emoji = "🟢" if direction == "BUY" else "🔴"
        action = "LONG" if direction == "BUY" else "SHORT"
        confidence = details.get("ai_confidence", "?")
        reasoning = details.get("ai_reasoning", "")[:500]
        agreement = details.get("bot_agreement")
        cat = self.risk.get_coin_category(epic)
        regime = details.get("regime", "?")

        msg = (
            f"🧠 {emoji} <b>[AI] {action}: {epic}</b> ({cat})\n"
            f"Pris: EUR {price:.4f}\n"
            f"Stoerrelse: {size}\n"
        )
        if allocated_amount:
            msg += f"Allokeret: EUR {allocated_amount:.0f}\n"
        msg += (
            f"Stop-loss: EUR {stop_loss:.5f}\n"
            f"Take-profit: EUR {take_profit:.4f}\n"
            f"Regime: {regime}\n\n"
            f"🤖 <b>AI Analyse (confidence: {confidence}/10):</b>\n"
            f"{reasoning}"
        )
        if agreement:
            agree_text = "FULD ENIGHED" if agreement is True else "DELVIS ENIGHED"
            msg += f"\n\n🤝 <b>Bot samarbejde: {agree_text}</b>"
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
        self.notifier.register_command("/ai_debug", self._cmd_debug)
        # Short versions (this bot has its own Telegram bot)
        self.notifier.register_command("/start", self._cmd_help)
        self.notifier.register_command("/help", self._cmd_help)
        self.notifier.register_command("/status", self._cmd_status)
        self.notifier.register_command("/trades", self._cmd_trades)
        self.notifier.register_command("/scan", self._cmd_scan)
        self.notifier.register_command("/report", self._cmd_report)
        self.notifier.register_command("/stop", self._cmd_stop)
        self.notifier.register_command("/close", self._cmd_close)
        self.notifier.register_command("/debug", self._cmd_debug)

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
                deal_id = pos["position"]["dealId"]
                emoji = "🟢" if direction == "BUY" else "🔴"

                # Show hold time
                entry_time = self.watchdog._entry_times.get(deal_id)
                hold_str = ""
                if entry_time:
                    hold_hours = (datetime.now() - entry_time).total_seconds() / 3600
                    max_h = self.risk.get_max_hold_hours(epic)
                    hold_str = f" | ⏱{hold_hours:.1f}/{max_h}h"

                msg += f"  {emoji} {epic} ({direction}) P/L: EUR {pl:+.2f}{hold_str}\n"

        msg += f"\n<b>Statistik:</b>\n"
        msg += f"  Handler: {stats['total_trades']} | Win: {stats['win_rate']}%\n"
        msg += f"  Total P/L: EUR {stats['total_pl']:+.2f}\n"

        wd = self.watchdog.get_status()
        msg += f"\n<b>Watchdog:</b> {'Aktiv' if wd['running'] else 'Stoppet'}\n"
        msg += f"  Interval: {wd['interval']}s | Tracked: {wd['tracked_positions']}\n"
        msg += f"  Break-even: {wd['breakeven_set']} | Delvis profit: {wd['partial_taken']}\n"
        msg += f"  TP udvidelser: {sum(wd['tp_extensions'].values())} | Scale-ins: {wd['scale_ins']}"
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

                # Get regime and time bias
                regime, adx = self.regime.get_regime(epic)
                time_bias_label, time_bias_return, _ = self.time_bias.get_bias(epic)
                regime_data = {
                    "regime": regime, "adx": adx,
                    "time_bias": time_bias_label, "time_bias_return": time_bias_return,
                }

                # Get rule-based signal
                rule_sig, rule_det = self.signals.get_signal(df, epic=epic)
                rule_sc = rule_det.get("buy_score") or rule_det.get("sell_score") or 0
                rule_rs = rule_det.get("buy_reasons") or rule_det.get("sell_reasons") or []
                rule_data = {"signal": rule_sig, "score": rule_sc, "reasons": rule_rs}

                signal_type, details = self.ai.analyze(epic, df, sentiment, rule_signal=rule_data, regime_data=regime_data)
                confidence = details.get("ai_confidence", "?")
                reasoning = details.get("ai_reasoning", "")[:60]

                if signal_type == "BUY":
                    emoji = "🟢"
                elif signal_type == "SELL":
                    emoji = "🔴"
                else:
                    emoji = "⚪"

                # Show both signals + regime
                rule_emoji = "🟢" if rule_sig == "BUY" else "🔴" if rule_sig == "SELL" else "⚪"
                regime_short = regime[:3] if regime else "?"
                msg += f"{emoji} <b>{epic}</b> (AI:{confidence}/10 | Bot:{rule_emoji}{rule_sc}p | {regime_short} ADX:{adx:.0f})\n"
                msg += f"   {reasoning}\n\n"

            except Exception as e:
                msg += f"❓ {epic}: Fejl ({e})\n"
        return msg

    def _cmd_report(self, args=None):
        """Generate detailed AI analysis report for a coin."""
        if not args:
            return "Brug: /report BTCUSD\nVaelg en coin at analysere."

        epic = args[0].upper()
        if epic not in self.coins:
            return f"{epic} er ikke i coin-listen.\nTilgaengelige: {', '.join(self.coins)}"

        try:
            self.notifier.send(f"🧠 Genererer rapport for {epic}...")

            prices = self.client.get_prices(epic, resolution=self.timeframe)
            df = self.signals.prepare_dataframe(prices)
            if df is None:
                return f"Ingen data for {epic}"

            df = self.signals.calculate_indicators(df)

            sentiment = None
            try:
                sentiment = self.signals.reddit.get_sentiment(epic)
            except Exception:
                pass

            # Get regime
            regime, adx = self.regime.get_regime(epic)
            regime_data = {"regime": regime, "adx": adx}

            # Get rule-based signal for report context
            rule_sig, rule_det = self.signals.get_signal(df, epic=epic)
            rule_sc = rule_det.get("buy_score") or rule_det.get("sell_score") or 0
            rule_rs = rule_det.get("buy_reasons") or rule_det.get("sell_reasons") or []
            rule_data = {"signal": rule_sig, "score": rule_sc, "reasons": rule_rs}

            report = self.ai.generate_report(epic, df, sentiment, rule_signal=rule_data, regime_data=regime_data)

            # Split long reports into multiple messages (Telegram limit: 4096 chars)
            if len(report) > 4000:
                parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
                for part in parts:
                    self.notifier.send(part)
                return None  # already sent
            return report

        except Exception as e:
            return f"Fejl ved rapport: {e}"

    def _cmd_debug(self, args=None):
        """Handle /ai_debug command - show detailed watchdog and regime state."""
        msg = "🔧 <b>AI Debug Info</b>\n\n"

        # Regime data
        regimes = self.regime.get_all_regimes()
        msg += "<b>Markedsregimer:</b>\n"
        if regimes:
            for epic, data in sorted(regimes.items()):
                regime = data["regime"]
                adx = data["adx"]
                emoji = "📈" if "UP" in regime else "📉" if "DOWN" in regime else "↔️" if regime == "RANGING" else "❓"
                msg += f"  {emoji} {epic}: {regime} (ADX: {adx:.1f})\n"
        else:
            msg += "  Ingen data endnu\n"

        # Time-of-day bias
        from datetime import datetime as _dt
        msg += f"\n<b>Time-of-day bias (UTC {_dt.utcnow().hour:02d}:00):</b>\n"
        biases = self.time_bias.get_all_biases()
        if biases:
            for epic, data in sorted(biases.items()):
                bias_emoji = "🟢" if data["bias"] == "BULLISH" else "🔴" if data["bias"] == "BEARISH" else "⚪"
                msg += f"  {bias_emoji} {epic}: {data['bias']} ({data['avg_return']})\n"
        else:
            msg += "  Beregnes ved foerste scan\n"

        # ATR per coin
        msg += "\n<b>ATR per coin:</b>\n"
        debug = self.watchdog.get_debug_info()
        for epic, atr in sorted(debug["atr_per_coin"].items()):
            msg += f"  {epic}: {atr}\n"

        # Hold times
        msg += "\n<b>Holdtider:</b>\n"
        if debug["hold_times"]:
            for deal_short, hold_time in debug["hold_times"].items():
                msg += f"  {deal_short}: {hold_time}\n"
        else:
            msg += "  Ingen aktive\n"

        # Max hold limits
        msg += "\n<b>Max hold limits:</b>\n"
        for epic, limit in sorted(debug["max_hold_limits"].items()):
            msg += f"  {epic}: {limit}\n"

        # Watchdog state
        msg += f"\n<b>Watchdog state:</b>\n"
        msg += f"  Break-even: {debug['breakeven_positions']}\n"
        msg += f"  Delvis profit: {debug['partial_profit_positions']}\n"
        msg += f"  TP udvidelser: {sum(self.watchdog._tp_extensions.values())}\n"
        msg += f"  Scale-ins: {debug['scale_ins_done']}\n"

        # Cycle cooldowns
        if debug["cycle_cooldowns"]:
            msg += "\n<b>Cycle cooldowns:</b>\n"
            for epic, remaining in debug["cycle_cooldowns"].items():
                msg += f"  {epic}: {remaining}\n"

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
            "<b>Analyse:</b>\n"
            "/scan - AI-analyse af alle coins\n"
            "/report BTCUSD - Detaljeret rapport\n"
            "/debug - Debug info (ATR, regimer, watchdog)\n\n"
            "<b>Info:</b>\n"
            "/status - Balance og positioner\n"
            "/trades - Seneste handler\n\n"
            "<b>Handel:</b>\n"
            "/close EPIC - Luk position\n"
            "/close ALL - Luk alle\n\n"
            "<b>System:</b>\n"
            "/stop - Stop AI-botten\n"
            "/help - Denne besked"
        )

    def stop(self):
        self.running = False
        self.watchdog.stop()
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
