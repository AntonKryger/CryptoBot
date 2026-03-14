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

    # ── Period-filtered comparison for /compare page ──

    def _period_cutoff(self, period):
        """Get UTC cutoff datetime for a period string."""
        now = datetime.now(timezone.utc)
        if period == "today":
            return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        elif period == "week":
            return now - timedelta(days=now.weekday())  # Monday
        elif period == "month":
            return datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        elif period == "year":
            return datetime(now.year, 1, 1, tzinfo=timezone.utc)
        return None  # "all" = no cutoff

    def _filter_by_period(self, closed, period):
        """Filter closed trades by period based on exit_timestamp."""
        if period == "all" or closed.empty:
            return closed
        cutoff = self._period_cutoff(period)
        if cutoff is None:
            return closed
        closed = closed.copy()
        closed["exit_dt"] = pd.to_datetime(closed["exit_timestamp"], format="ISO8601", utc=True, errors="coerce")
        return closed[closed["exit_dt"] >= cutoff]

    def get_period_comparison(self, period="all"):
        """Full comparison data for all bots within a period.

        Returns dict per bot with: overview, stats, daily_pnl, coin_stats, direction_stats.
        All P&L metrics include percentage-based versions.
        """
        result = {}
        for bot_name in self.db_paths:
            df = self._load_trades(bot_name)
            if df.empty:
                result[bot_name] = self._empty_period_result()
                continue

            all_closed = self._closed_with_pl(df)
            closed = self._filter_by_period(all_closed, period)
            open_trades = df[df["status"] == "OPEN"]

            # Find starting balance for the period (first balance snapshot or estimate)
            start_balance = self._get_period_start_balance(bot_name, period)

            result[bot_name] = self._compute_period_stats(
                closed, open_trades, start_balance, period
            )

        return result

    def _empty_period_result(self):
        return {
            "trades": 0, "wins": 0, "losses": 0, "open": 0,
            "win_rate": 0, "total_pl": 0, "roi_pct": 0,
            "avg_win": 0, "avg_loss": 0, "avg_win_pct": 0, "avg_loss_pct": 0,
            "profit_factor": 0, "sharpe": 0,
            "max_drawdown": 0, "max_dd_pct": 0,
            "best_trade": 0, "worst_trade": 0,
            "max_win_streak": 0, "max_loss_streak": 0,
            "daily_pnl": {"dates": [], "pnl": [], "cumulative_pct": []},
            "coin_stats": [],
            "direction_stats": {"buy_count": 0, "sell_count": 0, "buy_pl": 0, "sell_pl": 0},
            "start_balance": 0,
        }

    def _get_period_start_balance(self, bot_name, period):
        """Get the balance at the start of a period."""
        df = self._load_balances(bot_name)
        if df.empty:
            return 0

        df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601")
        if bot_name:
            df = df[df["bot"] == bot_name]

        if period == "all" or df.empty:
            return float(df.sort_values("timestamp").iloc[0]["balance"]) if not df.empty else 0

        cutoff = self._period_cutoff(period)
        if cutoff is None:
            return float(df.sort_values("timestamp").iloc[0]["balance"]) if not df.empty else 0

        # Find the balance closest to (but before) the cutoff
        cutoff_naive = cutoff.replace(tzinfo=None)
        before = df[df["timestamp"] <= cutoff_naive]
        if not before.empty:
            return float(before.sort_values("timestamp").iloc[-1]["balance"])
        # Fallback: earliest balance
        return float(df.sort_values("timestamp").iloc[0]["balance"])

    def _compute_period_stats(self, closed, open_trades, start_balance, period):
        """Compute all stats for a filtered set of trades."""
        if closed.empty:
            r = self._empty_period_result()
            r["open"] = len(open_trades)
            r["start_balance"] = round(start_balance, 2)
            return r

        wins = closed[closed["profit_loss"] > 0]
        losses = closed[closed["profit_loss"] < 0]
        total_win_eur = float(wins["profit_loss"].sum()) if not wins.empty else 0
        total_loss_eur = abs(float(losses["profit_loss"].sum())) if not losses.empty else 0
        total_pl = float(closed["profit_loss"].sum())

        # ROI % relative to start balance
        roi_pct = (total_pl / start_balance * 100) if start_balance > 0 else 0

        # Avg win/loss as percentage of start_balance
        avg_win = float(wins["profit_loss"].mean()) if not wins.empty else 0
        avg_loss = float(losses["profit_loss"].mean()) if not losses.empty else 0
        avg_win_pct = (avg_win / start_balance * 100) if start_balance > 0 else 0
        avg_loss_pct = (avg_loss / start_balance * 100) if start_balance > 0 else 0

        # Streaks
        sorted_closed = closed.sort_values("exit_timestamp")
        pls = sorted_closed["profit_loss"].dropna().tolist()
        max_win_s, max_loss_s = 0, 0
        ws, ls = 0, 0
        for pl in pls:
            if pl > 0:
                ws += 1; ls = 0
            elif pl < 0:
                ls += 1; ws = 0
            else:
                ws = 0; ls = 0
            max_win_s = max(max_win_s, ws)
            max_loss_s = max(max_loss_s, ls)

        # Max drawdown
        cum_pl = sorted_closed["profit_loss"].cumsum()
        running_max = cum_pl.cummax()
        drawdown = running_max - cum_pl
        max_dd = float(drawdown.max()) if not drawdown.empty else 0
        max_dd_pct = (max_dd / start_balance * 100) if start_balance > 0 else 0

        # Sharpe
        sharpe = 0
        if len(pls) >= 5:
            mean_r = closed["profit_loss"].mean()
            std_r = closed["profit_loss"].std()
            if std_r and std_r > 0:
                sharpe = round(float(mean_r / std_r * (252 ** 0.5)), 2)

        # Daily P&L with cumulative %
        daily_pnl = self._compute_daily_pnl_pct(sorted_closed, start_balance)

        # Per-coin stats
        coin_stats = []
        for epic, group in closed.groupby("epic"):
            g_wins = group[group["profit_loss"] > 0]
            coin_pl = float(group["profit_loss"].sum())
            coin_stats.append({
                "epic": epic,
                "trades": len(group),
                "win_rate": round(len(g_wins) / max(len(group), 1) * 100, 1),
                "total_pl": round(coin_pl, 2),
                "roi_pct": round(coin_pl / start_balance * 100, 3) if start_balance > 0 else 0,
            })
        coin_stats.sort(key=lambda x: x["total_pl"], reverse=True)

        # Direction stats
        buys = closed[closed["direction"] == "BUY"]
        sells = closed[closed["direction"] == "SELL"]

        return {
            "trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "open": len(open_trades),
            "win_rate": round(len(wins) / max(len(closed), 1) * 100, 1),
            "total_pl": round(total_pl, 2),
            "roi_pct": round(roi_pct, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_win_pct": round(avg_win_pct, 3),
            "avg_loss_pct": round(avg_loss_pct, 3),
            "profit_factor": round(total_win_eur / max(total_loss_eur, 0.01), 2),
            "sharpe": sharpe,
            "max_drawdown": round(max_dd, 2),
            "max_dd_pct": round(max_dd_pct, 2),
            "best_trade": round(float(closed["profit_loss"].max()), 2),
            "worst_trade": round(float(closed["profit_loss"].min()), 2),
            "max_win_streak": max_win_s,
            "max_loss_streak": max_loss_s,
            "daily_pnl": daily_pnl,
            "coin_stats": coin_stats,
            "direction_stats": {
                "buy_count": len(buys),
                "sell_count": len(sells),
                "buy_pl": round(float(buys["profit_loss"].sum()), 2) if not buys.empty else 0,
                "sell_pl": round(float(sells["profit_loss"].sum()), 2) if not sells.empty else 0,
            },
            "start_balance": round(start_balance, 2),
        }

    def _compute_daily_pnl_pct(self, sorted_closed, start_balance):
        """Compute daily P&L with cumulative percentage."""
        if sorted_closed.empty:
            return {"dates": [], "pnl": [], "cumulative_pct": []}

        sc = sorted_closed[sorted_closed["exit_timestamp"].notna()].copy()
        if sc.empty:
            return {"dates": [], "pnl": [], "cumulative_pct": []}

        sc["date"] = pd.to_datetime(sc["exit_timestamp"], format="ISO8601").dt.date
        daily = sc.groupby("date")["profit_loss"].sum().reset_index()
        daily = daily.sort_values("date")
        daily["cumulative"] = daily["profit_loss"].cumsum()
        daily["cumulative_pct"] = (daily["cumulative"] / start_balance * 100) if start_balance > 0 else 0

        return {
            "dates": [str(d) for d in daily["date"]],
            "pnl": [round(float(v), 2) for v in daily["profit_loss"]],
            "cumulative_pct": [round(float(v), 2) for v in daily["cumulative_pct"]],
        }
