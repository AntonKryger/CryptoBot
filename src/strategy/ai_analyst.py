"""
AI Analyst for CryptoBot - Uses Claude API to analyze market data
and make intelligent trading decisions.
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime

import anthropic

from src.strategy.chart_analysis import ChartAnalysis

logger = logging.getLogger(__name__)

# Will be set by main_ai.py
_news_monitor = None

SYSTEM_PROMPT = """Du er en erfaren, selvsikker daytrader. Ikke en analytiker. Ikke en compliance-officer. Du handler crypto CFD'er på EUR 95.000 konto.

DIN STIL: Rolig, direkte, præcis. Max 200 ord. Ingen forbehold. Ingen disclaimers.

REGLER:
- HOLD kræver præcis formulering: hvad venter du på, ved hvilket niveau, hvad trigger entry
- Ranging marked = definer konkret mean-reversion entry med niveau, TP og SL
- "Markedet er uklart" er ALDRIG et acceptabelt svar
- Short lige så villigt som long. Crypto falder hurtigt.
- Timeframe alignment er din lov: 15m+1H+4H skal pege samme vej

TRENDING: Køb pullbacks i uptrend, sælg rallies i downtrend. EMA 9/21 styrer.
RANGING (ADX<20): Mean-reversion ved ekstremer. Range_pos <25% = BUY, >75% = SELL. Definer entry, TP, SL.
MOMENTUM: ROC-6 >1.5% med trend = aggressiv entry.
EXHAUSTION: 3%+ move i 12t = det nemme er ovre. Kræv ny katalysator.

CONFIDENCE:
7 = minimum for trade. 8 = counter-trend. 9-10 = fuld alignment alle TF.
Under 7 = HOLD, men formuler præcist hvad du venter på.

