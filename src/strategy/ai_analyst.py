"""
AI Analyst for CryptoBot - Uses Claude API to analyze market data
and make intelligent trading decisions.
"""

import json
import logging
import os
import time
from datetime import datetime

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert crypto CFD trader on 1-hour timeframes managing a EUR 93,000 account.

YOUR PERFORMANCE PROBLEM: Your average loss (-161 EUR) is DOUBLE your average win (+81 EUR). Even at 50% win rate you LOSE money. You also have a massive long bias (87% BUY). You repeat the same losing trades on the same coins. THIS MUST CHANGE.

CORE PRINCIPLE: Trade WITH the trend. Only enter when the expected reward justifies the risk.

STRATEGY:
- TRENDING market (EMA 9 > EMA 21 or vice versa): Trade in the trend direction ONLY.
- RANGING market (ADX < 20): Mean-reversion at range extremes only.
- CONFLICTING signals or NEUTRAL regime: HOLD. Sitting out IS a valid strategy.

STRICT ENTRY RULES (violating ANY = HOLD):
1. TREND ALIGNMENT: EMA 9 > EMA 21 for BUY, EMA 9 < EMA 21 for SELL. NO counter-trend trades.
2. MOMENTUM CONFIRMATION: ROC (3-candle) must align with trade direction. Negative ROC = no BUY. Positive ROC = no SELL.
3. CONFIRMATION CANDLE: Require bullish engulfing/bounce for BUY, bearish engulfing/rejection for SELL. No entry on indicators alone.
4. RSI FILTER: Do NOT buy if RSI > 65 (already extended). Do NOT sell if RSI < 35.
5. VOLUME: Prefer entries with volume spike or above-average volume ratio.
6. RECENT LOSS FILTER: If you lost on this exact coin in the last 3 trades, require confidence >= 8 to re-enter.

POSITION SIZING BY CONFIDENCE:
- Confidence 6-7: SMALL position (minimum sizing). These are speculative.
- Confidence 8: MEDIUM position. Strong setup with multiple confirmations.
- Confidence 9-10: FULL position. Exceptional setup, trend + momentum + confirmation all aligned.
- NEVER give confidence 8+ unless ALL 5 entry rules above are met.

DIRECTION BALANCE — CRITICAL:
- You are 87% long. In bearish trends (EMA 9 < EMA 21), you MUST recommend SELL or HOLD. NEVER BUY.
- Falling prices with negative momentum = SELL opportunity, not a "dip to buy."
- If both ROC-3 and ROC-6 are negative, a BUY signal requires exceptional justification (confidence 9+).

LOSS PREVENTION:
- If your trade feedback shows net negative P/L on a coin, raise the bar. Require MORE confirmations.
- Your biggest losses come from buying into downtrends. Check EMA trend FIRST before anything else.
- A trade with 3% SL and 4.5% TP only works if your entry timing is precise. Wait for the confirmation candle.

R:R DISCIPLINE:
- Minimum R:R is 1.5:1. Your TP must be at least 1.5x your SL distance.
- If the nearest resistance/support doesn't allow 1.5:1 R:R, HOLD.

WHEN TO HOLD:
- No clear trend (ADX 15-25, flat EMAs)
- Conflicting indicators (e.g., bullish EMA but bearish momentum)
- Price in the middle of range (30-70% position) with no confirmation candle
- You've already lost on this coin recently and setup isn't exceptional

Sentiment is SUPPLEMENTARY only. Never trade on sentiment alone.

Respond ONLY with valid JSON:
{"signal": "BUY|SELL|HOLD", "confidence": 1-10, "reasoning": "your analysis here"}"""


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
        self.rule_db_path = ai_cfg.get("rule_db_path", "data/trades.db")  # Rule bot DB for cross-learning

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
            }

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

            # Only trigger trade if confidence meets minimum
            if signal in ("BUY", "SELL") and confidence < self.min_confidence:
                details["reason"] = f"AI {signal} but low confidence ({confidence}/{self.min_confidence})"
                details["ai_original_signal"] = signal
                logger.info(f"AI {epic}: {signal} rejected (confidence {confidence} < {self.min_confidence})")
                return "HOLD", details

            # HARD FILTER 1: Counter-trend blocker
            if signal in ("BUY", "SELL"):
                ema_fast = latest.get("ema_9", latest.get("close"))
                ema_slow = latest.get("ema_21", latest.get("close"))
                roc_3 = latest.get("roc_3", 0)
                rsi = latest.get("rsi", 50)

                if signal == "BUY" and ema_fast < ema_slow and roc_3 < 0:
                    details["reason"] = f"BLOCKED: BUY against bearish trend (EMA9<EMA21, ROC={roc_3:+.2f}%)"
                    logger.warning(f"AI {epic}: BUY BLOCKED - counter-trend (EMA bearish + negative momentum)")
                    return "HOLD", details

                if signal == "SELL" and ema_fast > ema_slow and roc_3 > 0:
                    details["reason"] = f"BLOCKED: SELL against bullish trend (EMA9>EMA21, ROC={roc_3:+.2f}%)"
                    logger.warning(f"AI {epic}: SELL BLOCKED - counter-trend (EMA bullish + positive momentum)")
                    return "HOLD", details

                # HARD FILTER 2: RSI overextension
                if signal == "BUY" and rsi > 65:
                    details["reason"] = f"BLOCKED: BUY with RSI={rsi:.0f} (overextended, >65)"
                    logger.warning(f"AI {epic}: BUY BLOCKED - RSI overextended ({rsi:.0f})")
                    return "HOLD", details

                if signal == "SELL" and rsi < 35:
                    details["reason"] = f"BLOCKED: SELL with RSI={rsi:.0f} (oversold, <35)"
                    logger.warning(f"AI {epic}: SELL BLOCKED - RSI oversold ({rsi:.0f})")
                    return "HOLD", details

            # HARD FILTER 3: Recent loss penalty — require higher confidence after losses
            if signal in ("BUY", "SELL") and self.trade_executor:
                try:
                    recent = self.trade_executor.get_trade_feedback(epic=epic, limit=3)
                    recent_losses = sum(1 for t in recent if (t.get("profit_loss") or 0) < 0)
                    if recent_losses >= 2 and confidence < 8:
                        details["reason"] = f"BLOCKED: {recent_losses} recent losses on {epic}, need conf>=8 (got {confidence})"
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

        # Recent candles summary (last 6 = 1.5 hours)
        recent = df.tail(6)
        candles_text = ""
        for i, (idx, row) in enumerate(recent.iterrows()):
            direction = "GREEN" if row["close"] > row["open"] else "RED"
            change_pct = (row["close"] - row["open"]) / row["open"] * 100
            candles_text += (
                f"  {idx}: {direction} O={row['open']:.4f} H={row['high']:.4f} "
                f"L={row['low']:.4f} C={row['close']:.4f} ({change_pct:+.2f}%)\n"
            )

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

        prompt = f"""Analyze {epic} for a potential trade:

PRICE: {latest['close']:.4f}
24h RANGE: {latest.get('range_low', 0):.4f} - {latest.get('range_high', 0):.4f}
RANGE SIZE: {range_pct:.1f}%
POSITION IN RANGE: {range_pos:.0f}% (0%=bottom, 100%=top)

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

RECENT CANDLES (15min each, newest last):
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

        # Add sentiment if available
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
