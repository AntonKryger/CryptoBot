"""
Pure Python/pandas statistical analysis for trading performance.
No LLM calls — just structured data for the advisor.
"""

import logging
import math

import pandas as pd
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Copenhagen")


def _safe_dict(d):
    """Replace NaN/inf with None for JSON serialization."""
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            out[k] = None
        elif isinstance(v, dict):
            out[k] = _safe_dict(v)
        else:
            out[k] = v
    return out


def _closed_trades(df):
    """Filter to closed trades with P/L data."""
    if df.empty:
        return pd.DataFrame()
    closed = df[df["status"] == "CLOSED"].copy()
    if closed.empty:
        return closed
    return closed[closed["profit_loss"].notna()]


def _win_stats(group):
    """Calculate win rate stats for a group of trades."""
    if group.empty:
        return {"trades": 0, "wins": 0, "win_rate": 0, "avg_pl": 0, "total_pl": 0}
    wins = (group["profit_loss"] > 0).sum()
    return _safe_dict({
        "trades": int(len(group)),
        "wins": int(wins),
        "win_rate": round(wins / len(group) * 100, 1) if len(group) > 0 else 0,
        "avg_pl": round(group["profit_loss"].mean(), 2),
        "total_pl": round(group["profit_loss"].sum(), 2),
    })


# ── Per-bot analyses ─────────────────────────────────────────────


def win_rate_by_regime(df):
    """Win rate broken down by market regime."""
    closed = _closed_trades(df)
    if closed.empty or "regime" not in closed.columns:
        return {}
    result = {}
    for regime, group in closed.groupby("regime"):
        result[regime] = _win_stats(group)
    return result


def win_rate_by_coin(df):
    """Win rate broken down by epic/coin."""
    closed = _closed_trades(df)
    if closed.empty:
        return {}
    result = {}
    for epic, group in closed.groupby("epic"):
        result[epic] = _win_stats(group)
    return result


def win_rate_by_hour(df):
    """Win rate broken down by entry hour (CET)."""
    closed = _closed_trades(df)
    if closed.empty or "timestamp" not in closed.columns:
        return {}
    closed = closed.copy()
    closed["hour_cet"] = closed["timestamp"].dt.tz_convert(CET).dt.hour
    result = {}
    for hour, group in closed.groupby("hour_cet"):
        result[int(hour)] = _win_stats(group)
    return result


def win_rate_by_direction(df):
    """Win rate broken down by BUY/SELL."""
    closed = _closed_trades(df)
    if closed.empty:
        return {}
    result = {}
    for direction, group in closed.groupby("direction"):
        result[direction] = _win_stats(group)
    return result


def win_rate_by_exit_reason(df):
    """Win rate broken down by exit reason."""
    closed = _closed_trades(df)
    if closed.empty or "exit_reason" not in closed.columns:
        return {}
    result = {}
    total = len(closed)
    for reason, group in closed.groupby("exit_reason"):
        stats = _win_stats(group)
        stats["pct_of_trades"] = round(len(group) / total * 100, 1) if total > 0 else 0
        result[reason] = stats
    return result


def risk_reward_analysis(df):
    """Analyze planned vs actual risk:reward ratios."""
    closed = _closed_trades(df)
    if closed.empty:
        return {}

    # Calculate planned R:R from entry/SL/TP
    has_sl_tp = closed[closed["stop_loss"].notna() & closed["take_profit"].notna() & closed["entry_price"].notna()].copy()
    if has_sl_tp.empty:
        return {"trades_analyzed": 0}

    has_sl_tp["planned_risk"] = abs(has_sl_tp["entry_price"] - has_sl_tp["stop_loss"])
    has_sl_tp["planned_reward"] = abs(has_sl_tp["take_profit"] - has_sl_tp["entry_price"])
    mask = has_sl_tp["planned_risk"] > 0
    has_sl_tp.loc[mask, "planned_rr"] = has_sl_tp.loc[mask, "planned_reward"] / has_sl_tp.loc[mask, "planned_risk"]

    # Actual R:R based on exit
    has_exit = has_sl_tp[has_sl_tp["exit_price"].notna()].copy()
    if not has_exit.empty:
        has_exit["actual_move"] = has_exit.apply(
            lambda r: (r["exit_price"] - r["entry_price"]) if r["direction"] == "BUY"
            else (r["entry_price"] - r["exit_price"]),
            axis=1,
        )
        mask2 = has_exit["planned_risk"] > 0
        has_exit.loc[mask2, "actual_rr"] = has_exit.loc[mask2, "actual_move"] / has_exit.loc[mask2, "planned_risk"]

    # SL/TP hit rates
    winners = closed[closed["profit_loss"] > 0]
    losers = closed[closed["profit_loss"] <= 0]

    return _safe_dict({
        "trades_analyzed": int(len(has_sl_tp)),
        "avg_planned_rr": round(has_sl_tp["planned_rr"].mean(), 2) if "planned_rr" in has_sl_tp.columns else None,
        "avg_actual_rr": round(has_exit["actual_rr"].mean(), 2) if not has_exit.empty and "actual_rr" in has_exit.columns else None,
        "tp_hit_rate": round(len(winners) / len(closed) * 100, 1) if len(closed) > 0 else 0,
        "sl_hit_rate": round(len(losers) / len(closed) * 100, 1) if len(closed) > 0 else 0,
        "avg_winner": round(winners["profit_loss"].mean(), 2) if not winners.empty else 0,
        "avg_loser": round(losers["profit_loss"].mean(), 2) if not losers.empty else 0,
    })