Svar KUN med valid JSON:
{"signal": "BUY|SELL|HOLD", "confidence": 1-10, "reasoning": "din analyse"}"""


class AIAnalyst:
    """Uses Claude API to analyze market data and generate trading signals."""

    def __init__(self, config):
        ai_cfg = config.get("ai", {})
        self.api_key = ai_cfg.get("anthropic_api_key", "")
        self.model = ai_cfg.get("model", "claude-haiku-4-5-20251001")
        self.max_tokens = ai_cfg.get("max_tokens", 300)
        self.min_confidence = ai_cfg.get("min_confidence", 5)

        if not self.api_key:
            raise ValueError("Anthropic API key not configured (ai.anthropic_api_key)")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self._last_request = 0
        self._request_delay = 1.0  # seconds between API calls
        self.trade_executor = None  # Set by main_ai.py for recent P/L feedback
        self.news_monitor = None    # Set by main_ai.py for breaking news
        self.position_sync = None   # Set by main_ai.py for portfolio awareness
        self.rule_db_path = ai_cfg.get("rule_db_path", "data/trades.db")  # Rule bot DB for cross-learning

        # Chat conversation state (persisted to SQLite)
        self._max_history = 50  # max exchanges to send to API
        self._max_token_estimate = 80000  # rough token guard
        self._active_strategies = []  # Set by main_ai.py from weekly evaluator
        self._feedback_db_path = config.get("database", {}).get("path", "data_ai/trades.db")
        self._init_feedback_table()

        logger.info(f"AI Analyst initialized (model: {self.model}, min_confidence: {self.min_confidence})")

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request = time.time()

    def analyze(self, epic, df, sentiment_data=None, rule_signal=None, regime_data=None):
        """Analyze market data using Claude and return a trading signal.

        Args:
            epic: Trading pair (e.g. "BTCUSD")
            df: DataFrame with calculated indicators
            sentiment_data: Optional dict from CryptoPanic/Reddit sentiment
            rule_signal: Optional dict with rule-based bot's signal
            regime_data: Optional dict with {"regime": str, "adx": float}

        Returns:
            (signal, details) tuple - same format as SignalEngine.get_signal()
        """
        if df is None or len(df) < 50:
            return "HOLD", {"reason": "Insufficient data for AI analysis"}

        latest = df.iloc[-1]
        prompt = self._build_prompt(epic, df, sentiment_data, rule_signal=rule_signal, regime_data=regime_data)

        try:
            self._rate_limit()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()
            # Strip markdown code blocks if present
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3].strip()
            result = json.loads(result_text)

            signal = result.get("signal", "HOLD").upper()
            confidence = int(result.get("confidence", 0))
            reasoning = result.get("reasoning", "No reasoning provided")

            details = {
                "close": latest["close"],
                "rsi": latest.get("rsi", 0),
                "range_position": latest.get("range_position", 50),
                "range_pct": latest.get("range_pct", 0),
                "range_high": latest.get("range_high", 0),
                "range_low": latest.get("range_low", 0),
                "bb_pct": latest.get("bb_pct", 0.5),
                "volume_spike": latest.get("volume_spike", False),
                "atr_pct": latest.get("atr_pct", 0),
                "sentiment": sentiment_data,
                "ai_confidence": confidence,
                "ai_reasoning": reasoning,
                "ai_model": self.model,
                "signal_strength": confidence,
                "zone": self._get_zone(latest.get("range_position", 50)),
                "regime": regime_data.get("regime") if regime_data else None,
                "adx": regime_data.get("adx", 0) if regime_data else 0,
                "alignment_score": regime_data.get("alignment", {}).get("alignment_score") if regime_data else None,
            }

            # HARD GATE: Multi-TF alignment check
            if signal in ("BUY", "SELL"):
                alignment_info = regime_data.get("alignment") if regime_data else None
                if alignment_info:
                    from src.strategy.technical_analysis import MultiTFAnalysis
                    passes, gate_reason = MultiTFAnalysis.passes_alignment_gate(alignment_info, min_score=2)
                    if not passes:
                        details["reason"] = f"ALIGNMENT GATE: {gate_reason}"
                        details["ai_original_signal"] = signal
                        logger.warning(f"AI {epic}: {signal} BLOCKED by alignment gate ({gate_reason})")
                        return "HOLD", details

            # Boost confidence when rule-based bot agrees
            if rule_signal and signal in ("BUY", "SELL") and rule_signal.get("signal") == signal:
                rule_score = rule_signal.get("score", 0)
                if rule_score >= 4:  # rule-based bot also triggered
                    confidence = min(10, confidence + 2)
                    details["bot_agreement"] = True
                    logger.info(f"AI {epic}: Both bots agree on {signal}! Confidence boosted to {confidence}")
                elif rule_score >= 2:  # rule-based bot leaning same way
                    confidence = min(10, confidence + 1)
                    details["bot_agreement"] = "partial"
                    logger.info(f"AI {epic}: Rule-bot leaning {signal} (score={rule_score}), confidence +1 to {confidence}")

            details["ai_confidence"] = confidence  # update after boost

            # E3: Confluence-based confidence cap
            if signal in ("BUY", "SELL") and confidence >= 7:
                alignment_count = 0
                # 1H EMA alignment
                ema_fast_val = latest.get("ema_9", latest.get("close"))
                ema_slow_val = latest.get("ema_21", latest.get("close"))
                if (signal == "BUY" and ema_fast_val > ema_slow_val) or \
                   (signal == "SELL" and ema_fast_val < ema_slow_val):
                    alignment_count += 1
                # Time bias
                if regime_data:
                    tb = regime_data.get("time_bias")
                    if (signal == "BUY" and tb == "BULLISH") or (signal == "SELL" and tb == "BEARISH"):
                        alignment_count += 1
                # Regime
                regime_val = regime_data.get("regime") if regime_data else None
                if (signal == "BUY" and regime_val in ("TRENDING_UP", "RANGING")) or \
                   (signal == "SELL" and regime_val in ("TRENDING_DOWN", "RANGING")):
                    alignment_count += 1
                # RSI not overextended
                rsi_val = latest.get("rsi", 50)
                if (signal == "BUY" and rsi_val < 65) or (signal == "SELL" and rsi_val > 35):
                    alignment_count += 1
                # Higher TF alignment
                htf_data = regime_data.get("htf_context") if regime_data else None
                if htf_data:
                    htf_align = htf_data.get("trend_alignment", "")
                    if (signal == "BUY" and htf_align == "ALIGNED_UP") or \
                       (signal == "SELL" and htf_align == "ALIGNED_DOWN"):
                        alignment_count += 1
                    elif htf_data.get("h4_ema_bullish") == (signal == "BUY"):
                        alignment_count += 1

                if alignment_count < 2:
                    confidence = min(confidence, 5)
                    details["ai_confidence"] = confidence
                    details["confluence_cap"] = f"Only {alignment_count} factors aligned, capped at 5"
                    logger.info(f"AI {epic}: Confluence cap — only {alignment_count} aligned, conf capped to {confidence}")
                elif alignment_count < 3:
                    confidence = min(confidence, 7)
                    details["ai_confidence"] = confidence
                    if confidence < int(result.get("confidence", 0)):
                        details["confluence_cap"] = f"{alignment_count} factors aligned, capped at 7"

            # Only trigger trade if confidence meets minimum
            if signal in ("BUY", "SELL") and confidence < self.min_confidence:
                details["reason"] = f"AI {signal} but low confidence ({confidence}/{self.min_confidence})"
                details["ai_original_signal"] = signal
                logger.info(f"AI {epic}: {signal} rejected (confidence {confidence} < {self.min_confidence})")
                return "HOLD", details

            # HARD FILTER 1: Counter-trend blocker (only block low confidence counter-trend)
            if signal in ("BUY", "SELL"):
                ema_fast = latest.get("ema_9", latest.get("close"))
                ema_slow = latest.get("ema_21", latest.get("close"))
                roc_3 = latest.get("roc_3", 0)
                rsi = latest.get("rsi", 50)

                # Only block counter-trend at low confidence (allow high-confidence counter-trend)
                if signal == "BUY" and ema_fast < ema_slow and roc_3 < -0.5 and confidence < 8:
                    details["reason"] = f"BLOCKED: Low-conf BUY against bearish trend (EMA9<EMA21, ROC={roc_3:+.2f}%)"
                    logger.warning(f"AI {epic}: BUY BLOCKED - counter-trend + low confidence ({confidence})")
                    return "HOLD", details

                if signal == "SELL" and ema_fast > ema_slow and roc_3 > 0.5 and confidence < 8:
                    details["reason"] = f"BLOCKED: Low-conf SELL against bullish trend (EMA9>EMA21, ROC={roc_3:+.2f}%)"
                    logger.warning(f"AI {epic}: SELL BLOCKED - counter-trend + low confidence ({confidence})")
                    return "HOLD", details

                # HARD FILTER 2: RSI extreme overextension (widened thresholds)
                if signal == "BUY" and rsi > 72:
                    details["reason"] = f"BLOCKED: BUY with RSI={rsi:.0f} (overextended, >72)"
                    logger.warning(f"AI {epic}: BUY BLOCKED - RSI overextended ({rsi:.0f})")
                    return "HOLD", details

                if signal == "SELL" and rsi < 28:
                    details["reason"] = f"BLOCKED: SELL with RSI={rsi:.0f} (oversold, <28)"
                    logger.warning(f"AI {epic}: SELL BLOCKED - RSI oversold ({rsi:.0f})")
                    return "HOLD", details

            # HARD FILTER 3: Recent loss penalty — only block after 3+ consecutive losses
            if signal in ("BUY", "SELL") and self.trade_executor:
                try:
                    recent = self.trade_executor.get_trade_feedback(epic=epic, limit=3)
                    recent_losses = sum(1 for t in recent if (t.get("profit_loss") or 0) < 0)
                    if recent_losses >= 3 and confidence < 8:
                        details["reason"] = f"BLOCKED: {recent_losses} consecutive losses on {epic}, need conf>=8 (got {confidence})"
                        logger.warning(f"AI {epic}: {signal} BLOCKED - {recent_losses} recent losses, confidence {confidence} < 8")
                        return "HOLD", details
                except Exception:
                    pass

            if signal in ("BUY", "SELL"):
                details["reasons"] = [f"AI: {reasoning[:100]}"]
                logger.info(f"AI {epic}: {signal} (confidence: {confidence}/10) - {reasoning[:80]}")
            else:
                details["reason"] = f"AI HOLD: {reasoning[:100]}"
                logger.info(f"AI {epic}: HOLD - {reasoning[:80]}")

            return signal, details

        except json.JSONDecodeError as e:
            logger.error(f"AI response not valid JSON: {e} | Response: {result_text[:200]}")
            return "HOLD", {"reason": f"AI parse error: {e}"}
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            return "HOLD", {"reason": f"AI API error: {e}"}
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return "HOLD", {"reason": f"AI error: {e}"}

    def _get_zone(self, range_position):
        if range_position <= 20:
            return "BUY_ZONE"
        elif range_position >= 80:
            return "SELL_ZONE"
        return "NEUTRAL"

    def _build_prompt(self, epic, df, sentiment_data=None, rule_signal=None, regime_data=None):
        """Build the analysis prompt with all market data."""
        latest = df.iloc[-1]

        # Recent candles summary (last 12 = 12 hours on 1H)
        recent = df.tail(12)
        candles_text = ""
        green_count = 0
        red_count = 0
        for i, (idx, row) in enumerate(recent.iterrows()):
            direction = "GREEN" if row["close"] > row["open"] else "RED"
            if direction == "GREEN":
                green_count += 1
            else:
                red_count += 1
            change_pct = (row["close"] - row["open"]) / row["open"] * 100
            candles_text += (
                f"  {idx}: {direction} O={row['open']:.4f} H={row['high']:.4f} "
                f"L={row['low']:.4f} C={row['close']:.4f} ({change_pct:+.2f}%)\n"
            )

        # Calculate sustained trend (consecutive candles in same direction)
        last_candles = df.tail(8)
        consecutive_green = 0
        consecutive_red = 0
        for _, row in last_candles.iloc[::-1].iterrows():
            if row["close"] > row["open"]:
                if consecutive_red > 0:
                    break
                consecutive_green += 1
            else:
                if consecutive_green > 0:
                    break
                consecutive_red += 1

        # 24h price change
        if len(df) >= 24:
            price_24h_ago = df.iloc[-24]["close"]
            change_24h = (latest["close"] - price_24h_ago) / price_24h_ago * 100
        else:
            change_24h = 0

        # Technical indicators
        range_pos = latest.get("range_position", 50)
        rsi = latest.get("rsi", 50)
        bb_pct = latest.get("bb_pct", 0.5)
        range_pct = latest.get("range_pct", 0)
        atr_pct = latest.get("atr_pct", 0)
        ema_fast = latest.get("ema_9", latest.get("close"))
        ema_slow = latest.get("ema_21", latest.get("close"))
        ema_trend = "BULLISH" if ema_fast > ema_slow else "BEARISH"
        vwap = latest.get("vwap", latest.get("close"))
        volume_spike = "YES" if latest.get("volume_spike", False) else "NO"
        roc_3 = latest.get("roc_3", 0)
        roc_6 = latest.get("roc_6", 0)
        bullish_engulfing = "YES" if latest.get("bullish_engulfing", False) else "NO"
        bearish_engulfing = "YES" if latest.get("bearish_engulfing", False) else "NO"
        macd_hist = latest.get("macd_histogram", 0)
        volume_ratio = latest.get("volume_ratio", 1.0)

        # Trend pattern summary
        if consecutive_green >= 3:
            trend_pattern = f"BULLISH STREAK: {consecutive_green} consecutive green candles"
        elif consecutive_red >= 3:
            trend_pattern = f"BEARISH STREAK: {consecutive_red} consecutive red candles"
        elif green_count >= 8:
            trend_pattern = f"STRONGLY BULLISH: {green_count}/{len(recent)} green candles in last 12h"
        elif red_count >= 8:
            trend_pattern = f"STRONGLY BEARISH: {red_count}/{len(recent)} red candles in last 12h"
        else:
            trend_pattern = f"MIXED: {green_count} green / {red_count} red in last 12h"

        # Portfolio context — FIRST section so AI always knows current state
        portfolio_text = ""
        if self.position_sync:
            try:
                portfolio_text = self.position_sync.format_for_prompt() + "\n\n"
            except Exception as e:
                logger.debug(f"Portfolio format error: {e}")

        prompt = f"""{portfolio_text}Analyze {epic} for a potential trade:

