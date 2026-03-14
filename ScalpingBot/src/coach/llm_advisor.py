"""
LLM-powered trading advisor. Sends structured statistics to Claude
and receives specific, actionable recommendations.
"""

import json
import logging
import re
import time

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Du er en kvantitativ trading-coach for CFD crypto-bots. Du analyserer statistik og giver specifikke, datadrevne anbefalinger til FORBEDRING.

GRUNDPRINCIPPER:
- Der findes IKKE dårlige coins — kun dårlige trades. Anbefal ALDRIG at banne en coin. Fokusér i stedet på HVORNÅR og HVORDAN der handles.
- Anbefal ALDRIG at deaktivere en hel retning (BUY eller SELL). Hvis SELL-trades taber, find ud af HVORFOR og foreslå bedre entry-betingelser, timing eller SL/TP-niveauer.
- Dit job er at gøre botten BEDRE — ikke at begrænse den. Færre trades er kun svaret hvis evidensen er overvældende.
- Fokusér på: timing (hvornår), entry-kvalitet (hvilke betingelser), risk/reward (SL/TP-placering), og position sizing.

Regler:
1. Giv KUN specifikke config-ændringer med nøgle + værdi. Ingen vage råd.
2. Flagu altid når sample size er for lille (<20 trades) — vær forsigtig med konklusioner.
3. Hver bot er en ANDEN type med sin egen strategi. Optimer for botens stil, ikke din egen mening.
4. Fokusér på hvad data viser, ikke hvad du tror markedet vil gøre.
5. Prioritér forbedring af dårlige trades over eliminering af dem. Spørg: "Hvad skulle have været anderledes for at denne trade virkede?"
6. Overvej altid om en anbefaling har nok evidens. "Måske" er et gyldigt svar.

Bot-typer:
- "rule": Regelbaseret bot med tekniske indikatorer (RSI, EMA, BB, ADX). Config-nøgler under trading: og risk:
- "ai": AI-bot der bruger Claude til signaler + regelbaserede hard gates. Config under ai: og trading:
- "scalper": Range-scalper der handler i definerede pris-zoner. Config under scalper: og risk:

Tilladt coin-liste: BTCUSD, ETHUSD, SOLUSD, AVAXUSD, LINKUSD, LTCUSD — disse er FASTE. Foreslå IKKE at fjerne nogen.

Svar KUN med valid JSON i dette format:
{
  "status": "HEALTHY|WARNING|CRITICAL",
  "top_finding": "Vigtigste observation i én sætning",
  "recommendations": [
    {
      "type": "config_change|strategy_change|timing_change",
      "priority": "high|medium|low",
      "description": "Specifik anbefaling på dansk",
      "config_key": "risk.stop_loss_pct",
      "current_value": "4.0",
      "recommended_value": "6.0",
      "evidence": "Konkret data der støtter anbefalingen",
      "expected_impact": "Forventet effekt"
    }
  ]
}

