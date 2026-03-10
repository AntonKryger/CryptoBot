"""Dashboard routes - HTML pages and JSON API endpoints."""

from flask import Blueprint, render_template, jsonify, request, current_app

import os

bp = Blueprint(
    "dashboard", __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
    static_url_path="/static",
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
)

# Display names for bots
BOT_LABELS = {
    "rule": "Live Bot",
    "ai": "AI Bot",
    "demo": "Demo Bot",
}


def _common_context():
    """Context variables shared across all templates."""
    current_bot = request.args.get("bot", "")
    available = current_app.config["DB_PATHS"]
    # Only show labels for bots that exist
    labels = {k: BOT_LABELS.get(k, k.upper()) for k in available}
    return {
        "current_bot": current_bot,
        "bot_labels": labels,
        "bots": list(available.keys()),
    }


# ── HTML Pages ────────────────────────────────────────────────

@bp.route("/")
def overview():
    ctx = _common_context()
    bot = ctx["current_bot"] or None
    data = current_app.stats.get_overview(bot)
    return render_template("overview.html", data=data, **ctx)


@bp.route("/trades")
def trades():
    ctx = _common_context()
    return render_template("trades.html", **ctx)


@bp.route("/stats")
def stats_page():
    ctx = _common_context()
    bot = ctx["current_bot"] or None
    overview = current_app.stats.get_overview(bot)
    detailed = current_app.stats.get_detailed_stats(bot)
    return render_template("stats.html", overview=overview, stats=detailed, **ctx)


@bp.route("/instruments")
def instruments():
    ctx = _common_context()
    return render_template("instruments.html", **ctx)


@bp.route("/calendar")
def calendar():
    ctx = _common_context()
    return render_template("calendar.html", **ctx)


@bp.route("/compare")
def compare():
    ctx = _common_context()
    comparison = current_app.stats.get_comparison()
    return render_template("compare.html", comparison=comparison, **ctx)


# ── JSON API ──────────────────────────────────────────────────

@bp.route("/api/overview")
def api_overview():
    bot = request.args.get("bot") or None
    return jsonify(current_app.stats.get_overview(bot))


@bp.route("/api/daily-pnl")
def api_daily_pnl():
    bot = request.args.get("bot") or None
    days = int(request.args.get("days", 30))
    return jsonify(current_app.stats.get_daily_pnl(bot, days))


@bp.route("/api/instruments")
def api_instruments():
    bot = request.args.get("bot") or None
    return jsonify(current_app.stats.get_instrument_stats(bot))


@bp.route("/api/calendar")
def api_calendar():
    bot = request.args.get("bot") or None
    return jsonify(current_app.stats.get_calendar_data(bot))


@bp.route("/api/trades")
def api_trades():
    bot = request.args.get("bot") or None
    limit = int(request.args.get("limit", 100))
    epic = request.args.get("epic")
    direction = request.args.get("direction")
    status = request.args.get("status")
    return jsonify(current_app.stats.get_trades(bot, limit, epic, direction, status))


@bp.route("/api/balance")
def api_balance():
    bot = request.args.get("bot") or None
    hours = int(request.args.get("hours", 168))
    return jsonify(current_app.stats.get_balance_history(bot, hours))


@bp.route("/api/comparison")
def api_comparison():
    return jsonify(current_app.stats.get_comparison())