def signal_indicator_analysis(df):
    """Win rate broken down by RSI, ADX, and range_position buckets."""
    closed = _closed_trades(df)
    if closed.empty:
        return {}

    result = {}

    # RSI buckets
    if "rsi" in closed.columns and closed["rsi"].notna().any():
        rsi_df = closed[closed["rsi"].notna()].copy()
        rsi_df["rsi_bucket"] = pd.cut(rsi_df["rsi"], bins=[0, 30, 40, 50, 60, 70, 100],
                                       labels=["<30", "30-40", "40-50", "50-60", "60-70", ">70"])
        rsi_stats = {}
        for bucket, group in rsi_df.groupby("rsi_bucket", observed=True):
            rsi_stats[str(bucket)] = _win_stats(group)
        result["rsi"] = rsi_stats

    # ADX buckets
    if "adx" in closed.columns and closed["adx"].notna().any():
        adx_df = closed[closed["adx"].notna()].copy()
        adx_df["adx_bucket"] = pd.cut(adx_df["adx"], bins=[0, 15, 20, 25, 30, 50, 100],
                                       labels=["<15", "15-20", "20-25", "25-30", "30-50", ">50"])
        adx_stats = {}
        for bucket, group in adx_df.groupby("adx_bucket", observed=True):
            adx_stats[str(bucket)] = _win_stats(group)
        result["adx"] = adx_stats

    # Range position buckets (for scalpers)
    if "range_position" in closed.columns and closed["range_position"].notna().any():
        rp_df = closed[closed["range_position"].notna()].copy()
        rp_df["rp_bucket"] = pd.cut(rp_df["range_position"], bins=[0, 20, 40, 60, 80, 100],
                                     labels=["0-20", "20-40", "40-60", "60-80", "80-100"])
        rp_stats = {}
        for bucket, group in rp_df.groupby("rp_bucket", observed=True):
            rp_stats[str(bucket)] = _win_stats(group)
        result["range_position"] = rp_stats

    return result


def hold_duration_analysis(df):
    """Analyze correlation between hold duration and outcome."""
    closed = _closed_trades(df)
    if closed.empty or "hold_hours" not in closed.columns:
        return {}

    has_hold = closed[closed["hold_hours"].notna()].copy()
    if has_hold.empty:
        return {}

    # Bucket by hold duration
    bins = [0, 1, 4, 12, 24, 48, float("inf")]
    labels = ["<1h", "1-4h", "4-12h", "12-24h", "24-48h", ">48h"]
    has_hold["hold_bucket"] = pd.cut(has_hold["hold_hours"], bins=bins, labels=labels)

    result = {}
    for bucket, group in has_hold.groupby("hold_bucket", observed=True):
        result[str(bucket)] = _win_stats(group)

    # Overall stats
    winners = has_hold[has_hold["profit_loss"] > 0]
    losers = has_hold[has_hold["profit_loss"] <= 0]
    result["_summary"] = _safe_dict({
        "avg_hold_all": round(has_hold["hold_hours"].mean(), 1),
        "avg_hold_winners": round(winners["hold_hours"].mean(), 1) if not winners.empty else None,
        "avg_hold_losers": round(losers["hold_hours"].mean(), 1) if not losers.empty else None,
    })

    return result


