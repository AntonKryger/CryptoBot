"""Dashboard routes - HTML pages and JSON API endpoints."""

import logging
import os
import time

import requests as http_requests
from flask import Blueprint, render_template, jsonify, request, current_app

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
    return render_template("compare.html", **ctx)


@bp.route("/leaderboard")
def leaderboard():
    ctx = _common_context()
    return render_template("leaderboard.html", **ctx)


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


@bp.route("/api/compare")
def api_compare():
    period = request.args.get("period", "all")
    return jsonify(current_app.stats.get_period_comparison(period))


@bp.route("/api/leaderboard")
def api_leaderboard():
    return jsonify(current_app.stats.get_leaderboard_data())


# ── Price proxy for SaaS platform charts ─────────────────────

DEMO_URL = "https://demo-api-capital.backend-capital.com"
ALLOWED_EPICS = {"BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "LTCUSD"}
ALLOWED_RESOLUTIONS = {"MINUTE_15", "HOUR", "HOUR_4", "DAY"}

_capital_session = {"cst": None, "token": None, "expires": 0}


def _get_capital_session():
    """Get or refresh Capital.com session for price data."""
    if _capital_session["cst"] and time.time() < _capital_session["expires"]:
        return _capital_session["cst"], _capital_session["token"]

    email = os.environ.get("CAPITAL_EMAIL", "")
    password = os.environ.get("CAPITAL_PASSWORD", "")
    api_key = os.environ.get("CAPITAL_API_KEY", "")

    if not all([email, password, api_key]):
        raise ValueError("Capital.com credentials not configured")

    resp = http_requests.post(f"{DEMO_URL}/api/v1/session", json={
        "identifier": email,
        "password": password,
        "encryptedPassword": False,
    }, headers={"X-CAP-API-KEY": api_key}, timeout=10)
    resp.raise_for_status()

    _capital_session["cst"] = resp.headers.get("CST")
    _capital_session["token"] = resp.headers.get("X-SECURITY-TOKEN")
    _capital_session["expires"] = time.time() + 8 * 60
    return _capital_session["cst"], _capital_session["token"]


@bp.route("/api/prices")
def api_prices():
    """Proxy Capital.com price data for SaaS platform charts."""
    epic = request.args.get("epic", "BTCUSD")
    resolution = request.args.get("resolution", "HOUR")
    max_count = min(int(request.args.get("max", 200)), 500)

    if epic not in ALLOWED_EPICS:
        return jsonify({"error": f"Invalid epic: {epic}"}), 400
    if resolution not in ALLOWED_RESOLUTIONS:
        return jsonify({"error": f"Invalid resolution: {resolution}"}), 400

    try:
        api_key = os.environ.get("CAPITAL_API_KEY", "")
        cst, token = _get_capital_session()

        resp = http_requests.get(
            f"{DEMO_URL}/api/v1/prices/{epic}",
            params={"resolution": resolution, "max": max_count},
            headers={
                "X-CAP-API-KEY": api_key,
                "CST": cst,
                "X-SECURITY-TOKEN": token,
            },
            timeout=10,
        )

        if resp.status_code == 401:
            _capital_session["expires"] = 0
            cst, token = _get_capital_session()
            resp = http_requests.get(
                f"{DEMO_URL}/api/v1/prices/{epic}",
                params={"resolution": resolution, "max": max_count},
                headers={
                    "X-CAP-API-KEY": api_key,
                    "CST": cst,
                    "X-SECURITY-TOKEN": token,
                },
                timeout=10,
            )

        resp.raise_for_status()
        data = resp.json()

        candles = []
        for p in data.get("prices", []):
            time_str = p.get("snapshotTime", "")
            try:
                # Capital.com returns ISO format: "2026-03-13T14:00:00"
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
                ts = int(dt.timestamp())
            except (ValueError, TypeError):
                continue

            o = p.get("openPrice", {})
            h = p.get("highPrice", {})
            l = p.get("lowPrice", {})
            c = p.get("closePrice", {})

            def _mid(prices):
                """Calculate mid price from bid/ask."""
                bid = prices.get("bid", 0)
                ask = prices.get("ask", 0)
                if bid and ask:
                    return round((bid + ask) / 2, 6)
                return ask or bid or 0

            candles.append({
                "time": ts,
                "open": _mid(o),
                "high": _mid(h),
                "low": _mid(l),
                "close": _mid(c),
                "volume": p.get("lastTradedVolume", 0),
            })

        response = jsonify({"candles": candles})
        response.headers["Cache-Control"] = "public, max-age=30"
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    except Exception as e:
        logging.error(f"[Dashboard] Price proxy error: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/api/validate_pl")
def api_validate_pl():
    """Validate P/L data integrity: show DB totals, trade counts, and duplicate detection."""
    import sqlite3
    results = {}
    for bot_name, db_path in current_app.config["DB_PATHS"].items():
        try:
            db = sqlite3.connect(db_path)
            # Total P/L from closed trades
            row = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(profit_loss), 0) FROM trades WHERE status = 'CLOSED' AND profit_loss IS NOT NULL"
            ).fetchone()
            closed_count, total_pl = row

            # Open trades
            open_count = db.execute(
                "SELECT COUNT(*) FROM trades WHERE status = 'OPEN'"
            ).fetchone()[0]

            # Trades with NULL P/L
            null_pl = db.execute(
                "SELECT COUNT(*) FROM trades WHERE status = 'CLOSED' AND profit_loss IS NULL"
            ).fetchone()[0]

            # Duplicate deal_ids
            dupes = db.execute(
                "SELECT deal_id, COUNT(*) as cnt FROM trades WHERE deal_id IS NOT NULL "
                "GROUP BY deal_id HAVING cnt > 1"
            ).fetchall()

            # Source breakdown
            source_rows = db.execute(
                "SELECT COALESCE(source, 'unknown'), COUNT(*), COALESCE(SUM(profit_loss), 0) "
                "FROM trades WHERE status = 'CLOSED' GROUP BY COALESCE(source, 'unknown')"
            ).fetchall()
            sources = {r[0]: {"count": r[1], "pl": round(r[2], 2)} for r in source_rows}

            db.close()
            results[bot_name] = {
                "closed_trades": closed_count,
                "open_trades": open_count,
                "total_pl_eur": round(total_pl, 2),
                "null_pl_trades": null_pl,
                "duplicate_deal_ids": len(dupes),
                "duplicates": [{"deal_id": d[0], "count": d[1]} for d in dupes[:10]],
                "sources": sources,
            }
        except Exception as e:
            results[bot_name] = {"error": str(e)}

    return jsonify(results)
