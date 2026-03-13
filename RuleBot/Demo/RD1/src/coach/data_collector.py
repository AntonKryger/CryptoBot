"""
Read-only access to all bot SQLite databases.
Parses JSON columns and returns pandas DataFrames for analysis.
"""

import json
import logging
import os
import sqlite3

import pandas as pd

logger = logging.getLogger(__name__)


def discover_bots(bot_data_dir):
    """Discover all bot databases in the data directory.

    Args:
        bot_data_dir: Path to directory containing bot subdirectories (e.g., /app/bot_data)

    Returns:
        dict of bot_id -> db_path (e.g., {"rl1": "/app/bot_data/rl1/trades.db"})
    """
    bots = {}
    if not os.path.isdir(bot_data_dir):
        logger.warning(f"[Coach] Bot data dir not found: {bot_data_dir}")
        return bots

    for entry in os.listdir(bot_data_dir):
        bot_dir = os.path.join(bot_data_dir, entry)
        if not os.path.isdir(bot_dir):
            continue
        db_path = os.path.join(bot_dir, "trades.db")
        if os.path.isfile(db_path):
            bots[entry] = db_path
            logger.info(f"[Coach] Discovered bot: {entry} -> {db_path}")

    if not bots:
        logger.warning(f"[Coach] No bot databases found in {bot_data_dir}")
    return bots


def _open_readonly(db_path):
    """Open SQLite database in read-only mode."""
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _safe_json_parse(val):
    """Parse JSON string, return empty dict on failure."""
    if not val or pd.isna(val):
        return {}
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return {}


def load_trades(bot_id, db_path, days=None):
    """Load trades from a bot's database as a DataFrame.

    Args:
        bot_id: Bot identifier (e.g., "rl1")
        db_path: Path to the bot's trades.db
        days: If set, only load trades from the last N days

    Returns:
        DataFrame with parsed JSON columns expanded
    """
    try:
        conn = _open_readonly(db_path)
        query = "SELECT * FROM trades"
        if days:
            query += f" WHERE timestamp >= datetime('now', '-{int(days)} days')"
        df = pd.read_sql_query(query, conn)
        conn.close()
    except Exception as e:
        logger.error(f"[Coach] Failed to load trades for {bot_id}: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    df["bot"] = bot_id

    # Convert numeric columns
    for col in ["profit_loss", "entry_price", "exit_price", "stop_loss", "take_profit", "size"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse JSON columns into dicts
    json_cols = ["signal_details", "risk_snapshot", "account_snapshot", "gates_snapshot", "post_analysis"]
    for col in json_cols:
        if col in df.columns:
            df[f"{col}_parsed"] = df[col].apply(_safe_json_parse)

    # Extract commonly needed fields from signal_details
    if "signal_details_parsed" in df.columns:
        df["confidence"] = df["signal_details_parsed"].apply(lambda d: d.get("ai_confidence") or d.get("confidence") or d.get("signal_strength", 0))
        df["regime"] = df["signal_details_parsed"].apply(lambda d: d.get("regime", "UNKNOWN"))
        df["rsi"] = df["signal_details_parsed"].apply(lambda d: d.get("rsi", None))
        df["adx"] = df["signal_details_parsed"].apply(lambda d: d.get("adx", None))
        df["range_position"] = df["signal_details_parsed"].apply(lambda d: d.get("range_position", None))

    # Parse timestamps
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True, errors="coerce")
    if "exit_timestamp" in df.columns:
        df["exit_timestamp"] = pd.to_datetime(df["exit_timestamp"], format="ISO8601", utc=True, errors="coerce")

    # Calculate hold duration for closed trades
    if "timestamp" in df.columns and "exit_timestamp" in df.columns:
        mask = df["exit_timestamp"].notna()
        df.loc[mask, "hold_hours"] = (df.loc[mask, "exit_timestamp"] - df.loc[mask, "timestamp"]).dt.total_seconds() / 3600

    # Extract exit_reason if available
    if "post_analysis_parsed" in df.columns:
        df["exit_reason"] = df["post_analysis_parsed"].apply(lambda d: d.get("exit_reason", "unknown"))

    logger.info(f"[Coach] Loaded {len(df)} trades for {bot_id}" + (f" (last {days}d)" if days else ""))
    return df


def load_balance_history(bot_id, db_path):
    """Load balance snapshots from a bot's database.

    Returns:
        DataFrame with timestamp and balance columns
    """
    try:
        conn = _open_readonly(db_path)
        df = pd.read_sql_query("SELECT * FROM balance_snapshots", conn)
        conn.close()
    except Exception as e:
        logger.error(f"[Coach] Failed to load balances for {bot_id}: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    df["bot"] = bot_id
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True, errors="coerce")
    if "balance" in df.columns:
        df["balance"] = pd.to_numeric(df["balance"], errors="coerce")

    return df


def get_bot_type(bot_id, config=None):
    """Infer bot type from its ID.

    Returns: "rule" | "ai" | "scalper" | "unknown"
    """
    bid = bot_id.lower()
    if bid.startswith("r"):
        return "rule"
    elif bid.startswith("a"):
        return "ai"
    elif bid.startswith("s"):
        return "scalper"
    return "unknown"
