"""
Statistics engine for the trading dashboard.
Reads from SQLite databases (rule bot + AI bot) and computes all metrics.
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone


class StatsEngine:
    """Compute trading statistics from one or more bot databases."""

    def __init__(self, db_paths: dict):
        """
        Args:
            db_paths: {"rule": "data/trades.db", "ai": "data_ai/trades.db"}
        """
        self.db_paths = db_paths

    def _get_db(self, bot_name):
        path = self.db_paths.get(bot_name)
        if not path:
            return None
        try:
            return sqlite3.connect(path)
        except Exception:
            return None

    def _load_trades(self, bot_name=None):
        """Load trades as DataFrame. If bot_name is None, load all bots combined."""
        frames = []
        bots = [bot_name] if bot_name else list(self.db_paths.keys())
        for bn in bots:
            db = self._get_db(bn)
            if db is None:
                continue
            try:
                df = pd.read_sql_query("SELECT * FROM trades", db)
                df["bot"] = bn
                frames.append(df)
            except Exception:
                pass
            finally:
                db.close()
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames, ignore_index=True)
        # Ensure profit_loss is numeric (NULL -> NaN)
        if "profit_loss" in combined.columns:
            combined["profit_loss"] = pd.to_numeric(combined["profit_loss"], errors="coerce")
        return combined

    def _load_balances(self, bot_name=None):
        """Load balance snapshots as DataFrame."""
        frames = []
        bots = [bot_name] if bot_name else list(self.db_paths.keys())
        for bn in bots:
            db = self._get_db(bn)
            if db is None:
                continue
            try:
                df = pd.read_sql_query("SELECT * FROM balance_snapshots", db)
                df["bot"] = bn
                frames.append(df)
            except Exception:
                pass
            finally:
                db.close()
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _closed_with_pl(self, df):
        """Get closed trades that have profit_loss data (not NULL)."""
        if df.empty:
            return pd.DataFrame()
        closed = df[df["status"] == "CLOSED"].copy()
        if closed.empty:
            return closed
        return closed[closed["profit_loss"].notna()]

    def get_overview(self, bot_name=None):
        """KPI overview: win rate, total P&L, open trades, today's P&L."""
        df = self._load_trades(bot_name)
        if df.empty:
            return {
                "total_trades": 0, "open_trades": 0, "closed_trades": 0,
                "closed_with_pl": 0,
                "win_rate": 0, "total_pl": 0, "today_pl": 0,
                "avg_win": 0, "avg_loss": 0, "profit_factor": 0,
            }

        all_closed = df[df["status"] == "CLOSED"]
        open_trades = df[df["status"] == "OPEN"]
        closed = self._closed_with_pl(df)

        wins = closed[closed["profit_loss"] > 0] if not closed.empty else pd.DataFrame()
        losses = closed[closed["profit_loss"] < 0] if not closed.empty else pd.DataFrame()

        total_wins = wins["profit_loss"].sum() if not wins.empty else 0
        total_losses = abs(losses["profit_loss"].sum()) if not losses.empty else 0

        # Today's P&L (VPS stores timestamps in UTC)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_pl = 0
        if not closed.empty and "exit_timestamp" in closed.columns:
            today_closed = closed[closed["exit_timestamp"].str.startswith(today, na=False)]
            today_pl = today_closed["profit_loss"].sum() if not today_closed.empty else 0

        return {
            "total_trades": len(df),
            "open_trades": len(open_trades),
            "closed_trades": len(all_closed),
            "closed_with_pl": len(closed),
            "win_rate": round(len(wins) / max(len(closed), 1) * 100, 1),
            "total_pl": round(closed["profit_loss"].sum(), 2) if not closed.empty else 0,
            "today_pl": round(float(today_pl), 2),
            "avg_win": round(float(wins["profit_loss"].mean()), 2) if not wins.empty else 0,
            "avg_loss": round(float(losses["profit_loss"].mean()), 2) if not losses.empty else 0,
            "profit_factor": round(total_wins / max(total_losses, 0.01), 2),
        }

    def get_detailed_stats(self, bot_name=None):
        """Extended statistics: streaks, drawdown, Sharpe."""
        df = self._load_trades(bot_name)
        closed = self._closed_with_pl(df)

        empty_result = {
            "max_win_streak": 0, "max_loss_streak": 0, "current_streak": 0,
            "current_streak_type": "none", "max_drawdown": 0, "sharpe_ratio": 0,
            "best_trade": 0, "worst_trade": 0,
        }

        if closed.empty:
            return empty_result

        # Sort by exit time
        closed = closed.sort_values("exit_timestamp")
        pls = closed["profit_loss"].dropna().tolist()

        if not pls:
            return empty_result

        # Streaks
        max_win, max_loss = 0, 0
        win_streak, loss_streak = 0, 0
        for pl in pls:
            if pl > 0:
                win_streak += 1
                loss_streak = 0
            elif pl < 0:
                loss_streak += 1
                win_streak = 0
            else:
                win_streak = 0
                loss_streak = 0
            max_win = max(max_win, win_streak)
            max_loss = max(max_loss, loss_streak)

        # Current streak
        last = pls[-1]
        cur_type = "win" if last > 0 else "loss" if last < 0 else "even"
        cur = 0
        for pl in reversed(pls):
            if (cur_type == "win" and pl > 0) or (cur_type == "loss" and pl < 0):
                cur += 1
            else:
                break

        # Max drawdown from cumulative P&L
        cum_pl = closed["profit_loss"].cumsum()
        running_max = cum_pl.cummax()
        drawdown = running_max - cum_pl
        max_dd = round(float(drawdown.max()), 2) if not drawdown.empty else 0

        # Simple Sharpe
        sharpe = 0
        if len(pls) >= 5:
            returns = closed["profit_loss"]
            mean_r = returns.mean()
            std_r = returns.std()
            if std_r and std_r > 0:
                sharpe = round(float(mean_r / std_r * (252 ** 0.5)), 2)

        return {
            "max_win_streak": max_win,
            "max_loss_streak": max_loss,
            "current_streak": cur,
            "current_streak_type": cur_type,
            "max_drawdown": max_dd,
            "sharpe_ratio": sharpe,
            "best_trade": round(float(closed["profit_loss"].max()), 2),
            "worst_trade": round(float(closed["profit_loss"].min()), 2),
        }

    def get_daily_pnl(self, bot_name=None, days=30):
        """Daily P&L for the last N days."""
        df = self._load_trades(bot_name)
        closed = self._closed_with_pl(df)

        if closed.empty:
            return {"dates": [], "pnl": [], "cumulative": []}

        closed = closed[closed["exit_timestamp"].notna()].copy()
        if closed.empty:
            return {"dates": [], "pnl": [], "cumulative": []}

        closed["date"] = pd.to_datetime(closed["exit_timestamp"]).dt.date
        daily = closed.groupby("date")["profit_loss"].sum().reset_index()
        daily = daily.sort_values("date").tail(days)
        daily["cumulative"] = daily["profit_loss"].cumsum()

        return {
            "dates": [str(d) for d in daily["date"]],
            "pnl": [round(float(v), 2) for v in daily["profit_loss"]],
            "cumulative": [round(float(v), 2) for v in daily["cumulative"]],
        }

    def get_instrument_stats(self, bot_name=None):
        """Per-instrument breakdown."""
        df = self._load_trades(bot_name)
        closed = self._closed_with_pl(df)

        if closed.empty:
            return []

        results = []
        for epic, group in closed.groupby("epic"):
            wins = group[group["profit_loss"] > 0]
            results.append({
                "epic": epic,
                "trades": len(group),
                "wins": len(wins),
                "win_rate": round(len(wins) / max(len(group), 1) * 100, 1),
                "total_pl": round(float(group["profit_loss"].sum()), 2),
                "avg_pl": round(float(group["profit_loss"].mean()), 2),
            })

        return sorted(results, key=lambda x: x["total_pl"], reverse=True)

    def get_calendar_data(self, bot_name=None):
        """Daily P&L for calendar heatmap."""
        df = self._load_trades(bot_name)
        closed = self._closed_with_pl(df)

        if closed.empty:
            return []

        closed = closed[closed["exit_timestamp"].notna()].copy()
        if closed.empty:
            return []

        closed["date"] = pd.to_datetime(closed["exit_timestamp"]).dt.strftime("%Y-%m-%d")
        daily = closed.groupby("date").agg(
            pnl=("profit_loss", "sum"),
            trades=("id", "count"),
        ).reset_index()

        return [
            {"date": row["date"], "pnl": round(float(row["pnl"]), 2), "trades": int(row["trades"])}
            for _, row in daily.iterrows()
        ]

    def get_trades(self, bot_name=None, limit=100, epic=None, direction=None, status=None):
        """Get trades with optional filters."""
        df = self._load_trades(bot_name)
        if df.empty:
            return []

        if epic:
            df = df[df["epic"].str.contains(epic, case=False, na=False)]
        if direction:
            df = df[df["direction"] == direction]
        if status:
            df = df[df["status"] == status]

        df = df.sort_values("timestamp", ascending=False).head(limit)

        # Convert to records, replacing NaN/NaT with None for valid JSON
        import math
        records = df.to_dict(orient="records")
        for rec in records:
            for key, val in rec.items():
                if val is None:
                    continue
                if isinstance(val, float) and math.isnan(val):
                    rec[key] = None
                elif hasattr(val, 'isoformat'):  # NaT check
                    try:
                        str(val)
                    except Exception:
                        rec[key] = None
        return records

    def get_balance_history(self, bot_name=None, hours=168):
        """Get balance history for chart."""
        df = self._load_balances(bot_name)
        if df.empty:
            return {"timestamps": [], "balances": []}

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        df = df[df["timestamp"] >= cutoff].sort_values("timestamp")

        if bot_name:
            df = df[df["bot"] == bot_name]

        return {
            "timestamps": [t.isoformat() + "Z" for t in df["timestamp"]],
            "balances": [round(float(b), 2) for b in df["balance"]],
        }

    def get_comparison(self):
        """Side-by-side comparison of all bots."""
        result = {}
        for bot_name in self.db_paths:
            result[bot_name] = {
                "overview": self.get_overview(bot_name),
                "stats": self.get_detailed_stats(bot_name),
            }
        return result
