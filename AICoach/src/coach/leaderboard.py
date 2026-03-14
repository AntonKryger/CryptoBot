"""
Leaderboard — ranks all bot variants by composite score.
Exports to data/leaderboard.json for dashboard consumption.
"""

import json
import logging
import math
import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

from .analyzer import full_bot_analysis, _closed_trades
from .strategy_profiles import (
    evaluate_against_expectations,
    MIN_TRADES_FOR_EVALUATION,
)

logger = logging.getLogger(__name__)


def _load_trades_db(db_path):
    """Load trades from a SQLite database."""
    if not os.path.exists(db_path):
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM trades", conn)
        conn.close()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        return df
    except Exception as e:
        logger.warning(f"Failed to load {db_path}: {e}")
        return pd.DataFrame()


def calculate_sharpe_ratio(df, risk_free_rate=0.0):
    """Calculate annualized Sharpe ratio from trade P/L series."""
    closed = _closed_trades(df)
    if closed.empty or len(closed) < 5:
        return None

    if "timestamp" not in closed.columns or closed["timestamp"].isna().all():
        return None

    closed = closed.sort_values("timestamp")

    # Group by date for daily returns
    closed["date"] = closed["timestamp"].dt.date
    daily_pl = closed.groupby("date")["profit_loss"].sum()

    if len(daily_pl) < 5:
        return None

    mean_return = daily_pl.mean()
    std_return = daily_pl.std()

    if std_return == 0 or math.isnan(std_return):
        return None

    daily_sharpe = (mean_return - risk_free_rate) / std_return
    annualized = daily_sharpe * math.sqrt(252)

    return round(annualized, 3)


def calculate_profit_factor(df):
    """Calculate profit factor: sum(wins) / abs(sum(losses))."""
    closed = _closed_trades(df)
    if closed.empty:
        return None

    wins = closed[closed["profit_loss"] > 0]["profit_loss"].sum()
    losses = abs(closed[closed["profit_loss"] <= 0]["profit_loss"].sum())

    if losses == 0:
        return float("inf") if wins > 0 else None

    return round(wins / losses, 3)


def calculate_composite_score(metrics):
    """
    Composite bot score:
    0.30 × Sharpe + 0.25 × profit_factor + 0.20 × win_rate
    + 0.15 × (1 - max_drawdown) + 0.10 × trade_volume_bonus
    """
    sharpe = metrics.get("sharpe_ratio")
    pf = metrics.get("profit_factor")
    wr = metrics.get("win_rate", 0)
    dd = metrics.get("max_drawdown_pct", 0)
    trades = metrics.get("total_trades", 0)

    # Normalize each component to 0-1 scale
    # Sharpe: -2 to +3 → 0 to 1
    sharpe_norm = max(0, min(1, (sharpe + 2) / 5)) if sharpe is not None else 0.3

    # Profit factor: 0 to 3 → 0 to 1
    if pf is None:
        pf_norm = 0.3
    elif pf == float("inf"):
        pf_norm = 1.0
    else:
        pf_norm = max(0, min(1, pf / 3))

    # Win rate: 0-100% → 0-1
    wr_norm = wr / 100

    # Drawdown: 0-50% → 1-0 (lower is better)
    dd_norm = max(0, min(1, 1 - abs(dd) / 50))

    # Trade volume bonus: log scale, 10-500 trades → 0-1
    if trades <= 0:
        vol_norm = 0
    else:
        vol_norm = max(0, min(1, math.log10(trades) / math.log10(500)))

    score = (
        0.30 * sharpe_norm
        + 0.25 * pf_norm
        + 0.20 * wr_norm
        + 0.15 * dd_norm
        + 0.10 * vol_norm
    )

    return round(score, 4)


