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

import pandas as pd

from src.strategy.chart_analysis import ChartAnalysis

logger = logging.getLogger(__name__)


class PositionWatchdog:
    """Fast position monitor - checks open positions every 10-15 seconds."""

    def __init__(self, client, risk_manager, notifier, config):
        self.client = client
        self.risk = risk_manager
        self.notifier = notifier

        watchdog_cfg = config.get("watchdog", {})
        self.check_interval = watchdog_cfg.get("check_interval", 12)
        self.breakeven_trigger_pct = watchdog_cfg.get("breakeven_trigger_pct", 2.5)
        self.trailing_trigger_pct = watchdog_cfg.get("trailing_trigger_pct", 2.5)
        self.trailing_atr_mult = watchdog_cfg.get("trailing_atr_mult", 1.5)
        self.partial_profit_pct = watchdog_cfg.get("partial_profit_pct", 6.0)
        self.partial_close_ratio = watchdog_cfg.get("partial_close_ratio", 0.3)

        # Internal state
        self._running = False
        self._thread = None
        self._atr_cache = {}           # {epic: atr_pct} - updated by main scan
        self._peak_prices = {}         # {deal_id: best price seen}
        self._partial_taken = set()    # deal_ids where partial profit was taken
        self._breakeven_set = set()    # deal_ids where stop moved to break-even
        self._entry_times = {}         # {deal_id: datetime} - for max hold time
        self._iteration_count = 0      # for periodic tasks
        self._position_regimes = {}    # {deal_id: regime} - regime at entry

        # Early exit state
        self._candle_cache = {}        # {epic: {"candles": [...], "timestamp": float}}
        self._candle_cache_ttl = 300   # 5 minutes

        # Market structure cache for exit decisions
        self._structure_cache = {}     # {epic: {"structure": dict, "timestamp": float}}
        self._structure_cache_ttl = 600  # 10 minutes

        # Dynamic TP state
        self._tp_extensions = {}       # {deal_id: count} - max 2 per position

        # Cycle trading state
        self._cycle_cooldowns = {}     # {epic: datetime} - 30 min cooldown
        self._cycle_callback = None    # Set by main_ai.py for re-analysis

        # Progressive trailing SL state
        self._last_sl_update = {}      # {deal_id: last_sl_price} - avoid API spam
        self.progressive_sl_trigger = watchdog_cfg.get("progressive_sl_trigger_pct", 3.0)
        self.progressive_sl_trail = watchdog_cfg.get("progressive_sl_trail_pct", 1.0)

        # Profit pullback close - actively close when giving back profit
        self.pullback_peak_trigger = watchdog_cfg.get("pullback_peak_trigger_pct", 4.0)
        self.pullback_min_profit_pct = watchdog_cfg.get("pullback_min_profit_pct", 1.5)
        self.pullback_close_pct = watchdog_cfg.get("pullback_close_pct", 0.75)  # fallback only

        # Scale-in state
        self._scale_in_done = set()    # deal_ids that already got scale-in
        self._entry_confidence = {}    # {deal_id: confidence} - confidence at entry
        self._scale_in_callback = None # Set by main_ai.py for re-evaluation

        # References set by main*.py
        self.ai_analyst = None
        self.signal_engine = None
        self.executor = None  # For cooldown tracking
        self.time_bias = None  # For sentiment-based night mode
        self.mtf = None  # MultiTimeframeAnalyzer for daily trend context

        # Post-trade analysis and hard rules callbacks
        self._post_trade_callback = None   # Called with (deal_id, epic) on close
        self._trade_result_callback = None  # Called with (profit_loss) on close

        logger.info(
            f"Watchdog initialized (interval={self.check_interval}s, "
            f"breakeven={self.breakeven_trigger_pct}%, "
            f"pullback_close=peak>{self.pullback_peak_trigger}%+adaptive_drop+min{self.pullback_min_profit_pct}%, "
            f"partial={self.partial_profit_pct}%@{self.partial_close_ratio*100:.0f}%)"
        )

    def _set_cooldown(self, epic):
        """Set trade cooldown for an epic after watchdog closes a position."""
        if self.executor:
            self.executor._recently_traded[epic] = datetime.now()

    def _is_trend_aligned(self, deal_id, direction):
        """Check if position direction is aligned with the regime at entry."""
        regime = self._position_regimes.get(deal_id, "")
        if not regime:
            return False
        if direction == "BUY" and "UP" in regime:
            return True
        if direction == "SELL" and "DOWN" in regime:
            return True
        return False

    def _get_market_structure(self, epic):
        """Get cached market structure for an epic. Fetches 1H candles if stale."""
        cached = self._structure_cache.get(epic)
        if cached and (time.time() - cached["timestamp"]) < self._structure_cache_ttl:
            return cached["structure"]

        try:
            prices = self.client.get_prices(epic, resolution="HOUR", max_count=100)
            raw = prices.get("prices", [])
            if len(raw) < 30:
                return None

            rows = []
            for c in raw:
                rows.append({
                    "open": (c["openPrice"]["bid"] + c["openPrice"]["ask"]) / 2,
                    "high": (c["highPrice"]["bid"] + c["highPrice"]["ask"]) / 2,
                    "low": (c["lowPrice"]["bid"] + c["lowPrice"]["ask"]) / 2,
                    "close": (c["closePrice"]["bid"] + c["closePrice"]["ask"]) / 2,
                })
            df = pd.DataFrame(rows)
            structure = ChartAnalysis.detect_market_structure(df)
            self._structure_cache[epic] = {"structure": structure, "timestamp": time.time()}
            return structure
        except Exception as e:
            logger.debug(f"Watchdog: Could not fetch market structure for {epic}: {e}")
            return None

    def _is_structure_aligned(self, direction, epic):
        """Check if position direction aligns with current market structure.

        Returns True if: SHORT in BEARISH_IMPULSE, or LONG in BULLISH_IMPULSE.
        This means the trade is with the structural trend and should be given more room.
        """
        structure = self._get_market_structure(epic)
        if not structure:
            return False

        struct_type = structure.get("structure", "")
        if direction == "SELL" and struct_type == "BEARISH_IMPULSE":
            return True
        if direction == "BUY" and struct_type == "BULLISH_IMPULSE":
            return True
        return False

    def _calculate_adaptive_pullback(self, epic, direction, pl_pct, deal_id=None):
        """Calculate adaptive pullback threshold based on ATR, trend, and profit level.

        Returns pullback_pct clamped to [0.5%, 3.0%].
        """
        atr_pct = self._atr_cache.get(epic, 2.0)
        base_pullback = atr_pct * 0.75

        # Trend bonus: position aligned with entry regime gets wider pullback tolerance
        if deal_id and self._is_trend_aligned(deal_id, direction):
            base_pullback *= 1.5

        # Daily trend bonus from MTF: with daily trend = 2x wider, against = 0.5x tighter
        if self.mtf:
            try:
                htf = self.mtf.get_higher_tf_context(epic)
                daily_trend = htf.get("daily_trend", "NEUTRAL")
                if (direction == "BUY" and daily_trend == "UP") or \
                   (direction == "SELL" and daily_trend == "DOWN"):
                    base_pullback *= 2.0  # With daily trend: let winners run
                elif (direction == "BUY" and daily_trend == "DOWN") or \
                     (direction == "SELL" and daily_trend == "UP"):
                    base_pullback *= 0.5  # Against daily trend: tighter exit
            except Exception:
                pass

        # Market structure bonus: structure-aligned trades get 1.5x wider pullback
        if self._is_structure_aligned(direction, epic):
            base_pullback *= 1.5

        # Profit tightening: protect larger gains more aggressively
        if pl_pct > 8.0:
            base_pullback *= 0.5
        elif pl_pct > 4.0:
            base_pullback *= 0.75

        # Clamp to reasonable range
        return max(0.5, min(3.0, base_pullback))

    def update_atr(self, epic, atr_pct):
        """Called by main scan cycle to cache latest ATR for each coin."""
        self._atr_cache[epic] = atr_pct

    def track_entry(self, deal_id, epic, confidence=None, regime=None):
        """Track position entry time, confidence, and regime for max hold and scale-in."""
        self._entry_times[deal_id] = datetime.now()
        if confidence is not None:
            self._entry_confidence[deal_id] = confidence
        if regime is not None:
            self._position_regimes[deal_id] = regime

    def fix_open_positions_rr(self):
        """Fix R:R on all open positions - move TP to ensure min 2.0:1 R:R.

        Called at startup to fix positions opened with old bad R:R settings.
        """
        try:
            positions = self.client.get_positions()
            if not positions:
                return
            for pos in positions.get("positions", []):
                market = pos.get("market", {})
                position = pos.get("position", {})
                epic = market.get("epic", "?")
                deal_id = position.get("dealId", "")
                direction = position.get("direction", "BUY")
                entry_price = float(position.get("level", 0))
                current_sl = position.get("stopLevel")
                current_tp = position.get("profitLevel")

                if not entry_price:
                    continue

                current_sl = float(current_sl) if current_sl else None
                current_tp = float(current_tp) if current_tp else None

                # If SL or TP is missing, recalculate from ATR
                atr_pct = self._atr_cache.get(epic, 0)
                needs_update = False
                new_sl = current_sl
                new_tp = current_tp

                if not current_sl:
                    # SL missing - recalculate using ATR or default 3%
                    if atr_pct > 0:
                        new_sl = self.risk.calculate_atr_stop_loss(entry_price, direction, atr_pct)
                    else:
                        sl_pct = 3.0  # safe default
                        if direction == "BUY":
                            new_sl = round(entry_price * (1 - sl_pct / 100), 5)
                        else:
                            new_sl = round(entry_price * (1 + sl_pct / 100), 5)
                    needs_update = True
                    logger.warning(f"[R:R Fix] {epic}: SL was MISSING! Setting SL={new_sl:.5f}")

                if not current_tp:
                    # TP missing - recalculate
                    new_tp = self.risk.calculate_take_profit(entry_price, direction, atr_pct, sl_price=new_sl)
                    needs_update = True
                    logger.warning(f"[R:R Fix] {epic}: TP was MISSING! Setting TP={new_tp:.5f}")

                # Check R:R ratio
                sl_distance = abs(entry_price - new_sl)
                tp_distance = abs(new_tp - entry_price)

                if sl_distance == 0:
                    continue

                rr_ratio = tp_distance / sl_distance

                if rr_ratio < 1.5:
                    new_tp_distance = sl_distance * 1.5
                    if direction == "BUY":
                        new_tp = round(entry_price + new_tp_distance, 5)
                    else:
                        new_tp = round(entry_price - new_tp_distance, 5)
                    needs_update = True
                    new_rr = 1.5
                    logger.info(
                        f"[R:R Fix] {epic}: R:R {rr_ratio:.2f}:1 -> {new_rr:.2f}:1 | "
                        f"TP {current_tp} -> {new_tp:.5f}"
                    )
                else:
                    new_rr = rr_ratio

                if not needs_update:
                    logger.info(f"[R:R Fix] {epic}: R:R already OK ({rr_ratio:.2f}:1)")
                    continue

                result = self.client.update_position(deal_id, stop_loss=new_sl, take_profit=new_tp)
                if result:
                    sl_str = f"SL: {current_sl} → {new_sl:.2f}\n" if current_sl != new_sl else ""
                    tp_str = f"TP: {current_tp} → {new_tp:.2f}\n" if current_tp != new_tp else ""
                    self.notifier.send(
                        f"🔧 <b>R:R Fix: {epic}</b>\n"
                        f"{sl_str}{tp_str}"
                        f"R:R: {rr_ratio:.2f}:1 → {new_rr:.2f}:1"
                    )
                else:
                    logger.error(f"[R:R Fix] Failed to update {epic} TP")

        except Exception as e:
            logger.error(f"[R:R Fix] Error: {e}")

    def start(self):
        """Start the watchdog background thread."""
        self._running = True
        # Fix R:R on existing positions before starting monitor loop
        self.fix_open_positions_rr()
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
            self._position_regimes.pop(deal_id, None)

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

        # -- Rule 3c: PROFIT PULLBACK CLOSE (adaptive) --
        adaptive_pullback = self._calculate_adaptive_pullback(epic, direction, pl_pct, deal_id)
        if peak_profit_pct >= self.pullback_peak_trigger and drawdown_from_peak_pct >= adaptive_pullback and pl_pct >= self.pullback_min_profit_pct:
            try:
                logger.warning(
                    f"WATCHDOG: PROFIT PULLBACK closing {epic}! "
                    f"Peak P/L: +{peak_profit_pct:.1f}%, Now: +{pl_pct:.1f}%, "
                    f"Gave back: {drawdown_from_peak_pct:.2f}% from peak (adaptive threshold: {adaptive_pullback:.2f}%)"
                )
                self.client.close_position(deal_id, direction=direction, size=size)
                self._set_cooldown(epic)
                self._update_trade_db(deal_id, current_price, pl_pct, size, entry_price, epic=epic,
                                      exit_reason=f"profit_pullback|peak={peak_profit_pct:.1f}%|pullback={drawdown_from_peak_pct:.2f}%|threshold={adaptive_pullback:.2f}%")
                self.notifier.send(
                    f"💰 <b>Profit taget: {epic}</b>\n"
                    f"Peak: +{peak_profit_pct:.1f}% | Lukket: +{pl_pct:.1f}%\n"
                    f"Pullback fra top: {drawdown_from_peak_pct:.2f}% (grænse: {adaptive_pullback:.2f}%)\n"
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
                    self._update_trade_db(deal_id, current_price, partial_pl, partial_size, entry_price, partial=True, epic=epic)
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

        # -- Rule 6: ATR-based trailing stop (trend-aware) --
        # Trend-aligned positions get 1.5x wider trailing distance
        if self._is_trend_aligned(deal_id, direction):
            trailing_distance *= 1.5
        if pl_pct >= self.trailing_trigger_pct and peak_profit_pct > 0 and drawdown_from_peak_pct > trailing_distance:
            try:
                logger.warning(
                    f"WATCHDOG: Trailing stop triggered for {epic}! "
                    f"Peak: {peak:.4f}, Now: {current_price:.4f}, "
                    f"Drawdown: {drawdown_from_peak_pct:.1f}% > {trailing_distance:.1f}%"
                )
                self.client.close_position(deal_id, direction=direction, size=size)
                self._set_cooldown(epic)
                self._update_trade_db(deal_id, current_price, pl_pct, size, entry_price, epic=epic,
                                      exit_reason=f"trailing_stop|peak={peak:.4f}|drawdown={drawdown_from_peak_pct:.1f}%|trail={trailing_distance:.1f}%")
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

        # Structure override: don't close structure-aligned trades on sentiment alone
        if self._is_structure_aligned(direction, epic):
            logger.info(
                f"WATCHDOG: Skipping sentiment close for {epic} — structure-aligned {direction} "
                f"overrides {bias} time bias (P/L: +{pl_pct:.1f}%)"
            )
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
            self._update_trade_db_by_deal(deal_id, pl_pct, epic=epic,
                                          exit_reason=f"sentiment_close|bias={bias}|avg_return={avg_return:+.3f}%")
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
        """Move server-side SL up as position profits grow. ATR-adaptive trail distance."""
        atr_pct = self._atr_cache.get(epic, 2.0)
        # ATR-based trail: 0.5 * ATR, or 0.75 * ATR for trend-aligned
        if self._is_trend_aligned(deal_id, direction):
            trail_pct = max(0.5, min(2.5, atr_pct * 0.75))
        else:
            trail_pct = max(0.5, min(2.5, atr_pct * 0.5))

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

        # Structure-aligned trades are NEVER closed by max-hold — SL handles risk
        if self._is_structure_aligned(direction, epic):
            hold_hours = (datetime.now() - entry_time).total_seconds() / 3600
            if hold_hours >= max_hours:
                logger.info(
                    f"WATCHDOG: Max hold exceeded for {epic} ({hold_hours:.1f}h) "
                    f"but STRUCTURE-ALIGNED ({direction}) — SL handles risk, skipping time-close"
                )
            return False

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
            self._update_trade_db_by_deal(deal_id, pl_pct, epic=epic,
                                          exit_reason=f"max_hold_time|hold={hold_hours:.1f}h|max={max_hours}h|category={self.risk.get_coin_category(epic)}")
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

        # Structure override: if the trade is aligned with market structure,
        # don't panic-exit on short-term adverse candles — the trend supports us.
        # Only skip for 3-candle partial exit; still honor 4+ candle full exit
        # but require the trade to be losing more than 5% (real danger, not noise).
        structure_aligned = self._is_structure_aligned(direction, epic)

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
            # Structure override: skip 3-candle exit if trade is with the trend
            if structure_aligned:
                logger.info(
                    f"WATCHDOG: Skipping early exit for {epic} — structure-aligned {direction}, "
                    f"3 adverse candles but trend supports holding (P/L: {pl_pct:+.1f}%)"
                )
                return False

            partial_size = round(size * 0.5, 4)
            if partial_size > 0 and deal_id not in self._partial_taken:
                try:
                    self.client.close_position(deal_id, direction=direction, size=partial_size)
                    self._partial_taken.add(deal_id)
                    self._update_trade_db_by_deal(deal_id, pl_pct, partial=True, epic=epic,
                                                  exit_reason="early_exit_partial|adverse_candles=3")
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
            # Structure override: if trade is with the trend, only close on severe loss (> -5%)
            if structure_aligned and pl_pct > -5.0:
                logger.info(
                    f"WATCHDOG: Holding {epic} despite {len(adverse_candles)} adverse candles — "
                    f"structure-aligned {direction}, P/L {pl_pct:+.1f}% not critical yet (threshold: -5%)"
                )
                return False

            try:
                self.client.close_position(deal_id, direction=direction, size=size)
                self._set_cooldown(epic)
                self._update_trade_db_by_deal(deal_id, pl_pct, epic=epic,
                                              exit_reason=f"early_exit_full|adverse_candles={len(adverse_candles)}")
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

    def _update_trade_db(self, deal_id, exit_price, pl_pct, size, entry_price, partial=False, epic=None, exit_reason=None):
        """Update trade DB after watchdog closes a position."""
        if not self.executor:
            return
        if partial:
            partial_pl = (exit_price - entry_price) * size if pl_pct >= 0 else (entry_price - exit_price) * size
            self.executor.update_trade_close(deal_id, exit_price, partial_pl, partial=True, epic=epic)
        else:
            estimated_pl = pl_pct / 100 * entry_price * size
            self.executor.update_trade_close(deal_id, exit_price, estimated_pl, epic=epic, exit_reason=exit_reason)
            # Notify hard rules and post-trade analyzer on full close
            self._fire_close_callbacks(deal_id, epic, estimated_pl)

    def _update_trade_db_by_deal(self, deal_id, pl_pct, partial=False, epic=None, exit_reason=None):
        """Update trade DB when we only have deal_id and pl_pct (no entry_price in scope)."""
        if not self.executor:
            return
        try:
            db = self.executor._get_db()
            # Try deal_id match first, then epic match
            cursor = db.execute(
                "SELECT entry_price, size, epic FROM trades WHERE deal_id = ? AND status = 'OPEN'",
                (deal_id,)
            )
            row = cursor.fetchone()
            if not row and epic:
                cursor = db.execute(
                    "SELECT entry_price, size, epic FROM trades WHERE epic = ? AND status = 'OPEN' "
                    "ORDER BY timestamp DESC LIMIT 1",
                    (epic,)
                )
                row = cursor.fetchone()
            db.close()
            if row:
                entry_price, size, matched_epic = row
                estimated_pl = pl_pct / 100 * entry_price * size
                exit_price = entry_price * (1 + pl_pct / 100)
                self.executor.update_trade_close(deal_id, round(exit_price, 5), estimated_pl, partial=partial, epic=matched_epic, exit_reason=exit_reason)
                if not partial:
                    self._fire_close_callbacks(deal_id, matched_epic, estimated_pl)
            else:
                logger.warning(f"Watchdog: No matching OPEN trade for deal_id={deal_id} epic={epic}")
        except Exception as e:
            logger.error(f"Watchdog: DB update by deal failed: {e}")

    def _fire_close_callbacks(self, deal_id, epic, profit_loss):
        """Fire post-trade analysis and hard rules callbacks on position close."""
        try:
            if self._trade_result_callback:
                self._trade_result_callback(profit_loss)
        except Exception as e:
            logger.error(f"Trade result callback error: {e}")
        try:
            if self._post_trade_callback:
                self._post_trade_callback(deal_id, epic)
        except Exception as e:
            logger.error(f"Post-trade callback error: {e}")

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
            args=(epic, opposite_direction, closed_pl_pct),
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
            struct_str = " [SA]" if self._is_structure_aligned(direction, epic) else ""
            summaries.append(f"{epic}:{pl_pct:+.1f}%{be_str}{struct_str} {sl_str}")

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

        # Market structure cache
        info["market_structure"] = {}
        for epic, cached in self._structure_cache.items():
            s = cached.get("structure")
            if s:
                age = int(time.time() - cached["timestamp"])
                info["market_structure"][epic] = f"{s['structure']} (bias={s['bias']}, {age}s ago)"

        return info
