"""
Position Watchdog - Fast position monitor that runs every 10-15 seconds.
No AI calls in the fast loop - pure price-based protection.

Features:
1. Break-even stop at configurable profit % (default 1.5%)
2. Trailing stop at configurable profit % (default 2.5%), distance = 1.5x ATR
3. Partial profit-taking (close 50% at configurable threshold)
4. Max hold time per coin category (major: 24h, altcoin: 8h, memecoin: 4h)
5. Early exit on momentum acceleration (3+ adverse candles)
6. Dynamic take-profit extension near TP target
7. Cycle trading - re-analyse on position close for reversal
8. Scale-in on rising conviction
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionWatchdog:
    """Fast position monitor - checks open positions every 10-15 seconds."""

    def __init__(self, client, risk_manager, notifier, config):
        self.client = client
        self.risk = risk_manager
        self.notifier = notifier

        watchdog_cfg = config.get("watchdog", {})
        self.check_interval = watchdog_cfg.get("check_interval", 12)
        self.breakeven_trigger_pct = watchdog_cfg.get("breakeven_trigger_pct", 1.5)
        self.trailing_trigger_pct = watchdog_cfg.get("trailing_trigger_pct", 2.5)
        self.trailing_atr_mult = watchdog_cfg.get("trailing_atr_mult", 1.5)
        self.partial_profit_pct = watchdog_cfg.get("partial_profit_pct", 4.0)
        self.partial_close_ratio = watchdog_cfg.get("partial_close_ratio", 0.5)

        # Internal state
        self._running = False
        self._thread = None
        self._atr_cache = {}           # {epic: atr_pct} - updated by main scan
        self._peak_prices = {}         # {deal_id: best price seen}
        self._partial_taken = set()    # deal_ids where partial profit was taken
        self._breakeven_set = set()    # deal_ids where stop moved to break-even
        self._entry_times = {}         # {deal_id: datetime} - for max hold time
        self._iteration_count = 0      # for periodic tasks

        # Early exit state
        self._candle_cache = {}        # {epic: {"candles": [...], "timestamp": float}}
        self._candle_cache_ttl = 300   # 5 minutes

        # Dynamic TP state
        self._tp_extensions = {}       # {deal_id: count} - max 2 per position

        # Cycle trading state
        self._cycle_cooldowns = {}     # {epic: datetime} - 30 min cooldown
        self._cycle_callback = None    # Set by main_ai.py for re-analysis

        # Progressive trailing SL state
        self._last_sl_update = {}      # {deal_id: last_sl_price} - avoid API spam
        self.progressive_sl_trigger = watchdog_cfg.get("progressive_sl_trigger_pct", 2.0)
        self.progressive_sl_trail = watchdog_cfg.get("progressive_sl_trail_pct", 1.0)

        # Profit pullback close - actively close when giving back profit
        self.pullback_peak_trigger = watchdog_cfg.get("pullback_peak_trigger_pct", 1.5)
        self.pullback_close_pct = watchdog_cfg.get("pullback_close_pct", 0.75)

        # Scale-in state
        self._scale_in_done = set()    # deal_ids that already got scale-in
        self._entry_confidence = {}    # {deal_id: confidence} - confidence at entry
        self._scale_in_callback = None # Set by main_ai.py for re-evaluation

        # References set by main*.py
        self.ai_analyst = None
        self.signal_engine = None
        self.executor = None  # For cooldown tracking
        self.time_bias = None  # For sentiment-based night mode

        logger.info(
            f"Watchdog initialized (interval={self.check_interval}s, "
            f"breakeven={self.breakeven_trigger_pct}%, "
            f"pullback_close=peak>{self.pullback_peak_trigger}%+drop>{self.pullback_close_pct}%, "
            f"partial={self.partial_profit_pct}%@{self.partial_close_ratio*100:.0f}%)"
        )

    def _set_cooldown(self, epic):
        """Set trade cooldown for an epic after watchdog closes a position."""
        if self.executor:
            self.executor._recently_traded[epic] = datetime.now()

    def update_atr(self, epic, atr_pct):
        """Called by main scan cycle to cache latest ATR for each coin."""
        self._atr_cache[epic] = atr_pct

    def track_entry(self, deal_id, epic, confidence=None):
        """Track position entry time and confidence for max hold and scale-in."""
        self._entry_times[deal_id] = datetime.now()
        if confidence is not None:
            self._entry_confidence[deal_id] = confidence

    def start(self):
        """Start the watchdog background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info("Position watchdog started")

    def stop(self):
        """Stop the watchdog."""
        self._running = False
        logger.info("Position watchdog stopped")

    def _watch_loop(self):
        """Main watchdog loop - runs every check_interval seconds."""
        while self._running:
            try:
                self._iteration_count += 1
                self._check_positions()
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
            time.sleep(self.check_interval)

    def _check_positions(self):
        """Check all open positions for all watchdog rules."""
        try:
            positions = self.client.get_positions()
        except Exception as e:
            logger.warning(f"Watchdog: Could not fetch positions: {e}")
            return

        open_positions = positions.get("positions", [])

        # Clean up tracking for closed positions
        active_deal_ids = {p["position"]["dealId"] for p in open_positions}
        closed_ids = set(self._peak_prices.keys()) - active_deal_ids
        for deal_id in closed_ids:
            self._peak_prices.pop(deal_id, None)
            self._partial_taken.discard(deal_id)
            self._breakeven_set.discard(deal_id)
            self._entry_times.pop(deal_id, None)
            self._tp_extensions.pop(deal_id, None)
            self._last_sl_update.pop(deal_id, None)
            self._scale_in_done.discard(deal_id)
            self._entry_confidence.pop(deal_id, None)

        for pos in open_positions:
            self._evaluate_position(pos)

        # Periodic status log every ~5 min (25 iterations x 12s)
        if self._iteration_count % 25 == 0 and open_positions:
            self._log_status_summary(open_positions)

        # Periodic: scale-in check every ~10 min (50 iterations x 12s)
        if self._iteration_count % 50 == 0 and self._scale_in_callback:
            self._check_scale_in(open_positions)

    def _evaluate_position(self, pos):
        """Evaluate a single position for all watchdog rules."""
        deal_id = pos["position"]["dealId"]
        epic = pos["market"]["epic"]
        direction = pos["position"]["direction"]
        entry_price = pos["position"]["level"]
        size = pos["position"]["size"]
        current_price = pos["market"]["bid"] if direction == "BUY" else pos["market"]["offer"]

        # Calculate current P/L percentage
        if direction == "BUY":
            pl_pct = (current_price - entry_price) / entry_price * 100
        else:
            pl_pct = (entry_price - current_price) / entry_price * 100

        # Track peak price (best price since entry)
        if deal_id not in self._peak_prices:
            self._peak_prices[deal_id] = current_price
        else:
            if direction == "BUY":
                self._peak_prices[deal_id] = max(self._peak_prices[deal_id], current_price)
            else:
                self._peak_prices[deal_id] = min(self._peak_prices[deal_id], current_price)

        # Track entry time if not already tracked
        if deal_id not in self._entry_times:
            self._entry_times[deal_id] = datetime.now()

        peak = self._peak_prices[deal_id]

        # Calculate drawdown from peak
        if direction == "BUY":
            drawdown_from_peak_pct = (peak - current_price) / peak * 100
            peak_profit_pct = (peak - entry_price) / entry_price * 100
        else:
            drawdown_from_peak_pct = (current_price - peak) / peak * 100
            peak_profit_pct = (entry_price - peak) / entry_price * 100

        # Get ATR for dynamic calculations (default 2% if not cached yet)
        atr_pct = self._atr_cache.get(epic, 2.0)
        trailing_distance = atr_pct * self.trailing_atr_mult

        # -- Rule 1: Max Hold Time --
        if self._check_max_hold_time(deal_id, epic, direction, size, pl_pct):
            return  # Position was closed

        # -- Rule 2: Early Exit (momentum acceleration) --
        if self._check_early_exit(deal_id, epic, direction, size, pl_pct):
            return  # Position was (partially) closed

        # -- Rule 3: Break-even stop (server-side on Capital.com) --
        if deal_id not in self._breakeven_set and pl_pct >= self.breakeven_trigger_pct:
            try:
                self.client.update_position(deal_id, stop_loss=round(entry_price, 5))
                self._breakeven_set.add(deal_id)
                logger.info(
                    f"WATCHDOG: Break-even stop set for {epic} "
                    f"(P/L: +{pl_pct:.1f}%, trigger: {self.breakeven_trigger_pct}%)"
                )
                self.notifier.send(
                    f"🛡 <b>Break-even stop: {epic}</b>\n"
                    f"P/L: +{pl_pct:.1f}% | Stop flyttet til entry ({entry_price:.4f})"
                )
            except Exception as e:
                logger.warning(f"Watchdog: Failed to set break-even for {epic}: {e}")

        # -- Rule 3b: Progressive trailing SL (server-side) --
        if deal_id in self._breakeven_set and pl_pct >= self.progressive_sl_trigger:
            self._update_progressive_sl(deal_id, epic, direction, entry_price, current_price, pl_pct, pos)

        # -- Rule 3c: PROFIT PULLBACK CLOSE --
        if peak_profit_pct >= self.pullback_peak_trigger and drawdown_from_peak_pct >= self.pullback_close_pct:
            try:
                logger.warning(
                    f"WATCHDOG: PROFIT PULLBACK closing {epic}! "
                    f"Peak P/L: +{peak_profit_pct:.1f}%, Now: +{pl_pct:.1f}%, "
                    f"Gave back: {drawdown_from_peak_pct:.2f}% from peak"
                )
                self.client.close_position(deal_id, direction=direction, size=size)
                self._set_cooldown(epic)
                self._update_trade_db(deal_id, current_price, pl_pct, size, entry_price)
                self.notifier.send(
                    f"💰 <b>Profit taget: {epic}</b>\n"
                    f"Peak: +{peak_profit_pct:.1f}% | Lukket: +{pl_pct:.1f}%\n"
                    f"Pullback fra top: {drawdown_from_peak_pct:.2f}%\n"
                    f"Beskyttede profit i stedet for at vente"
                )
                self._trigger_cycle_trade(epic, direction, pl_pct)
                return  # Position closed
            except Exception as e:
                logger.error(f"Watchdog: Profit pullback close failed for {epic}: {e}")

        # -- Rule 4: Partial profit-taking --
        if deal_id not in self._partial_taken and pl_pct >= self.partial_profit_pct:
            partial_size = round(size * self.partial_close_ratio, 4)
            if partial_size > 0:
                try:
                    self.client.close_position(deal_id, direction=direction, size=partial_size)
                    self._partial_taken.add(deal_id)
                    partial_pl = (current_price - entry_price) * partial_size if direction == "BUY" else (entry_price - current_price) * partial_size
                    self._update_trade_db(deal_id, current_price, partial_pl, partial_size, entry_price, partial=True)
                    logger.info(
                        f"WATCHDOG: Partial profit taken on {epic} "
                        f"(+{pl_pct:.1f}%, closed {partial_size} of {size})"
                    )
                    self.notifier.send(
                        f"💰 <b>Delvis profit: {epic}</b>\n"
                        f"P/L: +{pl_pct:.1f}% | Lukket {partial_size} af {size}\n"
                        f"Resten koerer med trailing stop ({trailing_distance:.1f}%)"
                    )
                except Exception as e:
                    logger.error(f"Watchdog: Partial close failed for {epic}: {e}")

        # -- Rule 5: Dynamic Take Profit extension --
        self._check_dynamic_tp(deal_id, epic, direction, entry_price, current_price, pl_pct, atr_pct, pos)

        # -- Rule 6: ATR-based trailing stop --
        if pl_pct >= self.trailing_trigger_pct and peak_profit_pct > 0 and drawdown_from_peak_pct > trailing_distance:
            try:
                logger.warning(
                    f"WATCHDOG: Trailing stop triggered for {epic}! "
                    f"Peak: {peak:.4f}, Now: {current_price:.4f}, "
                    f"Drawdown: {drawdown_from_peak_pct:.1f}% > {trailing_distance:.1f}%"
                )
                self.client.close_position(deal_id, direction=direction, size=size)
                self._set_cooldown(epic)
                self._update_trade_db(deal_id, current_price, pl_pct, size, entry_price)
                self.notifier.send(
                    f"🔒 <b>Trailing stop: {epic}</b>\n"
                    f"Peak: {peak:.4f} | Lukket: {current_price:.4f}\n"
                    f"Drawdown fra top: {drawdown_from_peak_pct:.1f}% (graense: {trailing_distance:.1f}%)\n"
                    f"Profit fra entry: {pl_pct:+.1f}%"
                )
                self._trigger_cycle_trade(epic, direction, pl_pct)
            except Exception as e:
                logger.error(f"Watchdog: Trailing close failed for {epic}: {e}")

        # -- Rule 7: Sentiment-based close --
        if self.time_bias and pl_pct >= 0.5:
            self._check_sentiment_close(deal_id, epic, direction, size, pl_pct)

    def _check_sentiment_close(self, deal_id, epic, direction, size, pl_pct):
        """Close profitable positions when time-of-day bias goes against them."""
        try:
            bias, avg_return, _ = self.time_bias.get_bias(epic)
        except Exception:
            return

        if bias == "NEUTRAL":
            return

        should_close = False
        if bias == "BEARISH" and direction == "BUY" and pl_pct >= 0.5:
            should_close = True
        elif bias == "BULLISH" and direction == "SELL" and pl_pct >= 0.5:
            should_close = True

        if not should_close:
            return

        if self._iteration_count % 25 != 0:
            return

        try:
            opposite = "short" if direction == "BUY" else "long"
            logger.info(
                f"WATCHDOG: Sentiment close {epic} — {bias} hour (avg {avg_return:+.3f}%), "
                f"closing profitable {direction} (+{pl_pct:.1f}%) to free capital for {opposite}"
            )
            # Need entry_price for DB update - get from position data
            self.client.close_position(deal_id, direction=direction, size=size)
            self._set_cooldown(epic)
            # Note: pl_pct and size available from caller scope via _evaluate_position
            self._update_trade_db_by_deal(deal_id, pl_pct)
            self.notifier.send(
                f"🌙 <b>Sentiment close: {epic}</b>\n"
                f"Time bias: {bias} (avg return: {avg_return:+.3f}%)\n"
                f"Lukkede {direction} med +{pl_pct:.1f}% profit\n"
                f"Frigiver kapital til {'SHORT' if direction == 'BUY' else 'LONG'}"
            )
            self._trigger_cycle_trade(epic, direction, pl_pct)
        except Exception as e:
            logger.error(f"Watchdog: Sentiment close failed for {epic}: {e}")

    def _update_progressive_sl(self, deal_id, epic, direction, entry_price, current_price, pl_pct, pos):
        """Move server-side SL up as position profits grow."""
        trail_pct = self.progressive_sl_trail

        if direction == "BUY":
            new_sl = round(current_price * (1 - trail_pct / 100), 5)
        else:
            new_sl = round(current_price * (1 + trail_pct / 100), 5)

        current_sl = pos["position"].get("stopLevel")
        if current_sl is None:
            return
        current_sl = float(current_sl)

        if direction == "BUY" and new_sl <= current_sl:
            return
        if direction == "SELL" and new_sl >= current_sl:
            return

        sl_move_pct = abs(new_sl - current_sl) / entry_price * 100
        if sl_move_pct < 0.3:
            return

        try:
            self.client.update_position(deal_id, stop_loss=new_sl)
            self._last_sl_update[deal_id] = new_sl

            if direction == "BUY":
                locked_pct = (new_sl - entry_price) / entry_price * 100
            else:
                locked_pct = (entry_price - new_sl) / entry_price * 100

            logger.info(
                f"WATCHDOG: Progressive SL for {epic}: {current_sl:.4f} -> {new_sl:.4f} "
                f"(P/L: +{pl_pct:.1f}%, locked: +{locked_pct:.1f}%, trail: {trail_pct}%)"
            )
            self.notifier.send(
                f"📈 <b>SL strammet: {epic}</b>\n"
                f"SL: {current_sl:.4f} → {new_sl:.4f}\n"
                f"Låst profit: +{locked_pct:.1f}% | Nuværende: +{pl_pct:.1f}%"
            )
        except Exception as e:
            logger.warning(f"Watchdog: Progressive SL update failed for {epic}: {e}")

    def _check_max_hold_time(self, deal_id, epic, direction, size, pl_pct):
        """Close position if max hold time exceeded AND position is losing or breakeven."""
        entry_time = self._entry_times.get(deal_id)
        if not entry_time:
            return False

        max_hours = self.risk.get_max_hold_hours(epic)
        hold_duration = datetime.now() - entry_time
        hold_hours = hold_duration.total_seconds() / 3600

        if hold_hours < max_hours:
            return False

        if pl_pct > 0.5:
            logger.info(
                f"WATCHDOG: Max hold exceeded for {epic} ({hold_hours:.1f}h) "
                f"but P/L is +{pl_pct:.1f}% — letting trailing stop handle exit"
            )
            return False

        try:
            status = "tab" if pl_pct < -0.5 else "breakeven"
            logger.warning(
                f"WATCHDOG: Max hold time closing {epic} ({status})! "
                f"Hold: {hold_hours:.1f}h > {max_hours}h, P/L: {pl_pct:+.1f}%"
            )
            self.client.close_position(deal_id, direction=direction, size=size)
            self._set_cooldown(epic)
            self._update_trade_db_by_deal(deal_id, pl_pct)
            self.notifier.send(
                f"⏰ <b>Max holdtid ({status}): {epic}</b>\n"
                f"Holdtid: {hold_hours:.1f} timer (max: {max_hours}h)\n"
                f"P/L: {pl_pct:+.1f}%\n"
                f"Kategori: {self.risk.get_coin_category(epic)}\n"
                f"Vindere beskyttes af trailing stop"
            )
            self._trigger_cycle_trade(epic, direction, pl_pct)
            return True
        except Exception as e:
            logger.error(f"Watchdog: Max hold close failed for {epic}: {e}")
        return False

    def _check_early_exit(self, deal_id, epic, direction, size, pl_pct):
        """Detect momentum acceleration with adverse candles and exit early."""
        entry_time = self._entry_times.get(deal_id)
        if entry_time:
            age_minutes = (datetime.now() - entry_time).total_seconds() / 60
            if age_minutes < 15:
                return False

        candle_data = self._candle_cache.get(epic)
        if candle_data and (time.time() - candle_data["timestamp"]) < self._candle_cache_ttl:
            candles = candle_data["candles"]
        else:
            try:
                prices = self.client.get_prices(epic, resolution="MINUTE_15", max_count=10)
                raw_candles = prices.get("prices", [])
                candles = []
                for c in raw_candles:
                    o = (c["openPrice"]["bid"] + c["openPrice"]["ask"]) / 2
                    cl = (c["closePrice"]["bid"] + c["closePrice"]["ask"]) / 2
                    candles.append({"open": o, "close": cl, "change_pct": (cl - o) / o * 100})
                self._candle_cache[epic] = {"candles": candles, "timestamp": time.time()}
            except Exception as e:
                logger.debug(f"Watchdog: Could not fetch candles for early exit {epic}: {e}")
                return False

        if len(candles) < 4:
            return False

        recent = candles[-4:]
        adverse_candles = []
        for c in recent:
            if direction == "BUY" and c["change_pct"] < -0.1:
                adverse_candles.append(abs(c["change_pct"]))
            elif direction == "SELL" and c["change_pct"] > 0.1:
                adverse_candles.append(abs(c["change_pct"]))

        if len(adverse_candles) < 3:
            return False

        accelerating = all(
            adverse_candles[i] > adverse_candles[i - 1]
            for i in range(1, len(adverse_candles))
        )

        if not accelerating:
            return False

        if len(adverse_candles) == 3 and -3.0 < pl_pct <= -1.0:
            partial_size = round(size * 0.5, 4)
            if partial_size > 0 and deal_id not in self._partial_taken:
                try:
                    self.client.close_position(deal_id, direction=direction, size=partial_size)
                    self._partial_taken.add(deal_id)
                    self._update_trade_db_by_deal(deal_id, pl_pct, partial=True)
                    logger.warning(
                        f"WATCHDOG: Early exit (50%) {epic} - 3 accelerating adverse candles, P/L: {pl_pct:+.1f}%"
                    )
                    self.notifier.send(
                        f"⚡ <b>Early exit (50%): {epic}</b>\n"
                        f"3 accelererende modsat-candles\n"
                        f"P/L: {pl_pct:+.1f}% | Lukket {partial_size} af {size}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"Watchdog: Early exit partial failed for {epic}: {e}")

        elif len(adverse_candles) >= 4:
            try:
                self.client.close_position(deal_id, direction=direction, size=size)
                self._set_cooldown(epic)
                self._update_trade_db_by_deal(deal_id, pl_pct)
                logger.warning(
                    f"WATCHDOG: Full early exit {epic} - {len(adverse_candles)} accelerating adverse candles"
                )
                self.notifier.send(
                    f"🚨 <b>Early exit (100%): {epic}</b>\n"
                    f"{len(adverse_candles)} accelererende modsat-candles\n"
                    f"P/L: {pl_pct:+.1f}%"
                )
                self._trigger_cycle_trade(epic, direction, pl_pct)
                return True
            except Exception as e:
                logger.error(f"Watchdog: Full early exit failed for {epic}: {e}")

        return False

    def _check_dynamic_tp(self, deal_id, epic, direction, entry_price, current_price, pl_pct, atr_pct, pos):
        """Extend TP when price is within 1% of target and momentum is positive."""
        extensions = self._tp_extensions.get(deal_id, 0)
        if extensions >= 2:
            return

        tp = pos["position"].get("takeProfit")
        if tp is None:
            return

        tp = float(tp)
        if tp == 0:
            return

        if direction == "BUY":
            dist_to_tp_pct = (tp - current_price) / current_price * 100
        else:
            dist_to_tp_pct = (current_price - tp) / current_price * 100

        if dist_to_tp_pct > 1.0 or dist_to_tp_pct < 0:
            return

        candle_data = self._candle_cache.get(epic)
        if not candle_data:
            return

        candles = candle_data["candles"]
        if len(candles) < 3:
            return

        last_3 = candles[-3:]
        if direction == "BUY":
            positive_momentum = all(c["change_pct"] > 0 for c in last_3)
        else:
            positive_momentum = all(c["change_pct"] < 0 for c in last_3)

        if not positive_momentum:
            return

        atr_extension = current_price * (atr_pct / 100) * 1.5
        if direction == "BUY":
            new_tp = round(tp + atr_extension, 5)
        else:
            new_tp = round(tp - atr_extension, 5)

        try:
            self.client.update_position(deal_id, take_profit=new_tp)
            self._tp_extensions[deal_id] = extensions + 1
            logger.info(
                f"WATCHDOG: TP extended for {epic} ({extensions + 1}/2): "
                f"{tp:.4f} -> {new_tp:.4f} (ATR-based)"
            )
            self.notifier.send(
                f"🎯 <b>TP udvidet: {epic}</b> ({extensions + 1}/2)\n"
                f"Gammelt TP: {tp:.4f}\n"
                f"Nyt TP: {new_tp:.4f}\n"
                f"P/L: +{pl_pct:.1f}% | Positiv momentum"
            )
        except Exception as e:
            logger.warning(f"Watchdog: TP extension failed for {epic}: {e}")

    def _update_trade_db(self, deal_id, exit_price, pl_pct, size, entry_price, partial=False):
        """Update trade DB after watchdog closes a position."""
        if not self.executor:
            return
        if partial:
            partial_pl = (exit_price - entry_price) * size if pl_pct >= 0 else (entry_price - exit_price) * size
            self.executor.update_trade_close(deal_id, exit_price, partial_pl, partial=True)
        else:
            # Estimate P/L in EUR from percentage and entry price * size
            # This is approximate - reconcile_closed_trades will correct later
            estimated_pl = pl_pct / 100 * entry_price * size
            self.executor.update_trade_close(deal_id, exit_price, estimated_pl)

    def _update_trade_db_by_deal(self, deal_id, pl_pct, partial=False):
        """Update trade DB when we only have deal_id and pl_pct (no entry_price in scope)."""
        if not self.executor:
            return
        try:
            import sqlite3
            db = self.executor._get_db()
            cursor = db.execute(
                "SELECT entry_price, size FROM trades WHERE deal_id = ? AND status = 'OPEN'",
                (deal_id,)
            )
            row = cursor.fetchone()
            db.close()
            if row:
                entry_price, size = row
                estimated_pl = pl_pct / 100 * entry_price * size
                exit_price = entry_price * (1 + pl_pct / 100)
                self.executor.update_trade_close(deal_id, round(exit_price, 5), estimated_pl, partial=partial)
        except Exception as e:
            logger.error(f"Watchdog: DB update by deal failed: {e}")

    def _trigger_cycle_trade(self, epic, closed_direction, closed_pl_pct):
        """On position close, check for reversal opportunity (cycle trading)."""
        if not self._cycle_callback:
            return

        cooldown = self._cycle_cooldowns.get(epic)
        if cooldown and (datetime.now() - cooldown).total_seconds() < 1800:
            logger.info(f"Cycle trade {epic}: cooldown active, skipping")
            return

        self._cycle_cooldowns[epic] = datetime.now()

        opposite_direction = "SELL" if closed_direction == "BUY" else "BUY"
        thread = threading.Thread(
            target=self._cycle_callback,
            args=(epic, opposite_direction),
            daemon=True,
        )
        thread.start()
        logger.info(f"Cycle trade: queued re-analysis for {epic} ({opposite_direction})")

    def _check_scale_in(self, open_positions):
        """Check if any position qualifies for scale-in (every ~10 min)."""
        for pos in open_positions:
            deal_id = pos["position"]["dealId"]
            if deal_id in self._scale_in_done:
                continue

            epic = pos["market"]["epic"]
            direction = pos["position"]["direction"]
            entry_price = pos["position"]["level"]
            current_price = pos["market"]["bid"] if direction == "BUY" else pos["market"]["offer"]

            if direction == "BUY":
                pl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pl_pct = (entry_price - current_price) / entry_price * 100

            if pl_pct <= 0:
                continue

            entry_conf = self._entry_confidence.get(deal_id)
            if entry_conf is None:
                continue

            try:
                self._scale_in_callback(epic, direction, deal_id, entry_conf, pos)
            except Exception as e:
                logger.error(f"Watchdog: Scale-in check failed for {epic}: {e}")

    def mark_scale_in_done(self, deal_id):
        """Mark that a scale-in was already done for this position."""
        self._scale_in_done.add(deal_id)

    def _log_status_summary(self, open_positions):
        """Log a periodic summary so we can verify the watchdog is alive and evaluating."""
        summaries = []
        worst_pl = 0
        for pos in open_positions:
            epic = pos["market"]["epic"]
            direction = pos["position"]["direction"]
            entry_price = pos["position"]["level"]
            current_price = pos["market"]["bid"] if direction == "BUY" else pos["market"]["offer"]
            sl = pos["position"].get("stopLevel")

            if direction == "BUY":
                pl_pct = (current_price - entry_price) / entry_price * 100
            else:
                pl_pct = (entry_price - current_price) / entry_price * 100

            worst_pl = min(worst_pl, pl_pct)

            sl_str = f"SL:{sl:.4f}" if sl else "NO SL!"
            be_str = " [BE]" if pos["position"]["dealId"] in self._breakeven_set else ""
            summaries.append(f"{epic}:{pl_pct:+.1f}%{be_str} {sl_str}")

            if not sl:
                logger.warning(f"WATCHDOG ALERT: {epic} has NO STOP LOSS! deal={pos['position']['dealId']}")

        summary_line = " | ".join(summaries)
        logger.info(
            f"WATCHDOG alive (iter={self._iteration_count}): {len(open_positions)} pos | "
            f"worst={worst_pl:+.1f}% | BE={len(self._breakeven_set)} | "
            f"partial={len(self._partial_taken)} | {summary_line}"
        )

    def get_status(self):
        """Get watchdog status for /status command."""
        hold_times = {}
        for deal_id, entry_time in self._entry_times.items():
            hours = (datetime.now() - entry_time).total_seconds() / 3600
            hold_times[deal_id] = f"{hours:.1f}h"

        return {
            "running": self._running,
            "interval": self.check_interval,
            "tracked_positions": len(self._peak_prices),
            "partial_taken": len(self._partial_taken),
            "breakeven_set": len(self._breakeven_set),
            "atr_cache": {k: f"{v:.2f}%" for k, v in self._atr_cache.items()},
            "hold_times": hold_times,
            "tp_extensions": dict(self._tp_extensions),
            "scale_ins": len(self._scale_in_done),
        }

    def get_debug_info(self):
        """Get detailed debug info for /ai_debug command."""
        info = {
            "atr_per_coin": {k: f"{v:.2f}%" for k, v in self._atr_cache.items()},
            "hold_times": {},
            "max_hold_limits": {},
            "tp_extensions": dict(self._tp_extensions),
            "breakeven_positions": len(self._breakeven_set),
            "partial_profit_positions": len(self._partial_taken),
            "scale_ins_done": len(self._scale_in_done),
            "cycle_cooldowns": {},
        }

        for deal_id, entry_time in self._entry_times.items():
            hours = (datetime.now() - entry_time).total_seconds() / 3600
            info["hold_times"][deal_id[:8]] = f"{hours:.1f}h"

        for epic in self._atr_cache:
            max_h = self.risk.get_max_hold_hours(epic)
            cat = self.risk.get_coin_category(epic)
            info["max_hold_limits"][epic] = f"{max_h}h ({cat})"

        for epic, cooldown_time in self._cycle_cooldowns.items():
            remaining = 1800 - (datetime.now() - cooldown_time).total_seconds()
            if remaining > 0:
                info["cycle_cooldowns"][epic] = f"{remaining/60:.0f}min remaining"

        return info
