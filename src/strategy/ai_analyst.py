"""
AI Analyst for CryptoBot - Uses Claude API to analyze market data
and make intelligent trading decisions.
"""

import json
import logging
import time
from datetime import datetime

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert crypto trading analyst specializing in CFD trading on 15-minute timeframes.
You analyze technical indicators, price action, and news sentiment to make trading decisions.

Your strategy is mean-reversion / range-trading:
- BUY when price is near the bottom of its range with signs of reversal
- SELL (short) when price is near the top of its range with signs of rejection
- HOLD when there is no clear edge

You are risk-aware and only recommend trades with high conviction. You prefer to HOLD rather than take marginal trades.

IMPORTANT RULES:
- Only recommend BUY or SELL when multiple indicators align
- A low RSI alone is NOT enough to buy - you need confirmation (bounce, volume, sentiment)
- A high RSI alone is NOT enough to sell - you need confirmation (rejection, volume, sentiment)
- If the range is too small (<3%), HOLD - there is no edge in a flat market
- Consider the news sentiment carefully - bad news can override technical signals
- Be specific about what you see and why you recommend the action

Respond ONLY with valid JSON in this exact format:
{"signal": "BUY|SELL|HOLD", "confidence": 1-10, "reasoning": "your analysis here"}"""


class AIAnalyst:
    """Uses Claude API to analyze market data and generate trading signals."""

    def __init__(self, config):
        ai_cfg = config.get("ai", {})
        self.api_key = ai_cfg.get("anthropic_api_key", "")
        self.model = ai_cfg.get("model", "claude-haiku-4-5-20251001")
        self.max_tokens = ai_cfg.get("max_tokens", 300)
        self.min_confidence = ai_cfg.get("min_confidence", 6)

        if not self.api_key:
            raise ValueError("Anthropic API key not configured (ai.anthropic_api_key)")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self._last_request = 0
        self._request_delay = 1.0  # seconds between API calls

        logger.info(f"AI Analyst initialized (model: {self.model}, min_confidence: {self.min_confidence})")

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request = time.time()

    def analyze(self, epic, df, sentiment_data=None):
        """Analyze market data using Claude and return a trading signal.

        Args:
            epic: Trading pair (e.g. "BTCUSD")
            df: DataFrame with calculated indicators
            sentiment_data: Optional dict from CryptoPanic/Reddit sentiment

        Returns:
            (signal, details) tuple - same format as SignalEngine.get_signal()
        """
        if df is None or len(df) < 50:
            return "HOLD", {"reason": "Insufficient data for AI analysis"}

        latest = df.iloc[-1]
        prompt = self._build_prompt(epic, df, sentiment_data)

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
            }

            # Only trigger trade if confidence meets minimum
            if signal in ("BUY", "SELL") and confidence < self.min_confidence:
                details["reason"] = f"AI {signal} but low confidence ({confidence}/{self.min_confidence})"
                details["ai_original_signal"] = signal
                logger.info(f"AI {epic}: {signal} rejected (confidence {confidence} < {self.min_confidence})")
                return "HOLD", details

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

    def _build_prompt(self, epic, df, sentiment_data=None):
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
- Volume spike: {volume_spike}
- Momentum (3 candles): {roc_3:+.2f}%
- Momentum (6 candles): {roc_6:+.2f}%
- Bullish engulfing: {bullish_engulfing}
- Bearish engulfing: {bearish_engulfing}

SUPPORT: {latest.get('support', 'N/A')}
RESISTANCE: {latest.get('resistance', 'N/A')}

RECENT CANDLES (15min each, newest last):
{candles_text}"""

        # Add sentiment if available
        has_sentiment = sentiment_data and (
            sentiment_data.get("total_posts", 0) > 0 or sentiment_data.get("fear_greed")
        )
        if has_sentiment:
            prompt += f"""
NEWS SENTIMENT:
- Sentiment score: {sentiment_data['score']}/100 ({sentiment_data['label']})
- Bullish weight: {sentiment_data['bullish_weight']}
- Bearish weight: {sentiment_data['bearish_weight']}"""

            fng = sentiment_data.get("fear_greed")
            if fng:
                prompt += f"\n- Fear & Greed Index: {fng['value']}/100 ({fng['label']})"

            if sentiment_data.get("total_posts", 0) > 0:
                prompt += f"\n- News posts analyzed: {sentiment_data['total_posts']}"
            if sentiment_data.get("top_bullish"):
                prompt += f"\n- Top bullish headline: {sentiment_data['top_bullish'][0][:80]}"
            if sentiment_data.get("top_bearish"):
                prompt += f"\n- Top bearish headline: {sentiment_data['top_bearish'][0][:80]}"
        else:
            prompt += "\nNEWS SENTIMENT: No data available"

        prompt += "\n\nBased on ALL the above data, what is your recommendation? Return JSON only."
        return prompt

    def generate_report(self, epic, df, sentiment_data=None):
        """Generate a detailed analysis report explaining the reasoning step by step."""
        if df is None or len(df) < 50:
            return "Ikke nok data til rapport."

        latest = df.iloc[-1]
        prompt = self._build_prompt(epic, df, sentiment_data)

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
- Volume: er der udsving?

3. PRICE ACTION
- Beskriv de seneste candles
- Er der reversal-moenstre (engulfing, bounce)?
- Hvad er momentum-retningen?

4. SENTIMENT
- Hvad siger nyhederne?
- Er markedet bullish eller bearish?

5. KONKLUSION
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
