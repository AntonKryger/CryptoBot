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

    # Default DB paths
    db_paths = {
        "rule": os.environ.get("RULE_DB", "data/trades.db"),
        "ai": os.environ.get("AI_DB", "data_ai/trades.db"),
        "demo": os.environ.get("DEMO_DB", "data_demo/trades.db"),
    }

    # Filter to only existing DBs
    db_paths = {k: v for k, v in db_paths.items() if os.path.exists(v)}

    if not db_paths:
        # Fallback: try common paths
        for path in ["data/trades.db", "data_ai/trades.db"]:
            if os.path.exists(path):
                name = "rule" if "data_ai" not in path else "ai"
                db_paths[name] = path

    app.stats = StatsEngine(db_paths)
    app.config["DB_PATHS"] = db_paths

    from src.dashboard.routes import bp
    app.register_blueprint(bp)

    return app