PRICE: {latest['close']:.4f}
24h CHANGE: {change_24h:+.2f}%
24h RANGE: {latest.get('range_low', 0):.4f} - {latest.get('range_high', 0):.4f}
RANGE SIZE: {range_pct:.1f}%
POSITION IN RANGE: {range_pos:.0f}% (0%=bottom, 100%=top)

PATTERN: {trend_pattern}
{f'Consecutive streak: {consecutive_green} green candles — momentum building' if consecutive_green >= 3 else f'Consecutive streak: {consecutive_red} red candles — selling pressure' if consecutive_red >= 3 else ''}

TECHNICAL INDICATORS:
- RSI(14): {rsi:.1f}
- EMA 9/21: {ema_fast:.4f} / {ema_slow:.4f} (trend: {ema_trend})
- Bollinger Band %B: {bb_pct:.2f} (0=lower band, 1=upper band)
- VWAP: {vwap:.4f} (price {'above' if latest['close'] > vwap else 'below'} VWAP)
- ATR: {atr_pct:.2f}% (volatility)
- MACD Histogram: {macd_hist:.4f} ({'positive' if macd_hist > 0 else 'negative'})
- Volume spike: {volume_spike} (ratio: {volume_ratio:.1f}x)
- Momentum (3 candles): {roc_3:+.2f}%
- Momentum (6 candles): {roc_6:+.2f}%
- Bullish engulfing: {bullish_engulfing}
- Bearish engulfing: {bearish_engulfing}

