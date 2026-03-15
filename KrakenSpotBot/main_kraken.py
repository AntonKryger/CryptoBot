"""
KrakenBots — Unified entry point for all Kraken bot strategies.

Strategy type is loaded from config.yaml:
  strategy:
    type: grid | trend | mean_reversion | volatility

Each container runs ONE strategy, but shares coordinator state
with its partner bot for regime-based handoff.
"""

import argparse
import logging
import signal
import sys
import time
from datetime import datetime

from src.config import load_config
from src.exchange import get_adapter
from src.strategies import get_strategy
from src.risk.manager import SpotRiskManager
from src.risk.coordinator import BotCoordinator
from src.executor.trade_executor import TradeExecutor
from src.executor.spot_position_tracker import SpotPositionTracker
from src.executor.order_manager import OrderManager
from src.executor.position_watchdog import PositionWatchdog
from src.notifications.telegram_bot import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/kraken_bot.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)


class KrakenBot:
    """Unified Kraken bot — loads strategy from config."""

    def __init__(self, config_path: str):
        self.config = load_config(config_path)
        self.bot_id = self.config.get("bot", {}).get("id", "UNKNOWN")
        self.strategy_type = self.config.get("strategy", {}).get("type", "unknown")

        # Exchange adapter
        self.client = get_adapter(self.config)

        # Spot position tracker (Kraken spot has no native positions)
        self.position_tracker = SpotPositionTracker(
            db_path=self.config.get("database", {}).get("positions_path", "data/positions.db")
        )
        self.client.position_tracker = self.position_tracker

        # Risk manager
        self.risk = SpotRiskManager(self.config)

        # Coordinator (for partner-bot communication)
        self.coordinator = BotCoordinator(self.config)

        # Strategy (pluggable — loaded from config)
        self.strategy = get_strategy(self.config)
        self.strategy.client = self.client
        self.strategy.risk_manager = self.risk
        self.strategy.coordinator = self.coordinator

        # Telegram notifier
        self.notifier = TelegramNotifier(self.config)
        self.strategy.notifier = self.notifier

        # Trade executor
        self.executor = TradeExecutor(self.client, self.risk, self.config)

        # Order manager (for Grid bot)
        self.order_manager = OrderManager(self.client, self.config)

        # Position watchdog
        self.watchdog = PositionWatchdog(
            self.client, self.risk, self.notifier, self.config,
            executor=self.executor
        )
        self.watchdog.strategy = self.strategy

        # Trading config
        trading_cfg = self.config.get("trading", {})
        self.coins = trading_cfg.get("coins", ["BTC/USD", "ETH/USD"])
        self.scan_interval = trading_cfg.get("scan_interval", 60)
        self.scan_offset = trading_cfg.get("scan_offset_seconds", 0)
        self.timeframe = trading_cfg.get("timeframe", "MINUTE_15")

        self._running = False
        self._last_regime = {}  # {epic: regime}
        self._regime_counter = {}  # {epic: {"regime": str, "count": int}} — hysterese
        self._last_1h_candle_time = {}  # {epic: timestamp} — only update regime on candle close
        self._last_decay_check = None  # Date of last strategy decay check

        # Multi-tier circuit breaker (escalating pause based on move size)
        self._circuit_breaker_until = {}  # {epic: timestamp}
        circuit_cfg = self.config.get("circuit_breaker", {})
        self._circuit_breaker_tiers = circuit_cfg.get("tiers", [
            {"threshold_pct": 3.0, "pause_minutes": 5},    # Mild move
            {"threshold_pct": 5.0, "pause_minutes": 10},   # Strong move
            {"threshold_pct": 8.0, "pause_minutes": 30},   # Extreme move
        ])
        # Sort tiers descending so we match the highest threshold first
        self._circuit_breaker_tiers.sort(key=lambda t: t["threshold_pct"], reverse=True)

        # Adaptive stale data guard: per-timeframe max age (seconds)
        stale_cfg = self.config.get("trading", {}).get("stale_data_max_age", 30)
        if isinstance(stale_cfg, dict):
            self._stale_data_ages = stale_cfg  # {"1m": 10, "5m": 15, "15m": 30, "1h": 60}
        else:
            self._stale_data_ages = {}
            self._stale_data_default = int(stale_cfg)
        # Map common timeframe names to stale_data_ages keys
        self._timeframe_stale_map = {
            "MINUTE": 10, "MINUTE_5": 15, "MINUTE_15": 30, "MINUTE_30": 45,
            "HOUR": 120, "HOUR_4": 300, "DAY": 600,
            "1m": 10, "5m": 15, "15m": 30, "30m": 45,
            "1h": 120, "4h": 300, "1d": 600,
        }

        # Position reconciliation interval
        self._last_reconcile = 0  # timestamp

    def start(self):
        """Start the bot: connect, initialize, run main loop."""
        logger.info(f"Starting KrakenBot [{self.bot_id}] — strategy: {self.strategy_type}")

        # Connect to Kraken
        if not self.client.start_session():
            logger.error("Failed to connect to Kraken")
            sys.exit(1)

        # Initialize risk manager with current balance
        balance_info = self.client.get_account_balance()
        if balance_info:
            self.risk.initialize(balance_info["balance"])
            logger.info(f"Account balance: ${balance_info['balance']:.2f} (available: ${balance_info['available']:.2f})")
        else:
            logger.error("Could not fetch account balance")
            sys.exit(1)

        # Cancel any orphan orders from previous runs (Grid bot safety)
        if self.strategy_type == "grid":
            try:
                cancelled = self.client.cancel_all_orders()
                if cancelled > 0:
                    logger.info(f"Cleaned up {cancelled} orphan orders from previous run")
            except Exception as e:
                logger.warning(f"Orphan order cleanup failed: {e}")

        # Clean up stale coordinator locks
        self.coordinator.cleanup_stale_locks()

        # Start watchdog
        self.watchdog.start()

        # Register Telegram commands
        self._register_commands()
        self.notifier.start_command_listener()

        # Announce startup
        self.notifier.send(
            f"🚀 <b>{self.bot_id} started</b>\n"
            f"Strategy: {self.strategy_type}\n"
            f"Coins: {', '.join(self.coins)}\n"
            f"Balance: ${balance_info['balance']:.2f}"
        )

        # Apply scan offset for API rate limiting across bots
        if self.scan_offset > 0:
            logger.info(f"Scan offset: waiting {self.scan_offset}s before first scan")
            time.sleep(self.scan_offset)

        # Main loop
        self._running = True
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        try:
            self._run_loop()
        except KeyboardInterrupt:
            self._shutdown()

    def _get_stale_max_age(self) -> int:
        """Get max stale data age for current timeframe."""
        if self._stale_data_ages:
            # Config provides per-timeframe dict
            return self._stale_data_ages.get(self.timeframe, 30)
        if hasattr(self, '_stale_data_default'):
            return self._stale_data_default
        # Fallback: use timeframe map
        return self._timeframe_stale_map.get(self.timeframe, 30)

    def _run_loop(self):
        while self._running:
            try:
                self._scan_cycle()
            except Exception as e:
                logger.error(f"Scan cycle error: {e}", exc_info=True)

            time.sleep(self.scan_interval)

    def _scan_cycle(self):
        """Main scan: iterate coins, detect regime, run strategy, execute trades."""
        # Check kill switch
        balance_info = self.client.get_account_balance()
        if not balance_info:
            logger.warning("Could not fetch balance — skipping cycle")
            return

        current_balance = balance_info["balance"]
        killed, reason = self.risk.check_kill_switch(current_balance)
        if killed:
            logger.critical(f"KILL SWITCH: {reason}")
            self.notifier.notify_kill_switch(reason)
            self._running = False
            return

        # Report equity + check global kill-switch across all bots
        self.coordinator.update_equity(current_balance)
        global_killed, global_reason = self.coordinator.check_global_kill_switch()
        if global_killed:
            logger.critical(f"GLOBAL KILL SWITCH: {global_reason}")
            self.notifier.send(
                f"🛑 <b>GLOBAL KILL SWITCH</b>\n"
                f"{global_reason}\n"
                f"ALL bots should stop trading."
            )
            self._running = False
            return

        # Strategy decay check (once daily)
        today = datetime.now().date()
        if self._last_decay_check != today:
            self._last_decay_check = today
            try:
                history = self.executor.get_trade_history(limit=500)
                decay = self.risk.check_strategy_decay(history)
                if decay["decayed"]:
                    logger.warning(f"STRATEGY DECAY: {decay['recommendation']}")
                    self.notifier.send(
                        f"⚠️ <b>Strategy Decay Warning</b>\n"
                        f"{decay['recommendation']}\n"
                        f"Trades: {decay['trade_count']}, Avg P/L: ${decay.get('avg_pl', 0):.2f}"
                    )
                elif decay["trade_count"] >= 50:
                    logger.info(f"Strategy health: Sharpe {decay['sharpe']:.2f} ({decay['trade_count']} trades)")
            except Exception as e:
                logger.debug(f"Decay check skipped: {e}")

        # Get open positions
        positions = self.client.get_positions()
        open_positions = positions.get("positions", [])
        open_count = len(open_positions)
        open_epics = {p["position"]["epic"] for p in open_positions}

        # Balance snapshot
        self.executor.snapshot_balance(balance_info, bot_name=self.bot_id)

        # Check grid fills if Grid bot — update exposure for partial fills
        if self.strategy_type == "grid":
            fills = self.order_manager.check_fills()
            for fill in fills:
                self.strategy.on_position_opened(fill)
                # Track exposure from grid fills
                fill_size = fill.get("filled_size", fill.get("size", 0))
                fill_price = fill.get("fill_price", 0)
                if current_balance > 0 and fill_size and fill_price:
                    fill_exposure = (fill_size * fill_price) / current_balance * 100
                    self.coordinator.add_coin_exposure(fill["epic"], fill_exposure)

        # Position reconciliation every 5 minutes (ChatGPT: sync local vs exchange)
        now_ts = time.time()
        if now_ts - self._last_reconcile > 300:
            self._last_reconcile = now_ts
            self._reconcile_positions(open_positions)

        # Scan each coin
        signals = []
        for epic in self.coins:
            try:
                # Volatility circuit breaker: skip if paused
                breaker_until = self._circuit_breaker_until.get(epic, 0)
                if now_ts < breaker_until:
                    remaining = int(breaker_until - now_ts)
                    logger.debug(f"{epic}: Circuit breaker active ({remaining}s remaining)")
                    continue

                # Detect regime — only update on 1H candle close (avoid whipsaw)
                prices_1h = self.client.get_prices(epic, resolution="HOUR", max_count=50)
                df_1h = self.strategy.prepare_dataframe(prices_1h)
                if df_1h is not None and len(df_1h) >= 30:
                    adx = self.strategy.calculate_adx(df_1h)

                    # Check if new 1H candle has closed
                    latest_candle_time = df_1h.index[-1] if hasattr(df_1h.index, '__len__') else None
                    last_seen = self._last_1h_candle_time.get(epic)
                    new_candle = (latest_candle_time is not None and latest_candle_time != last_seen)
                    self._last_1h_candle_time[epic] = latest_candle_time

                    if new_candle:
                        # Classify with supplementary indicators
                        raw_regime = self._classify_regime(adx, df_1h)

                        # Hysterese: require 3 consecutive candles in same regime
                        counter = self._regime_counter.get(epic, {"regime": None, "count": 0})
                        if raw_regime == counter["regime"]:
                            counter["count"] += 1
                        else:
                            counter = {"regime": raw_regime, "count": 1}
                        self._regime_counter[epic] = counter

                        if counter["count"] >= 3:
                            regime = raw_regime
                        else:
                            regime = self._last_regime.get(epic, "NEUTRAL")

                        # Announce regime shift to coordinator
                        old_regime = self._last_regime.get(epic, "UNKNOWN")
                        if regime != old_regime and old_regime != "UNKNOWN":
                            logger.info(f"Regime shift {epic}: {old_regime} → {regime} (confirmed after {counter['count']} candles)")
                            self.coordinator.announce_regime_shift(epic, old_regime, regime)
                            self.notifier.notify_regime_shift(epic, old_regime, regime, self.bot_id)
                        self._last_regime[epic] = regime
                        self.coordinator.update_regime(epic, regime, adx)
                    else:
                        # No new candle — use cached regime
                        regime = self._last_regime.get(epic, "NEUTRAL")

                    # Check if this strategy should be active in current regime
                    if not self.strategy.should_be_active(regime, adx):
                        continue
                else:
                    adx = 0
                    regime = "UNKNOWN"

                # Register trade intent in priority queue
                self.coordinator.request_trade(epic)

                # Check coordinator permission (includes priority queue check)
                can_trade, coord_reason = self.coordinator.can_trade(epic)
                if not can_trade:
                    self.coordinator.clear_trade_request(epic)
                    logger.debug(f"{epic}: Coordinator blocked — {coord_reason}")
                    continue

                # Skip if already have position in this coin
                if epic in open_epics:
                    continue

                # Fetch price data for strategy's preferred timeframe
                prices = self.client.get_prices(epic, resolution=self.timeframe)

                # Stale data guard: skip if market data is too old (adaptive per timeframe)
                df_check = self.strategy.prepare_dataframe(prices)
                stale_max_age = self._get_stale_max_age()
                if df_check is not None and len(df_check) >= 2:
                    # Check timestamp of latest candle (ccxt returns ms timestamps)
                    latest_ts = df_check.index[-1]
                    if hasattr(latest_ts, 'timestamp'):
                        age_seconds = time.time() - latest_ts.timestamp()
                    else:
                        # Fallback: assume ms epoch
                        age_seconds = time.time() - (float(latest_ts) / 1000)
                    if age_seconds > stale_max_age:
                        logger.warning(f"{epic}: Stale data ({age_seconds:.0f}s old > {stale_max_age}s) — skipping")
                        continue

                    # Multi-tier circuit breaker: check for extreme candle move
                    recent_close = df_check["close"].iloc[-1]
                    prev_close = df_check["close"].iloc[-2]
                    move_pct = abs(recent_close - prev_close) / prev_close * 100 if prev_close > 0 else 0

                    # Match highest tier that triggers (tiers sorted descending)
                    breaker_triggered = False
                    for tier in self._circuit_breaker_tiers:
                        if move_pct >= tier["threshold_pct"]:
                            pause_minutes = tier["pause_minutes"]
                            pause_until = time.time() + (pause_minutes * 60)
                            self._circuit_breaker_until[epic] = pause_until
                            logger.warning(
                                f"[CIRCUIT BREAKER] {epic}: {move_pct:.1f}% move (tier {tier['threshold_pct']}%) — "
                                f"pausing {pause_minutes}min"
                            )
                            # Log to SQLite for monitoring/analysis
                            self.executor.log_circuit_breaker(
                                epic, move_pct, tier["threshold_pct"], pause_minutes, self.bot_id
                            )
                            self.notifier.send(
                                f"⚡ <b>Circuit Breaker: {epic}</b>\n"
                                f"{move_pct:.1f}% move in 1 candle — pausing {pause_minutes}min"
                            )
                            breaker_triggered = True
                            break  # Matched highest applicable tier

                    if breaker_triggered:
                        continue

                # Run strategy scan
                signal = self.strategy.scan(epic, prices)
                if signal:
                    # Update ATR cache for watchdog
                    df = self.strategy.prepare_dataframe(prices)
                    if df is not None:
                        atr = self.strategy.calculate_atr(df)
                        self.watchdog.update_atr(epic, atr)

                    signals.append(signal)

            except Exception as e:
                logger.error(f"Scan error for {epic}: {e}")

        # Execute signals
        for signal in signals:
            epic = signal["epic"]
            direction = signal.get("direction", "")

            # Grid setup is handled differently
            if direction == "GRID_SETUP":
                self._handle_grid_setup(signal, balance_info)
                continue

            # Execute trade
            result, error = self.executor.execute_signal(signal, balance_info, open_count)
            if result:
                deal_ref = result.get("dealReference", "")
                fill_size = result.get("size", signal.get("size", 0))
                fill_price = result.get("fillPrice", signal["entry_price"])

                # Calculate exposure_pct for this trade
                exposure_pct = 0
                if current_balance > 0 and fill_size and fill_price:
                    exposure_pct = (fill_size * fill_price) / current_balance * 100

                self.watchdog.track_entry(deal_ref, epic, signal_details=signal.get("details"))
                self.coordinator.lock_coin(epic, exposure_pct=exposure_pct)
                self.coordinator.clear_trade_request(epic)
                self.strategy.on_position_opened({"epic": epic, "deal_id": deal_ref})
                self.notifier.notify_trade(
                    direction, epic, signal.get("size", 0),
                    signal["entry_price"], signal.get("stop_loss", 0),
                    signal.get("take_profit", 0), signal.get("details")
                )
                open_count += 1
            elif error:
                self.coordinator.clear_trade_request(epic)
                logger.info(f"{epic}: Signal not executed — {error}")

    def _handle_grid_setup(self, signal, balance_info):
        """Set up grid orders with bell curve capital distribution."""
        epic = signal["epic"]
        grid_levels = signal.get("grid_levels", [])
        if not grid_levels:
            return

        available = balance_info.get("available", 0)
        total_grid_budget = available * 0.3  # 30% of available for grid
        current_price = signal["entry_price"]

        # Bell curve: each level has a weight (center=~2x, outer=~0.5x)
        total_weight = sum(lvl.get("weight", 1.0) for lvl in grid_levels)
        budget_per_unit = total_grid_budget / total_weight if total_weight > 0 else 0

        placed = 0
        for lvl in grid_levels:
            weight = lvl.get("weight", 1.0)
            level_budget = budget_per_unit * weight
            level_size = self.risk.calculate_position_size(level_budget, current_price)
            lvl["size"] = level_size

        placed = self.order_manager.place_grid_orders(epic, grid_levels)
        if placed > 0:
            self.coordinator.lock_coin(epic)
            self.notifier.send(
                f"📊 <b>Grid setup: {epic}</b>\n"
                f"Levels: {placed}/{len(grid_levels)}\n"
                f"Budget: ${total_grid_budget:.2f} (bell curve weighted)\n"
                f"Spacing: {signal.get('details', {}).get('spacing_pct', '?')}%"
            )

    def _classify_regime(self, adx: float, df) -> str:
        """Classify market regime from ADX + supplementary indicators.

        Thresholds (ChatGPT-tuned for crypto):
        - TRENDING: ADX >= 28 (crypto has more noise than forex)
        - RANGING:  ADX <= 18
        - NEUTRAL:  18 < ADX < 28 (no trading zone)

        Supplementary: ATR expansion ratio + Bollinger Band width.
        """
        # ATR expansion: ATR(14) / ATR(50) — volatility spike detection
        atr_14 = df["close"].diff().abs().rolling(14).mean().iloc[-1]
        atr_50 = df["close"].diff().abs().rolling(50).mean().iloc[-1]
        atr_ratio = atr_14 / atr_50 if atr_50 > 0 else 1.0

        # Bollinger Band width
        bb_mid = df["close"].rolling(20).mean().iloc[-1]
        bb_std = df["close"].rolling(20).std().iloc[-1]
        bbw = (bb_std * 4) / bb_mid if bb_mid > 0 else 0

        if adx >= 28:
            # Confirm with BB width (>0.04 = trending)
            if bbw > 0.04 or atr_ratio > 1.5:
                if len(df) >= 50:
                    ema20 = df["close"].ewm(span=20).mean().iloc[-1]
                    ema50 = df["close"].ewm(span=50).mean().iloc[-1]
                    if ema20 > ema50:
                        return "TRENDING_UP"
                    return "TRENDING_DOWN"
                return "TRENDING_UP"
            # ADX high but no volatility confirmation — stay neutral
            return "NEUTRAL"
        elif adx <= 18:
            # Confirm ranging with tight BB width (<0.02)
            if bbw < 0.02:
                return "RANGING"
            # BB expanding despite low ADX — transitional, stay neutral
            return "RANGING"  # Still ranging if ADX is clearly low
        return "NEUTRAL"

    def _reconcile_positions(self, exchange_positions: list):
        """Sync local position tracker with exchange state (ChatGPT: prevent desync).

        Runs every 5 minutes. Detects:
        - Positions closed on exchange but still OPEN in local DB
        - Orphan local positions with no exchange match
        """
        if not hasattr(self.client, 'position_tracker') or not self.client.position_tracker:
            return

        tracker = self.client.position_tracker
        local_open = tracker.get_open_positions()
        exchange_ids = set()

        for p in exchange_positions:
            deal_id = p.get("position", {}).get("dealId", "")
            if deal_id:
                exchange_ids.add(deal_id)

        # Find local positions that are no longer on exchange (closed externally)
        reconciled = 0
        for local_pos in local_open:
            deal_id = local_pos.get("deal_id", "")
            if deal_id and deal_id not in exchange_ids:
                logger.warning(f"[RECONCILE] Position {deal_id} ({local_pos.get('epic', '?')}) "
                               f"missing from exchange — marking as closed")
                try:
                    tracker.close_position(deal_id, exit_price=0, profit_loss=0)
                    # Unlock coin in coordinator
                    epic = local_pos.get("epic", "")
                    if epic:
                        self.coordinator.unlock_coin(epic)
                    reconciled += 1
                except Exception as e:
                    logger.error(f"[RECONCILE] Failed to close orphan {deal_id}: {e}")

        if reconciled > 0:
            logger.info(f"[RECONCILE] Reconciled {reconciled} orphan positions")

    def _register_commands(self):
        """Register Telegram commands."""
        self.notifier.register_command("/status", self._cmd_status)
        self.notifier.register_command("/positions", self._cmd_positions)
        self.notifier.register_command("/balance", self._cmd_balance)
        self.notifier.register_command("/regime", self._cmd_regime)
        self.notifier.register_command("/stats", self._cmd_stats)
        self.notifier.register_command("/stop", self._cmd_stop)
        self.notifier.register_command("/help", self._cmd_help)

    def _cmd_status(self, args):
        positions = self.client.get_positions()
        open_count = len(positions.get("positions", []))
        balance = self.client.get_account_balance()
        coord_status = self.coordinator.get_status()

        return (
            f"📊 <b>{self.bot_id} Status</b>\n"
            f"Strategy: {self.strategy_type}\n"
            f"Balance: ${balance['balance']:.2f}\n"
            f"Open positions: {open_count}\n"
            f"Regimes: {', '.join(f'{k}={v}' for k, v in self._last_regime.items())}\n"
            f"Coordinator locks: {len(coord_status.get('locks', {}))}"
        )

    def _cmd_positions(self, args):
        positions = self.client.get_positions()
        pos_list = positions.get("positions", [])
        if not pos_list:
            return "No open positions"

        msg = f"📊 <b>Open Positions ({len(pos_list)})</b>\n"
        for p in pos_list:
            epic = p["position"]["epic"]
            direction = p["position"]["direction"]
            entry = p["position"]["level"]
            current = p["market"]["bid"] if direction == "BUY" else p["market"]["offer"]
            pl_pct = ((current - entry) / entry * 100) if direction == "BUY" else ((entry - current) / entry * 100)
            msg += f"\n{epic}: {direction} @ {entry:.2f} → {current:.2f} ({pl_pct:+.1f}%)"
        return msg

    def _cmd_balance(self, args):
        balance = self.client.get_account_balance()
        return (
            f"💰 <b>Kraken Balance</b>\n"
            f"Total: ${balance['balance']:.2f}\n"
            f"Available: ${balance['available']:.2f}"
        )

    def _cmd_regime(self, args):
        msg = "📈 <b>Market Regimes</b>\n"
        for epic in self.coins:
            regime = self._last_regime.get(epic, "?")
            coord = self.coordinator.get_regime(epic)
            adx = coord.get("adx", 0) if coord else 0
            msg += f"\n{epic}: {regime} (ADX: {adx:.1f})"
        return msg

    def _cmd_stats(self, args):
        stats = self.executor.get_stats()
        return (
            f"📊 <b>{self.bot_id} Stats</b>\n"
            f"Trades: {stats['total_trades']}\n"
            f"Wins: {stats['wins']} | Losses: {stats['losses']}\n"
            f"Win rate: {stats['win_rate']}%\n"
            f"Total P/L: ${stats['total_pl']:.2f}\n"
            f"Avg P/L: ${stats['avg_pl']:.2f}"
        )

    def _cmd_stop(self, args):
        self._running = False
        return f"🛑 {self.bot_id} stopping after current cycle..."

    def _cmd_help(self, args):
        return (
            f"<b>{self.bot_id} Commands</b>\n"
            "/status — Bot status\n"
            "/positions — Open positions\n"
            "/balance — Account balance\n"
            "/regime — Market regimes\n"
            "/stats — Trading statistics\n"
            "/stop — Stop bot"
        )

    def _handle_shutdown(self, signum, frame):
        logger.info(f"Shutdown signal received ({signum})")
        self._shutdown()

    def _shutdown(self):
        self._running = False
        self.watchdog.stop()
        self.notifier.stop_command_listener()

        # Grid bot: cancel all orders on shutdown
        if self.strategy_type == "grid" and hasattr(self.strategy, 'shutdown'):
            self.strategy.shutdown()

        self.notifier.send(f"🛑 <b>{self.bot_id} stopped</b>")
        logger.info(f"KrakenBot [{self.bot_id}] stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KrakenBots — Multi-strategy Kraken trading")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    bot = KrakenBot(args.config)
    bot.start()