def drawdown_analysis(df):
    """Analyze drawdown patterns and losing streaks."""
    closed = _closed_trades(df)
    if closed.empty:
        return {}

    closed = closed.sort_values("timestamp" if "timestamp" in closed.columns else "id")
    pls = closed["profit_loss"].values

    # Calculate streaks
    max_loss_streak = 0
    current_streak = 0
    streaks = []
    for pl in pls:
        if pl <= 0:
            current_streak += 1
            max_loss_streak = max(max_loss_streak, current_streak)
        else:
            if current_streak > 0:
                streaks.append(current_streak)
            current_streak = 0
    if current_streak > 0:
        streaks.append(current_streak)

    # Cumulative P/L for drawdown
    cumulative = pd.Series(pls).cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    max_drawdown = drawdown.min()

    return _safe_dict({
        "max_drawdown": round(float(max_drawdown), 2),
        "max_loss_streak": int(max_loss_streak),
        "avg_loss_streak": round(sum(streaks) / len(streaks), 1) if streaks else 0,
        "total_trades": int(len(closed)),
        "total_pl": round(float(closed["profit_loss"].sum()), 2),
    })


# ── Type-specific analyses ───────────────────────────────────────


def ai_confidence_vs_outcome(df):
    """Win rate by AI confidence bucket (AI bot only)."""
    closed = _closed_trades(df)
    if closed.empty or "confidence" not in closed.columns:
        return {}

    has_conf = closed[closed["confidence"].notna() & (closed["confidence"] > 0)].copy()
    if has_conf.empty:
        return {}

    has_conf["conf_bucket"] = pd.cut(has_conf["confidence"], bins=[0, 3, 5, 7, 9, 10],
                                      labels=["1-3", "4-5", "6-7", "8-9", "10"])
    result = {}
    for bucket, group in has_conf.groupby("conf_bucket", observed=True):
        result[str(bucket)] = _win_stats(group)
    return result


def scalper_zone_analysis(df):
    """Win rate by entry zone/range_position (scalper only)."""
    closed = _closed_trades(df)
    if closed.empty or "range_position" not in closed.columns:
        return {}

    has_rp = closed[closed["range_position"].notna()].copy()
    if has_rp.empty:
        return {}

    # Combine with direction for more insight
    result = {}
    for direction in ["BUY", "SELL"]:
        dir_df = has_rp[has_rp["direction"] == direction]
        if dir_df.empty:
            continue
        dir_df = dir_df.copy()
        dir_df["zone"] = pd.cut(dir_df["range_position"], bins=[0, 25, 50, 75, 100],
                                 labels=["bottom_25", "lower_mid", "upper_mid", "top_25"])
        zone_stats = {}
        for zone, group in dir_df.groupby("zone", observed=True):
            zone_stats[str(zone)] = _win_stats(group)
        result[direction] = zone_stats

    return result


# ── Cross-bot comparison ─────────────────────────────────────────


def cross_bot_comparison(all_data):
    """Compare performance across all bots.

    Args:
        all_data: dict of bot_id -> DataFrame

    Returns:
        dict with side-by-side comparison per coin, regime, and time
    """
    result = {"per_bot": {}, "per_coin": {}, "per_regime": {}}

    for bot_id, df in all_data.items():
        closed = _closed_trades(df)
        if closed.empty:
            result["per_bot"][bot_id] = {"trades": 0}
            continue

        wins = (closed["profit_loss"] > 0).sum()
        result["per_bot"][bot_id] = _safe_dict({
            "trades": int(len(closed)),
            "win_rate": round(wins / len(closed) * 100, 1),
            "total_pl": round(closed["profit_loss"].sum(), 2),
            "avg_pl": round(closed["profit_loss"].mean(), 2),
            "best_trade": round(closed["profit_loss"].max(), 2),
            "worst_trade": round(closed["profit_loss"].min(), 2),
        })

    # Combine all for per-coin and per-regime comparisons
    all_closed = []
    for bot_id, df in all_data.items():
        closed = _closed_trades(df)
        if not closed.empty:
            all_closed.append(closed)

    if not all_closed:
        return result

    combined = pd.concat(all_closed, ignore_index=True)

    # Per coin across bots
    for epic in combined["epic"].unique():
        coin_data = combined[combined["epic"] == epic]
        coin_bots = {}
        for bot_id, group in coin_data.groupby("bot"):
            coin_bots[bot_id] = _win_stats(group)
        result["per_coin"][epic] = coin_bots

    # Per regime across bots
    if "regime" in combined.columns:
        for regime in combined["regime"].unique():
            regime_data = combined[combined["regime"] == regime]
            regime_bots = {}
            for bot_id, group in regime_data.groupby("bot"):
                regime_bots[bot_id] = _win_stats(group)
            result["per_regime"][regime] = regime_bots

    return result