def build_leaderboard(bot_data_dirs, variants_config=None):
    """
    Build complete leaderboard from all bot data directories.

    Args:
        bot_data_dirs: dict of bot_id -> path to data/ directory
        variants_config: dict from variants.yaml (optional, for profile-adjusted scoring)

    Returns:
        dict with leaderboard data
    """
    variants_cfg = variants_config or {}
    entries = []

    for bot_id, data_dir in sorted(bot_data_dirs.items()):
        db_path = os.path.join(data_dir, "trades.db")
        df = _load_trades_db(db_path)

        if df.empty:
            entries.append({
                "bot_id": bot_id,
                "status": "no_data",
                "total_trades": 0,
            })
            continue

        closed = _closed_trades(df)
        if closed.empty:
            entries.append({
                "bot_id": bot_id,
                "status": "no_closed_trades",
                "total_trades": 0,
            })
            continue

        total_trades = len(closed)
        wins = (closed["profit_loss"] > 0).sum()
        win_rate = round(wins / total_trades * 100, 1) if total_trades > 0 else 0
        total_pl = round(closed["profit_loss"].sum(), 2)
        avg_pl = round(closed["profit_loss"].mean(), 2)

        # Calculate drawdown
        cumulative = closed.sort_values(
            "timestamp" if "timestamp" in closed.columns else "id"
        )["profit_loss"].cumsum()
        running_max = cumulative.cummax()
        max_dd = round(float((cumulative - running_max).min()), 2)

        # Advanced metrics
        sharpe = calculate_sharpe_ratio(df)
        pf = calculate_profit_factor(df)

        # Days active
        if "timestamp" in closed.columns and closed["timestamp"].notna().any():
            first = closed["timestamp"].min()
            last = closed["timestamp"].max()
            days_active = max(1, (last - first).days)
            trades_per_day = round(total_trades / days_active, 1)
        else:
            days_active = None
            trades_per_day = None

        metrics = {
            "sharpe_ratio": sharpe,
            "profit_factor": pf if pf != float("inf") else 99.0,
            "win_rate": win_rate,
            "max_drawdown_pct": max_dd,
            "total_trades": total_trades,
            "trades_per_day": trades_per_day,
        }

        composite = calculate_composite_score(metrics)

        # Profile-adjusted evaluation
        vcfg = variants_cfg.get(bot_id, {})
        bot_type = vcfg.get("type", _infer_bot_type(bot_id))
        profile = vcfg.get("profile", "moderate")
        evaluation = evaluate_against_expectations(bot_type, profile, metrics)

        # Determine readiness
        if total_trades >= MIN_TRADES_FOR_EVALUATION["reliable"]:
            confidence = "high"
        elif total_trades >= MIN_TRADES_FOR_EVALUATION["meaningful"]:
            confidence = "medium"
        elif total_trades >= MIN_TRADES_FOR_EVALUATION["preliminary"]:
            confidence = "low"
        else:
            confidence = "insufficient"

        entry = {
            "bot_id": bot_id,
            "bot_type": bot_type,
            "profile": profile,
            "batch": vcfg.get("batch", "unknown"),
            "status": "active",
            "total_trades": total_trades,
            "win_rate": win_rate,
            "total_pl": total_pl,
            "avg_pl": avg_pl,
            "sharpe_ratio": sharpe,
            "profit_factor": pf if pf != float("inf") else None,
            "max_drawdown": max_dd,
            "trades_per_day": trades_per_day,
            "days_active": days_active,
            "composite_score": composite,
            "profile_score": evaluation.get("score"),
            "profile_verdict": evaluation.get("verdict"),
            "profile_details": evaluation.get("details", []),
            "confidence": confidence,
        }
        entries.append(entry)

    # Sort by composite score (descending)
    entries.sort(key=lambda e: e.get("composite_score", 0), reverse=True)

    # Add rank
    for i, entry in enumerate(entries):
        entry["rank"] = i + 1

    # Flag underperformers
    for entry in entries:
        if (
            entry.get("total_trades", 0) >= MIN_TRADES_FOR_EVALUATION["meaningful"]
            and entry.get("sharpe_ratio") is not None
            and entry["sharpe_ratio"] < 0
        ):
            entry["flag"] = "underperformer"
        elif entry.get("profile_verdict") == "critical":
            entry["flag"] = "critical"
        else:
            entry["flag"] = None

    # Per-type rankings
    by_type = {}
    for entry in entries:
        bt = entry.get("bot_type", "unknown")
        by_type.setdefault(bt, []).append(entry["bot_id"])

    leaderboard = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_variants": len(entries),
        "entries": entries,
        "by_type": by_type,
    }

    return leaderboard


def export_leaderboard(leaderboard, output_path):
    """Write leaderboard to JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(leaderboard, f, indent=2, default=str)
    logger.info(f"Leaderboard exported to {output_path}")


def format_leaderboard_telegram(leaderboard, top_n=10):
    """Format leaderboard for Telegram message."""
    entries = leaderboard.get("entries", [])
    if not entries:
        return "📊 Leaderboard: Ingen data endnu."

    lines = ["📊 *Bot Leaderboard*", ""]

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for entry in entries[:top_n]:
        rank = entry.get("rank", "?")
        medal = medals.get(rank, f"#{rank}")
        bot_id = entry["bot_id"]
        score = entry.get("composite_score", 0)
        wr = entry.get("win_rate", 0)
        pl = entry.get("total_pl", 0)
        trades = entry.get("total_trades", 0)
        flag = entry.get("flag")

        flag_emoji = ""
        if flag == "underperformer":
            flag_emoji = " ⚠️"
        elif flag == "critical":
            flag_emoji = " 🔴"

        pl_sign = "+" if pl >= 0 else ""
        lines.append(
            f"{medal} *{bot_id}* — Score: {score:.2f}{flag_emoji}\n"
            f"   WR: {wr}% | P/L: {pl_sign}{pl:.0f} EUR | {trades} trades"
        )

    lines.append(f"\n_Genereret: {leaderboard.get('generated_at', '?')}_")
    return "\n".join(lines)


def _infer_bot_type(bot_id):
    """Infer bot type from ID prefix."""
    prefix = bot_id[:2].upper()
    type_map = {"RL": "rule", "RD": "rule", "SD": "scalper", "AD": "ai", "AC": "coach"}
    return type_map.get(prefix, "unknown")