SUPPORT: {latest.get('support', 'N/A')}
RESISTANCE: {latest.get('resistance', 'N/A')}

RECENT CANDLES (last 12 hours, newest last):
{candles_text}"""

        # Add regime data
        if regime_data:
            regime = regime_data.get("regime", "UNKNOWN")
            adx = regime_data.get("adx", 0)
            prompt += f"""
MARKET REGIME: {regime} (ADX: {adx:.1f})
- ADX > 25 = trending, < 20 = ranging, 20-25 = neutral
- Current regime implications: """
            if regime == "RANGING":
                prompt += "Mean-reversion strategies optimal. Trade with confidence."
            elif regime == "TRENDING_UP":
                prompt += "Favor BUY signals. SELL signals need extra confirmation."
            elif regime == "TRENDING_DOWN":
                prompt += "Favor SELL signals. BUY signals need extra confirmation."
            else:
                prompt += "Unclear direction. Only trade with strong technical confirmation."
            prompt += "\n"
        else:
            prompt += "\nMARKET REGIME: Not available\n"

        # Add higher-timeframe context
        htf = regime_data.get("htf_context") if regime_data else None
        if htf:
            prompt += f"""
HIGHER TIMEFRAME CONTEXT (CRITICAL - trade WITH these trends):
- 4H Trend: {htf.get('h4_trend', 'N/A')} (RSI: {htf.get('h4_rsi', 'N/A')}, EMA: {'bullish' if htf.get('h4_ema_bullish') else 'bearish'})
- Daily Trend: {htf.get('daily_trend', 'N/A')} (RSI: {htf.get('daily_rsi', 'N/A')})
- Alignment: {htf.get('trend_alignment', 'N/A')}
- Daily Support: {htf.get('daily_support', 'N/A')}
- Daily Resistance: {htf.get('daily_resistance', 'N/A')}
"""
            alignment = htf.get("trend_alignment", "")
            if alignment == "ALIGNED_UP":
                prompt += "→ Both higher TFs bullish. FAVOR BUY. SHORT needs conf >= 9.\n"
            elif alignment == "ALIGNED_DOWN":
                prompt += "→ Both higher TFs bearish. FAVOR SELL. BUY needs conf >= 9.\n"
            elif alignment == "CONFLICTING":
                prompt += "→ Higher TFs conflict. Be cautious. Only trade with strong 1H confirmation.\n"
        else:
            prompt += "\nHIGHER TIMEFRAME CONTEXT: Not available\n"

        # Add chart analysis (Fibonacci, S/R zones, patterns)
        try:
            chart = ChartAnalysis.get_full_analysis(df)
            chart_text = ChartAnalysis.format_for_prompt(chart)
            if chart_text:
                prompt += f"\n{chart_text}\n"
        except Exception as e:
            logger.debug(f"Chart analysis failed for {epic}: {e}")

        # Add multi-TF alignment if available
        alignment_data = regime_data.get("alignment") if regime_data else None
        if alignment_data:
            from src.strategy.technical_analysis import MultiTFAnalysis
            prompt += f"\n{MultiTFAnalysis.format_for_prompt(alignment_data)}\n"

        # Add sentiment pipeline if available
        pipeline_data = regime_data.get("sentiment_pipeline") if regime_data else None
        if pipeline_data and pipeline_data.get("composite_score", 50) != 50:
            from src.strategy.sentiment_pipeline import SentimentPipeline
            prompt += f"\n{SentimentPipeline.format_for_prompt(pipeline_data)}\n"

        # Add time-of-day bias if available in details
        time_bias = None
        time_bias_return = 0
        # Extract from latest row if present (passed through details)
        if regime_data:
            time_bias = regime_data.get("time_bias")
            time_bias_return = regime_data.get("time_bias_return", 0)
        if time_bias:
            prompt += (
                f"\nTIME-OF-DAY BIAS: {time_bias} (avg return this hour: {time_bias_return:+.3f}%)\n"
                f"- Based on 7-day hourly return analysis. "
                f"{'Historically bullish hour - favor BUY.' if time_bias == 'BULLISH' else 'Historically bearish hour - favor SELL.' if time_bias == 'BEARISH' else 'No clear hourly pattern.'}\n"
            )

        # Add sentiment if available (legacy format from reddit_sentiment)
        has_sentiment = sentiment_data and (
            sentiment_data.get("total_posts", 0) > 0 or sentiment_data.get("fear_greed")
        )
        if has_sentiment:
            prompt += f"""
