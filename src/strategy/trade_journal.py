"""
Trade Journal - Structured pre-trade documentation.
Every trade must have a journal entry before execution.
"""

import logging

logger = logging.getLogger(__name__)


class TradeJournal:
    """Creates structured trade journal entries from AI analysis data."""

    def __init__(self, config):
        self.config = config

    def create_journal(self, epic, direction, entry_price, size, sl, tp, ai_details, regime_data):
        """Build a structured trade journal from existing analysis data.

        Returns:
            (journal_dict, is_valid, error_reason)
        """
        regime = regime_data.get("regime", "") if regime_data else ""
        adx = regime_data.get("adx", 0) if regime_data else 0

        # Map regime to market condition
        if "TRENDING" in regime:
            condition = "trending"
        elif regime == "RANGING" or adx < 20:
            condition = "ranging"
        else:
            condition = "volatile"

        reasoning = ai_details.get("ai_reasoning", "")
        confidence = ai_details.get("ai_confidence", 0)

        # Validate reasoning exists and is meaningful
        if not reasoning or len(reasoning.strip()) < 20:
            return None, False, "AI reasoning too short for journal"

        journal = {
            "asset": epic,
            "direction": direction,
            "entry_price": entry_price,
            "size": size,
            "why": reasoning[:500],
            "expected_target": tp,
            "market_condition": condition,
            "stop_loss": sl,
            "take_profit": tp,
            "confidence": confidence,
        }

        logger.info(
            f"[Journal] {epic} {direction}: {condition} | "
            f"SL={sl:.4f} TP={tp:.4f} | {reasoning[:60]}"
        )

        return journal, True, None

    @staticmethod
    def format_for_telegram(journal):
        """Format journal entry for Telegram notification."""
        emoji = "🟢" if journal["direction"] == "BUY" else "🔴"
        action = "LONG" if journal["direction"] == "BUY" else "SHORT"
        return (
            f"📓 <b>TRADE JOURNAL</b>\n"
            f"{emoji} {action}: {journal['asset']}\n"
            f"Entry: EUR {journal['entry_price']:.4f}\n"
            f"Size: {journal['size']}\n"
            f"SL: {journal['stop_loss']:.4f} | TP: {journal['take_profit']:.4f}\n"
            f"Marked: {journal['market_condition'].upper()}\n"
            f"Confidence: {journal['confidence']}/10\n\n"
            f"<b>HVORFOR:</b> {journal['why'][:300]}"
        )
