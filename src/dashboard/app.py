"""Flask app factory for the trading dashboard."""

import os
from flask import Flask
from src.dashboard.stats_engine import StatsEngine


def create_app(config=None):
    """Create and configure the Flask app."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    # Auto-discover bot DBs from BOT_DATA_DIR
    bot_data_dir = os.environ.get("BOT_DATA_DIR", "")
    db_paths = {}

    if bot_data_dir and os.path.isdir(bot_data_dir):
        for bot_id in sorted(os.listdir(bot_data_dir)):
            db_file = os.path.join(bot_data_dir, bot_id, "trades.db")
            if os.path.exists(db_file):
                db_paths[bot_id] = db_file

    # Fallback: legacy hardcoded paths (backward compat)
    if not db_paths:
        for name, path in [("rule", "data/trades.db"), ("ai", "data_ai/trades.db"), ("demo", "data_demo/trades.db")]:
            if os.path.exists(path):
                db_paths[name] = path

    app.stats = StatsEngine(db_paths)
    app.config["DB_PATHS"] = db_paths

    from src.dashboard.routes import bp
    app.register_blueprint(bp)

    return app