NEWS SENTIMENT (SUPPLEMENTARY - require 3+ technical confirmations):
- Sentiment score: {sentiment_data['score']}/100 ({sentiment_data['label']})
- Bullish weight: {sentiment_data['bullish_weight']}
- Bearish weight: {sentiment_data['bearish_weight']}"""

            fng = sentiment_data.get("fear_greed")
            if fng:
                prompt += f"\n- Fear & Greed Index: {fng['value']}/100 ({fng['label']})"

            cg = sentiment_data.get("coingecko")
            if cg:
                prompt += f"\n- CoinGecko community: {cg['up_pct']:.0f}% bullish / {cg['down_pct']:.0f}% bearish"

            if sentiment_data.get("total_posts", 0) > 0:
                prompt += f"\n- News posts analyzed: {sentiment_data['total_posts']}"
            if sentiment_data.get("top_bullish"):
                prompt += f"\n- Top bullish headline: {sentiment_data['top_bullish'][0][:80]}"
            if sentiment_data.get("top_bearish"):
                prompt += f"\n- Top bearish headline: {sentiment_data['top_bearish'][0][:80]}"
        else:
            prompt += "\nNEWS SENTIMENT: No data available"

        # Add breaking news and market context
        if self.news_monitor:
            try:
                market_ctx = self.news_monitor.get_market_context()
                if market_ctx:
                    prompt += f"\n{market_ctx}"

                breaking = self.news_monitor.get_breaking_news(epic)
                if breaking:
                    prompt += "\nBREAKING NEWS (hot in last hour):\n"
                    for item in breaking[:3]:
                        votes = item.get("votes", {})
                        vote_str = f"+{votes.get('positive', 0)}/-{votes.get('negative', 0)}"
                        prompt += f"  - {item['title'][:80]} ({vote_str})\n"
            except Exception as e:
                logger.debug(f"News context failed: {e}")

        # Add rule-based bot's signal for collaboration
        if rule_signal:
            rs_signal = rule_signal.get("signal", "HOLD")
            rs_score = rule_signal.get("score", 0)
            rs_reasons = rule_signal.get("reasons", [])
            prompt += f"""