Giv max 5 anbefalinger per bot. Sortér efter prioritet (high først)."""


class LLMAdvisor:
    """Send trading statistics to Claude and get recommendations."""

    def __init__(self, config):
        ai_cfg = config.get("coach", {}).get("ai", config.get("ai", {}))
        self.api_key = ai_cfg.get("anthropic_api_key", "")
        self.model = ai_cfg.get("model", "claude-sonnet-4-20250514")
        self.max_tokens = ai_cfg.get("max_tokens", 2000)

        if not self.api_key:
            raise ValueError("Anthropic API key not configured for coach")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self._last_request = 0
        self._request_delay = 2.0
        self._market_data = None  # Set via set_market_data()

    def _rate_limit(self):
        elapsed = time.time() - self._last_request
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request = time.time()

    def set_market_data(self, market_data_provider):
        """Attach market data provider for context-aware analysis."""
        self._market_data = market_data_provider

    def analyze_bot(self, bot_id, bot_type, stats, trade_count):
        """Get LLM recommendations for a single bot.

        Args:
            bot_id: Bot identifier (e.g., "ad1")
            bot_type: "rule" | "ai" | "scalper"
            stats: dict from analyzer.full_bot_analysis()
            trade_count: total number of closed trades

        Returns:
            (response_dict, token_count) or (None, 0) on failure
        """
        prompt = self._build_prompt(bot_id, bot_type, stats, trade_count)

        try:
            self._rate_limit()
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()
            token_count = response.usage.input_tokens + response.usage.output_tokens

            # Strip markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[1] if "\n" in result_text else result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3].strip()

            # Extract JSON
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(result_text)

            logger.info(f"[Coach] LLM analysis for {bot_id}: status={result.get('status')}, "
                        f"{len(result.get('recommendations', []))} recommendations, {token_count} tokens")

            return result, token_count

        except json.JSONDecodeError as e:
            logger.error(f"[Coach] JSON parse error for {bot_id}: {e}")
            return None, 0
        except anthropic.APIError as e:
            logger.error(f"[Coach] Anthropic API error for {bot_id}: {e}")
            return None, 0
        except Exception as e:
            logger.error(f"[Coach] LLM analysis failed for {bot_id}: {e}")
            return None, 0

    def _build_prompt(self, bot_id, bot_type, stats, trade_count):
        """Build analysis prompt with all statistics and market context."""
        sections = [
            f"Analysér bot '{bot_id}' (type: {bot_type}, {trade_count} lukkede trades).",
            "",
        ]

        # Add live market context if available
        if self._market_data and self._market_data.enabled:
            try:
                market_ctx = self._market_data.format_market_context()
                if market_ctx:
                    sections.append(market_ctx)
                    sections.append("")

                # Add per-coin context for coins this bot trades
                coins_traded = list(stats.get("by_coin", {}).keys())
                for coin in coins_traded[:3]:  # Top 3 most traded coins
                    epic = coin if coin.endswith("USD") else f"{coin}USD"
                    coin_ctx = self._market_data.get_coin_context(epic)
                    if coin_ctx:
                        sections.append(coin_ctx)
            except Exception as e:
                logger.warning(f"[Coach] Market data failed for {bot_id}: {e}")

        # Win rate by regime
        if stats.get("by_regime"):
            sections.append("REGIME PERFORMANCE:")
            for regime, s in stats["by_regime"].items():
                sections.append(f"  {regime}: {s['trades']} trades, {s['win_rate']}% win, avg €{s['avg_pl']}, total €{s['total_pl']}")

        # Win rate by coin
        if stats.get("by_coin"):
            sections.append("\nCOIN PERFORMANCE:")
            for coin, s in stats["by_coin"].items():
                sections.append(f"  {coin}: {s['trades']} trades, {s['win_rate']}% win, avg €{s['avg_pl']}, total €{s['total_pl']}")

        # Win rate by hour
        if stats.get("by_hour"):
            sections.append("\nHOUR PERFORMANCE (CET):")
            for hour, s in sorted(stats["by_hour"].items(), key=lambda x: int(x[0])):
                sections.append(f"  {hour}:00: {s['trades']} trades, {s['win_rate']}% win, avg €{s['avg_pl']}")

        # Win rate by direction
        if stats.get("by_direction"):
            sections.append("\nDIRECTION PERFORMANCE:")
            for direction, s in stats["by_direction"].items():
                sections.append(f"  {direction}: {s['trades']} trades, {s['win_rate']}% win, total €{s['total_pl']}")

        # Exit reasons
        if stats.get("by_exit_reason"):
            sections.append("\nEXIT REASONS:")
            for reason, s in stats["by_exit_reason"].items():
                sections.append(f"  {reason}: {s['trades']} trades ({s.get('pct_of_trades', 0)}%), {s['win_rate']}% win, avg €{s['avg_pl']}")

        # Risk/reward
        if stats.get("risk_reward"):
            rr = stats["risk_reward"]
            sections.append("\nRISK/REWARD:")
            sections.append(f"  Planned R:R: {rr.get('avg_planned_rr')}")
            sections.append(f"  Actual R:R: {rr.get('avg_actual_rr')}")
            sections.append(f"  TP hit rate: {rr.get('tp_hit_rate')}%")
            sections.append(f"  SL hit rate: {rr.get('sl_hit_rate')}%")
            sections.append(f"  Avg winner: €{rr.get('avg_winner')}")
            sections.append(f"  Avg loser: €{rr.get('avg_loser')}")

        # Indicators
        if stats.get("indicators"):
            ind = stats["indicators"]
            if ind.get("rsi"):
                sections.append("\nRSI BUCKETS:")
                for bucket, s in ind["rsi"].items():
                    sections.append(f"  RSI {bucket}: {s['trades']} trades, {s['win_rate']}% win")
            if ind.get("adx"):
                sections.append("\nADX BUCKETS:")
                for bucket, s in ind["adx"].items():
                    sections.append(f"  ADX {bucket}: {s['trades']} trades, {s['win_rate']}% win")

        # Hold duration
        if stats.get("hold_duration"):
            sections.append("\nHOLD DURATION:")
            for bucket, s in stats["hold_duration"].items():
                if bucket.startswith("_"):
                    continue
                sections.append(f"  {bucket}: {s['trades']} trades, {s['win_rate']}% win, avg €{s['avg_pl']}")
            summary = stats["hold_duration"].get("_summary", {})
            if summary:
                sections.append(f"  Avg hold (winners): {summary.get('avg_hold_winners')}h")
                sections.append(f"  Avg hold (losers): {summary.get('avg_hold_losers')}h")

        # Drawdown
        if stats.get("drawdown"):
            dd = stats["drawdown"]
            sections.append("\nDRAWDOWN:")
            sections.append(f"  Max drawdown: €{dd.get('max_drawdown')}")
            sections.append(f"  Max loss streak: {dd.get('max_loss_streak')}")
            sections.append(f"  Avg loss streak: {dd.get('avg_loss_streak')}")

        # AI-specific
        if stats.get("confidence_vs_outcome"):
            sections.append("\nAI CONFIDENCE vs OUTCOME:")
            for bucket, s in stats["confidence_vs_outcome"].items():
                sections.append(f"  Confidence {bucket}: {s['trades']} trades, {s['win_rate']}% win, avg €{s['avg_pl']}")

        # Scalper-specific
        if stats.get("zone_analysis"):
            sections.append("\nSCALPER ZONE ANALYSIS:")
            for direction, zones in stats["zone_analysis"].items():
                for zone, s in zones.items():
                    sections.append(f"  {direction} {zone}: {s['trades']} trades, {s['win_rate']}% win")

        return "\n".join(sections)
