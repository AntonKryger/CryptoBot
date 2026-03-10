"""Dashboard routes - HTML pages and JSON API endpoints."""

from flask import Blueprint, render_template, jsonify, request, current_app

bp = Blueprint("dashboard", __name__)


# ── HTML Pages ────────────────────────────────────────────────

@bp.route("/")
def overview():
    stats = current_app.stats
    data = stats.get_overview()
    return render_template("overview.html", data=data, bots=list(current_app.config["DB_PATHS"].keys()))


@bp.route("/trades")
def trades():
    return render_template("trades.html", bots=list(current_app.config["DB_PATHS"].keys()))


@bp.route("/stats")
def stats_page():
    stats = current_app.stats
    overview = stats.get_overview()
    detailed = stats.get_detailed_stats()
    return render_template("stats.html", overview=overview, stats=detailed,
                           bots=list(current_app.config["DB_PATHS"].keys()))


@bp.route("/instruments")
def instruments():
    return render_template("instruments.html", bots=list(current_app.config["DB_PATHS"].keys()))


@bp.route("/calendar")
def calendar():
    return render_template("calendar.html", bots=list(current_app.config["DB_PATHS"].keys()))


@bp.route("/compare")
def compare():
    stats = current_app.stats
    comparison = stats.get_comparison()
    return render_template("compare.html", comparison=comparison,
                           bots=list(current_app.config["DB_PATHS"].keys()))


# ── JSON API ──────────────────────────────────────────────────

@bp.route("/api/overview")
def api_overview():
    bot = request.args.get("bot")
    return jsonify(current_app.stats.get_overview(bot))


@bp.route("/api/daily-pnl")
def api_daily_pnl():
    bot = request.args.get("bot")
    days = int(request.args.get("days", 30))
    return jsonify(current_app.stats.get_daily_pnl(bot, days))


@bp.route("/api/instruments")
def api_instruments():
    bot = request.args.get("bot")
    return jsonify(current_app.stats.get_instrument_stats(bot))


@bp.route("/api/calendar")
def api_calendar():
    bot = request.args.get("bot")
    return jsonify(current_app.stats.get_calendar_data(bot))


@bp.route("/api/trades")
def api_trades():
    bot = request.args.get("bot")
    limit = int(request.args.get("limit", 100))
    epic = request.args.get("epic")
    direction = request.args.get("direction")
    status = request.args.get("status")
    return jsonify(current_app.stats.get_trades(bot, limit, epic, direction, status))


@bp.route("/api/balance")
def api_balance():
    bot = request.args.get("bot")
    hours = int(request.args.get("hours", 168))
    return jsonify(current_app.stats.get_balance_history(bot, hours))


@bp.route("/api/comparison")
def api_comparison():
    return jsonify(current_app.stats.get_comparison())