RULE-BASED BOT SIGNAL:
- Signal: {rs_signal}
- Score: {rs_score}/9 (needs 4+ to trigger)
- Reasons: {', '.join(rs_reasons[:5]) if rs_reasons else 'None'}
- Note: This is the technical scoring system's conclusion. If it agrees with your analysis, you can be more confident. If it disagrees, explain why you see it differently."""

        # Enhanced AI feedback loop - learn from wins AND losses
        if self.trade_executor:
            try:
                feedback = self.trade_executor.get_trade_feedback(epic=epic, limit=10)
                if feedback:
                    wins = [t for t in feedback if (t.get("profit_loss") or 0) > 0]
                    losses = [t for t in feedback if (t.get("profit_loss") or 0) < 0]
                    total_pl = sum(t.get("profit_loss", 0) for t in feedback)

                    prompt += f"\n\n{'='*50}\nTRADE FEEDBACK FOR {epic} (CRITICAL - learn from this):\n"
                    prompt += f"Record: {len(wins)}W / {len(losses)}L | Net P&L: EUR {total_pl:+.2f}\n"

                    # Analyze losses - what went wrong?
                    if losses:
                        prompt += f"\n⚠ LOSSES TO LEARN FROM ({len(losses)} trades):\n"
                        for t in losses[:3]:
                            entry = t.get("entry_price", 0)
                            exit_p = t.get("exit_price", 0)
                            sl = t.get("stop_loss", 0)
                            tp = t.get("take_profit", 0)
                            pl = t.get("profit_loss", 0)
                            hit_sl = abs(exit_p - sl) < abs(exit_p - tp) if sl and tp and exit_p else False
                            prompt += (
                                f"  - {t['direction']} @ {entry:.4f} → exit {exit_p:.4f} | EUR {pl:+.2f}\n"
                                f"    SL={sl:.4f} TP={tp:.4f} | {'Hit SL' if hit_sl else 'Closed early'}\n"
                            )
                            # Parse signal_details for lessons
                            details_str = t.get("signal_details", "")
                            if details_str:
                                try:
                                    d = json.loads(details_str) if isinstance(details_str, str) else details_str
                                    rsi_at_entry = d.get("rsi", "?")
                                    regime_at_entry = d.get("regime", "?")
                                    prompt += f"    Entry RSI={rsi_at_entry}, Regime={regime_at_entry}\n"
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        prompt += "  → LESSON: What indicators could have warned? Use this to enter BETTER next time.\n"
                        prompt += "  → Do NOT avoid this coin — find the RIGHT setup instead.\n"

                    # Analyze wins - what worked?
                    if wins:
                        prompt += f"\n✓ WINNING PATTERNS ({len(wins)} trades):\n"
                        for t in wins[:3]:
                            entry = t.get("entry_price", 0)
                            exit_p = t.get("exit_price", 0)
                            pl = t.get("profit_loss", 0)
                            prompt += f"  - {t['direction']} @ {entry:.4f} → exit {exit_p:.4f} | EUR {pl:+.2f}\n"
                            details_str = t.get("signal_details", "")
                            if details_str:
                                try:
                                    d = json.loads(details_str) if isinstance(details_str, str) else details_str
                                    rsi_at_entry = d.get("rsi", "?")
                                    regime_at_entry = d.get("regime", "?")
                                    prompt += f"    Entry RSI={rsi_at_entry}, Regime={regime_at_entry}\n"
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        prompt += "  → These setups WORKED. Look for similar patterns now.\n"

                # Cross-bot learning: rule bot's best trades
                if os.path.exists(self.rule_db_path):
                    rule_winners = self.trade_executor.get_cross_bot_winners(self.rule_db_path, limit=5)
                    epic_rule_wins = [t for t in rule_winners if t["epic"] == epic]
                    if epic_rule_wins:
                        prompt += f"\n📊 RULE BOT'S BEST {epic} TRADES (learn from these):\n"
                        for t in epic_rule_wins[:3]:
                            entry = t.get("entry_price", 0)
                            exit_p = t.get("exit_price", 0)
                            pl = t.get("profit_loss", 0)
                            prompt += f"  - {t['direction']} @ {entry:.4f} → {exit_p:.4f} | EUR {pl:+.2f}\n"
                            details_str = t.get("signal_details", "")
                            if details_str:
                                try:
                                    d = json.loads(details_str) if isinstance(details_str, str) else details_str
                                    prompt += f"    Signal: score={d.get('signal_strength','?')}, zone={d.get('zone','?')}, RSI={d.get('rsi','?')}\n"
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        prompt += "  → The rule bot found profitable setups here. Consider similar entries.\n"

                # Overall AI performance summary
                all_feedback = self.trade_executor.get_trade_feedback(limit=30)
                if len(all_feedback) >= 5:
                    all_wins = sum(1 for t in all_feedback if (t.get("profit_loss") or 0) > 0)
                    all_losses = sum(1 for t in all_feedback if (t.get("profit_loss") or 0) < 0)
                    win_rate = all_wins / (all_wins + all_losses) * 100 if (all_wins + all_losses) > 0 else 0
                    long_count = sum(1 for t in all_feedback if t["direction"] == "BUY")
                    short_count = sum(1 for t in all_feedback if t["direction"] == "SELL")
                    prompt += f"\n📈 YOUR OVERALL STATS: {win_rate:.0f}% win rate ({all_wins}W/{all_losses}L)\n"
                    prompt += f"Direction bias: {long_count} longs / {short_count} shorts\n"
                    if short_count < long_count * 0.3:
                        prompt += "⚠ You barely take short positions! In bearish trends, you MUST short. Look for SELL setups more actively.\n"
                    if win_rate < 45:
                        prompt += "⚠ Win rate is below 45%. Study your winning trades — what did they have in common? Replicate THOSE setups.\n"

            except Exception as e:
                logger.debug(f"Trade feedback error: {e}")

        # Inject approved weekly strategy rules
        if self._active_strategies:
            prompt += "\n\nAPPROVED WEEKLY STRATEGY RULES (follow these):\n"
            for rule in self._active_strategies:
                prompt += f"- {rule}\n"

        # Inject user feedback/training rules
        user_feedback = self._load_user_feedback(limit=5)
        if user_feedback:
            prompt += "\n\nUSER GUIDANCE (the trader gave you these rules - FOLLOW THEM):\n"
            for fb in user_feedback:
                prompt += f"- {fb['feedback']}\n"

        prompt += "\n\nBased on ALL the above data, what is your recommendation? Return JSON only."
        return prompt

    def generate_report(self, epic, df, sentiment_data=None, rule_signal=None, regime_data=None):
        """Generate a detailed analysis report explaining the reasoning step by step."""
        if df is None or len(df) < 50:
            return "Ikke nok data til rapport."

        latest = df.iloc[-1]
        prompt = self._build_prompt(epic, df, sentiment_data, rule_signal=rule_signal, regime_data=regime_data)

        report_system = """You are an expert crypto trading analyst writing a detailed report in Danish.

Analyze the market data and write a structured report that explains your reasoning step by step.

Write the report in this exact format (use plain text, no markdown):

ANALYSE RAPPORT: {epic}
Dato: {current date/time}

1. PRIS & RANGE
- Beskriv hvor prisen er i forhold til 24-timers range
- Er den naer support eller resistance?

2. TEKNISKE INDIKATORER
- RSI: hvad siger den? Er den oversold/overbought?
- EMA 9/21: hvad er trenden?
- Bollinger Bands: hvor er prisen i forhold til baandene?
- VWAP: er prisen over eller under?
- MACD: hvad viser histogrammet?
- Volume: er der udsving?

3. MARKEDSREGIME
- Er markedet trending eller ranging?
- Hvad betyder det for strategien?

4. PRICE ACTION
- Beskriv de seneste candles
- Er der reversal-moenstre (engulfing, bounce)?
- Hvad er momentum-retningen?

5. SENTIMENT
- Hvad siger nyhederne?
- Er markedet bullish eller bearish?

6. REGEL-BOT SAMMENLIGNING
- Hvad siger den regelbaserede bot?
- Er I enige eller uenige? Hvorfor?

7. KONKLUSION
- Samlet vurdering
- Signal: BUY / SELL / HOLD
- Confidence: X/10
- Begrundelse i 2-3 saetninger

Keep it concise but informative. Max 400 words.

IMPORTANT: Return ONLY plain text. Do NOT wrap in JSON, code blocks, or any other format. Just write the report directly."""

        try:
            self._rate_limit()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                system=report_system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            # Strip code blocks if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3].strip()
            # If Claude returned JSON, extract the report field
            if text.startswith("{"):
                try:
                    data = json.loads(text)
                    text = data.get("report", text)
                except json.JSONDecodeError:
                    pass
            return text
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return f"Fejl ved rapport: {e}"

    # ── Feedback & Chat System ────────────────────────────────────

    def _init_feedback_table(self):
        """Create user_feedback table in the trades DB for storing user guidance."""
        try:
            db_dir = os.path.dirname(self._feedback_db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            conn = sqlite3.connect(self._feedback_db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    feedback TEXT NOT NULL,
                    active INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    session_date DATE NOT NULL
                )
            """)
            conn.commit()
            conn.close()
            logger.info("Feedback + conversation tables initialized")
        except Exception as e:
            logger.error(f"Failed to init feedback table: {e}")

    def _save_chat_message(self, role, message):
        """Save a chat message to SQLite conversation_history."""
        try:
            conn = sqlite3.connect(self._feedback_db_path)
            conn.execute(
                "INSERT INTO conversation_history (timestamp, role, message, session_date) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), role, message, datetime.now().strftime("%Y-%m-%d"))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Save chat message error: {e}")

    def _load_chat_history(self):
        """Load last 24h of chat history from SQLite, with token guard.

        Returns list of {"role": str, "content": str} for Haiku API.
        """
        try:
            conn = sqlite3.connect(self._feedback_db_path)
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
            cursor = conn.execute(
                "SELECT role, message FROM conversation_history "
                "WHERE timestamp > ? ORDER BY id ASC",
                (cutoff,)
            )
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return []

            # Token guard: rough estimate 1 token ~= 4 chars
            messages = [{"role": role, "content": msg} for role, msg in rows]
            total_chars = sum(len(m["content"]) for m in messages)
            estimated_tokens = total_chars // 4

            if estimated_tokens > self._max_token_estimate:
                # Keep only last N exchanges (1 exchange = 2 messages)
                max_messages = self._max_history * 2
                messages = messages[-max_messages:]
                logger.info(f"Chat history trimmed to {len(messages)} messages (token guard)")

            return messages
        except Exception as e:
            logger.error(f"Load chat history error: {e}")
            return []

    def _load_user_feedback(self, limit=10):
        """Load active user feedback for injection into trading prompts."""
        try:
            conn = sqlite3.connect(self._feedback_db_path)
            rows = conn.execute(
                "SELECT category, feedback FROM user_feedback WHERE active = 1 ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            conn.close()
            return [{"category": r[0], "feedback": r[1]} for r in rows]
        except Exception as e:
            logger.debug(f"Load feedback error: {e}")
            return []

    def _save_feedback(self, feedback_text, category="general"):
        """Save user feedback to the database."""
        try:
            conn = sqlite3.connect(self._feedback_db_path)
            conn.execute(
                "INSERT INTO user_feedback (timestamp, category, feedback) VALUES (?, ?, ?)",
                (datetime.now().isoformat(), category, feedback_text)
            )
            conn.commit()
            conn.close()
            logger.info(f"Saved user feedback: {feedback_text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Save feedback error: {e}")
            return False

    def chat(self, user_message, context_fn=None, image_data=None):
        """Interactive chat with the AI trader.

        Args:
            user_message: Free-text message from user
            context_fn: Callable that returns current bot state dict
            image_data: Optional base64-encoded image (from Telegram photo)

        Returns:
            Response string (Danish)
        """
        # Check for feedback/training commands
        lower_msg = user_message.strip().lower()
        if lower_msg.startswith("husk:") or lower_msg.startswith("remember:"):
            feedback = user_message.split(":", 1)[1].strip()
            if self._save_feedback(feedback, category="trading_rule"):
                return f"Noteret! Jeg husker: \"{feedback}\"\n\nDette vil pavirke mine fremtidige handelsbeslutninger."
            return "Fejl ved at gemme feedback."

        if lower_msg.startswith("glem:") or lower_msg.startswith("forget:"):
            keyword = user_message.split(":", 1)[1].strip()
            return self._forget_feedback(keyword)

        if lower_msg in ("feedback", "regler", "rules"):
            return self._list_feedback()

        # Build context
        context_text = ""
        if context_fn:
            try:
                ctx = context_fn()
                context_text = self._format_chat_context(ctx)
            except Exception as e:
                logger.error(f"Context fn error: {e}")

        # Load user feedback for personality
        feedback_items = self._load_user_feedback()
        feedback_text = ""
        if feedback_items:
            feedback_text = "\n\nUSER GUIDANCE (follow these rules):\n"
            for fb in feedback_items:
                feedback_text += f"- [{fb['category']}] {fb['feedback']}\n"

        # Inject live portfolio into chat system prompt
        portfolio_text = ""
        if self.position_sync:
            try:
                portfolio_text = "\n" + self.position_sync.format_for_prompt() + "\n"
                logger.info(f"[Chat] Portfolio injected: {len(portfolio_text)} chars, {self.position_sync.get_portfolio()['open_count']} positions")
            except Exception as e:
                logger.error(f"[Chat] Portfolio inject failed: {e}")

        chat_system = f"""Du er en erfaren krypto-CFD-trader der styrer en automatiseret handelsbot.
Du taler dansk. Du er direkte, ærlig og forklarer dine beslutninger klart.
{portfolio_text}
DIN ROLLE:
- Forklar dine handelsbeslutninger og analyse
- Accepter feedback fra brugeren og lær af det
- Vær ærlig om fejl og tabende handler
- Del din markedsopfattelse og strategi
- Hjælp brugeren med at forstå teknisk analyse

Brugeren kan give dig feedback med "husk: ..." for at gemme regler du skal følge.
Brugeren kan skrive "regler" for at se aktive feedback-regler.

VIGTIGE REGLER:
- Svar ALTID på dansk
- Hold svar under 600 ord
- Vær konkret, undgå vage svar
- Hvis du ikke ved noget, sig det
- Referer til konkrete trades og tal når muligt
- Hvis brugeren sender et billede/chart, analyser det grundigt (trends, patterns, S/R, indikatorer)
{feedback_text}"""

        # Load persistent conversation history from SQLite (last 24h)
        messages = self._load_chat_history()

        # Build user message content (text or multimodal with image)
        text_part = ""
        if context_text:
            text_part += f"AKTUEL BOT STATUS:\n{context_text}\n\n"
        text_part += f"BRUGER: {user_message}"

        if image_data:
            # Multimodal message with image
            user_content = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": text_part},
            ]
        else:
            user_content = text_part

        messages.append({"role": "user", "content": user_content})

        try:
            self._rate_limit()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                system=chat_system,
                messages=messages,
            )

            reply = response.content[0].text.strip()

            # Persist both messages to SQLite
            self._save_chat_message("user", user_message)
            self._save_chat_message("assistant", reply)

            return reply

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return f"Fejl i chat: {e}"

    def _format_chat_context(self, ctx):
        """Format bot state dict into readable text for chat."""
        lines = []
        if ctx.get("balance"):
            lines.append(f"Balance: EUR {ctx['balance']:.2f}")
        if ctx.get("available"):
            lines.append(f"Tilgængelig: EUR {ctx['available']:.2f}")
        if ctx.get("daily_pl") is not None:
            lines.append(f"Daglig P/L: EUR {ctx['daily_pl']:+.2f}")

        positions = ctx.get("positions", [])
        if positions:
            lines.append(f"\nÅbne positioner ({len(positions)}):")
            for p in positions:
                emoji = "🟢" if p["direction"] == "BUY" else "🔴"
                profit = p.get('profit') or 0
                lines.append(f"  {emoji} {p['epic']} {p['direction']} P/L: EUR {profit:+.2f} (hold: {p.get('hold_hours', '?')}t)")
        else:
            lines.append("Ingen åbne positioner")

        regimes = ctx.get("regimes", {})
        if regimes:
            lines.append("\nMarkedsregimer:")
            for epic, data in regimes.items():
                adx = data.get('adx') or 0
                lines.append(f"  {epic}: {data['regime']} (ADX: {adx:.0f})")

        recent = ctx.get("recent_trades", [])
        if recent:
            lines.append(f"\nSeneste handler:")
            for t in recent[:5]:
                pl = t.get("profit_loss") or 0
                emoji = "✅" if pl >= 0 else "❌"
                lines.append(f"  {emoji} {t['epic']} {t['direction']} P/L: EUR {pl:+.2f}")

        stats = ctx.get("stats", {})
        if stats:
            lines.append(f"\nStatistik: {stats.get('total_trades', 0)} trades, win rate: {stats.get('win_rate', 0)}%, total P/L: EUR {stats.get('total_pl', 0):+.2f}")

        return "\n".join(lines)

    def _forget_feedback(self, keyword):
        """Deactivate feedback matching keyword."""
        try:
            conn = sqlite3.connect(self._feedback_db_path)
            rows = conn.execute(
                "SELECT id, feedback FROM user_feedback WHERE active = 1 AND feedback LIKE ?",
                (f"%{keyword}%",)
            ).fetchall()
            if not rows:
                conn.close()
                return f"Ingen aktive regler matcher '{keyword}'."
            for row in rows:
                conn.execute("UPDATE user_feedback SET active = 0 WHERE id = ?", (row[0],))
            conn.commit()
            conn.close()
            return f"Glemt {len(rows)} regel(er) der matchede '{keyword}'."
        except Exception as e:
            return f"Fejl: {e}"

    def _list_feedback(self):
        """List all active feedback rules."""
        items = self._load_user_feedback(limit=20)
        if not items:
            return "Ingen aktive regler. Brug 'husk: ...' for at tilføje."
        msg = "📋 Aktive regler:\n\n"
        for i, fb in enumerate(items, 1):
            msg += f"{i}. [{fb['category']}] {fb['feedback']}\n"
        msg += "\nBrug 'glem: <søgeord>' for at fjerne en regel."
        return msg