def sharpe_ratio(df, risk_free_rate=0.0):
    """Calculate annualized Sharpe ratio from trade P/L series."""
    closed = _closed_trades(df)
    if closed.empty or len(closed) < 5:
        return {"sharpe_ratio": None, "daily_returns": 0}

    if "timestamp" not in closed.columns or closed["timestamp"].isna().all():
        return {"sharpe_ratio": None, "daily_returns": 0}

    closed = closed.sort_values("timestamp").copy()
    closed["date"] = closed["timestamp"].dt.date
    daily_pl = closed.groupby("date")["profit_loss"].sum()

    if len(daily_pl) < 5:
        return {"sharpe_ratio": None, "daily_returns": int(len(daily_pl))}

    mean_return = daily_pl.mean()
    std_return = daily_pl.std()

    if std_return == 0 or math.isnan(std_return):
        return {"sharpe_ratio": None, "daily_returns": int(len(daily_pl))}

    daily_sharpe = (mean_return - risk_free_rate) / std_return
    annualized = daily_sharpe * math.sqrt(252)

    return _safe_dict({
        "sharpe_ratio": round(annualized, 3),
        "daily_returns": int(len(daily_pl)),
        "mean_daily_pl": round(float(mean_return), 2),
        "std_daily_pl": round(float(std_return), 2),
    })


def profit_factor_analysis(df):
    """Calculate profit factor: sum(wins) / abs(sum(losses))."""
    closed = _closed_trades(df)
    if closed.empty:
        return {"profit_factor": None}

    gross_wins = closed[closed["profit_loss"] > 0]["profit_loss"].sum()
    gross_losses = abs(closed[closed["profit_loss"] <= 0]["profit_loss"].sum())

    if gross_losses == 0:
        pf = None if gross_wins == 0 else 99.0
    else:
        pf = round(float(gross_wins / gross_losses), 3)

    return _safe_dict({
        "profit_factor": pf,
        "gross_wins": round(float(gross_wins), 2),
        "gross_losses": round(float(gross_losses), 2),
    })


def composite_score(df):
    """Calculate composite bot score combining multiple metrics."""
    closed = _closed_trades(df)
    if closed.empty:
        return {"composite_score": None}

    total = len(closed)
    wins = (closed["profit_loss"] > 0).sum()
    wr = wins / total * 100 if total > 0 else 0

    sr = sharpe_ratio(df)
    s = sr.get("sharpe_ratio")

    pf_data = profit_factor_analysis(df)
    pf = pf_data.get("profit_factor")

    dd_data = drawdown_analysis(df)
    max_dd = abs(dd_data.get("max_drawdown", 0))

    # Normalize to 0-1
    sharpe_norm = max(0, min(1, (s + 2) / 5)) if s is not None else 0.3
    if pf is None:
        pf_norm = 0.3
    else:
        pf_norm = max(0, min(1, pf / 3))
    wr_norm = wr / 100
    dd_norm = max(0, min(1, 1 - max_dd / 50))
    vol_norm = max(0, min(1, math.log10(max(total, 1)) / math.log10(500)))

    score = (
        0.30 * sharpe_norm
        + 0.25 * pf_norm
        + 0.20 * wr_norm
        + 0.15 * dd_norm
        + 0.10 * vol_norm
    )

    return _safe_dict({
        "composite_score": round(score, 4),
        "components": {
            "sharpe_norm": round(sharpe_norm, 3),
            "pf_norm": round(pf_norm, 3),
            "wr_norm": round(wr_norm, 3),
            "dd_norm": round(dd_norm, 3),
            "vol_norm": round(vol_norm, 3),
        },
    })


def full_bot_analysis(df, bot_type="rule"):
    """Run all relevant analyses for a single bot.

    Args:
        df: DataFrame of trades for this bot
        bot_type: "rule" | "ai" | "scalper"

    Returns:
        dict with all analysis results
    """
    result = {
        "by_regime": win_rate_by_regime(df),
        "by_coin": win_rate_by_coin(df),
        "by_hour": win_rate_by_hour(df),
        "by_direction": win_rate_by_direction(df),
        "by_exit_reason": win_rate_by_exit_reason(df),
        "risk_reward": risk_reward_analysis(df),
        "indicators": signal_indicator_analysis(df),
        "hold_duration": hold_duration_analysis(df),
        "drawdown": drawdown_analysis(df),
        "sharpe": sharpe_ratio(df),
        "profit_factor": profit_factor_analysis(df),
        "composite": composite_score(df),
    }

    if bot_type == "ai":
        result["confidence_vs_outcome"] = ai_confidence_vs_outcome(df)

    if bot_type == "scalper":
        result["zone_analysis"] = scalper_zone_analysis(df)

    return result
