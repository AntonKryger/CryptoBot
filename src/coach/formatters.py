"""
Telegram HTML formatting for coach reports and recommendations.
"""


def format_report_summary(report_data):
    """Format a full analysis report for Telegram.

    Args:
        report_data: dict with bot_results, cross_bot, trigger
    """
    lines = ["📊 <b>AI Coach Rapport</b>"]
    lines.append(f"Trigger: {report_data.get('trigger', 'manual')}")
    lines.append("")

    bot_results = report_data.get("bot_results", {})
    for bot_id, result in bot_results.items():
        if not result:
            continue

        status = result.get("status", "UNKNOWN")
        status_emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🚨"}.get(status, "❓")

        lines.append(f"{status_emoji} <b>{bot_id.upper()}</b> — {status}")
        lines.append(f"  {result.get('top_finding', 'Ingen data')}")

        recs = result.get("recommendations", [])
        if recs:
            lines.append(f"  📋 {len(recs)} anbefalinger:")
            for rec in recs[:3]:  # Show max 3 in summary
                priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec.get("priority"), "⚪")
                lines.append(f"    {priority_emoji} {rec.get('description', '?')}")
        lines.append("")

    lines.append("Brug /coach_recs for alle anbefalinger")
    return "\n".join(lines)


def format_recommendations(recommendations):
    """Format a list of recommendations for Telegram.

    Args:
        recommendations: list of recommendation dicts from coach_db
    """
    if not recommendations:
        return "Ingen ventende anbefalinger."

    lines = ["📋 <b>Ventende Anbefalinger</b>", ""]

    for rec in recommendations:
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rec.get("priority"), "⚪")
        lines.append(f"{priority_emoji} <b>#{rec['id']}</b> [{rec.get('bot_id', '?').upper()}] ({rec.get('type', '?')})")
        lines.append(f"  {rec.get('description', '?')}")

        if rec.get("config_key"):
            lines.append(f"  Config: <code>{rec['config_key']}</code>")
            lines.append(f"  Nu: {rec.get('current_value', '?')} → Anbefalet: {rec.get('recommended_value', '?')}")

        if rec.get("evidence"):
            lines.append(f"  Evidens: {rec['evidence']}")

        if rec.get("expected_impact"):
            lines.append(f"  Forventet: {rec['expected_impact']}")

        lines.append(f"  → /coach_approve {rec['id']} eller /coach_reject {rec['id']}")
        lines.append("")

    return "\n".join(lines)


def format_bot_report(bot_id, stats, llm_result=None):
    """Format detailed report for a single bot.

    Args:
        bot_id: Bot identifier
        stats: dict from analyzer.full_bot_analysis()
        llm_result: optional dict from LLM analysis
    """
    lines = [f"🤖 <b>Rapport: {bot_id.upper()}</b>", ""]

    # Drawdown summary
    dd = stats.get("drawdown", {})
    if dd:
        lines.append("<b>Oversigt:</b>")
        lines.append(f"  Trades: {dd.get('total_trades', 0)}")
        lines.append(f"  Total P/L: €{dd.get('total_pl', 0):.2f}")
        lines.append(f"  Max drawdown: €{dd.get('max_drawdown', 0):.2f}")
        lines.append(f"  Max tabsrække: {dd.get('max_loss_streak', 0)}")
        lines.append("")

    # Direction performance
    by_dir = stats.get("by_direction", {})
    if by_dir:
        lines.append("<b>Retning:</b>")
        for direction, s in by_dir.items():
            lines.append(f"  {direction}: {s['trades']} trades, {s['win_rate']}% win, €{s['total_pl']:.2f}")
        lines.append("")

    # Top coins
    by_coin = stats.get("by_coin", {})
    if by_coin:
        lines.append("<b>Coins:</b>")
        sorted_coins = sorted(by_coin.items(), key=lambda x: x[1].get("total_pl", 0), reverse=True)
        for coin, s in sorted_coins:
            emoji = "📈" if s.get("total_pl", 0) > 0 else "📉"
            lines.append(f"  {emoji} {coin}: {s['trades']}t, {s['win_rate']}% win, €{s['total_pl']:.2f}")
        lines.append("")

    # R:R
    rr = stats.get("risk_reward", {})
    if rr and rr.get("trades_analyzed", 0) > 0:
        lines.append("<b>Risk/Reward:</b>")
        lines.append(f"  Planned R:R: {rr.get('avg_planned_rr', '?')}")
        lines.append(f"  Actual R:R: {rr.get('avg_actual_rr', '?')}")
        lines.append(f"  Avg winner: €{rr.get('avg_winner', 0):.2f}")
        lines.append(f"  Avg loser: €{rr.get('avg_loser', 0):.2f}")
        lines.append("")

    # LLM assessment
    if llm_result:
        status = llm_result.get("status", "UNKNOWN")
        status_emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🚨"}.get(status, "❓")
        lines.append(f"<b>AI Vurdering:</b> {status_emoji} {status}")
        lines.append(f"  {llm_result.get('top_finding', '')}")

    return "\n".join(lines)


def format_status(bots, latest_report, pending_count):
    """Format coach status overview.

    Args:
        bots: dict of discovered bot_id -> db_path
        latest_report: latest report dict or None
        pending_count: number of pending recommendations
    """
    lines = ["🏋️ <b>Coach Status</b>", ""]

    lines.append(f"<b>Bots:</b> {', '.join(sorted(bots.keys())) if bots else 'Ingen fundet'}")
    lines.append(f"<b>Ventende anbefalinger:</b> {pending_count}")

    if latest_report:
        lines.append(f"<b>Seneste rapport:</b> {latest_report.get('created_at', '?')}")
        lines.append(f"  Trigger: {latest_report.get('trigger', '?')}")
        lines.append(f"  Model: {latest_report.get('model_used', '?')}")
        lines.append(f"  Tokens: {latest_report.get('token_count', '?')}")
    else:
        lines.append("<b>Seneste rapport:</b> Ingen endnu")

    lines.append("")
    lines.append("Kommandoer:")
    lines.append("  /coach_analyze — Kør analyse nu")
    lines.append("  /coach_recs — Vis anbefalinger")
    lines.append("  /coach_bot {id} — Detaljer for bot")
    lines.append("  /coach_approve {id} — Godkend anbefaling")
    lines.append("  /coach_reject {id} — Afvis anbefaling")

    return "\n".join(lines)
