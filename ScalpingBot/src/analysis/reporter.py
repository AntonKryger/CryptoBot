import sqlite3
import pandas as pd
import json
import os
import logging

logger = logging.getLogger(__name__)


class Reporter:
    """
    Data analysis module for reviewing bot performance in Claude Code sessions.
    Exports data in readable formats for collaborative analysis.
    """

    def __init__(self, config):
        self.db_path = config.get("database", {}).get("path", "data/trades.db")
        self.export_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")
        os.makedirs(self.export_dir, exist_ok=True)

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def get_all_trades(self):
        """Get all trades as a pandas DataFrame."""
        conn = self._connect()
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY timestamp DESC", conn)
        conn.close()
        return df

    def get_summary(self):
        """Get a human-readable performance summary."""
        df = self.get_all_trades()
        if df.empty:
            return "Ingen handler endnu."

        closed = df[df["status"] == "CLOSED"]
        open_trades = df[df["status"] == "OPEN"]

        summary = []
        summary.append("=" * 50)
        summary.append("CRYPTOBOT PERFORMANCE RAPPORT")
        summary.append("=" * 50)
        summary.append(f"Totale handler: {len(df)}")
        summary.append(f"Åbne positioner: {len(open_trades)}")
        summary.append(f"Lukkede handler: {len(closed)}")

        if not closed.empty:
            wins = closed[closed["profit_loss"] > 0]
            losses = closed[closed["profit_loss"] < 0]
            total_pl = closed["profit_loss"].sum()
            avg_pl = closed["profit_loss"].mean()

            summary.append(f"\nVundne: {len(wins)} ({len(wins)/len(closed)*100:.1f}%)")
            summary.append(f"Tabte: {len(losses)} ({len(losses)/len(closed)*100:.1f}%)")
            summary.append(f"Total P/L: €{total_pl:.2f}")
            summary.append(f"Gennemsnit P/L per trade: €{avg_pl:.2f}")

            if not wins.empty:
                summary.append(f"Gennemsnit gevinst: €{wins['profit_loss'].mean():.2f}")
            if not losses.empty:
                summary.append(f"Gennemsnit tab: €{losses['profit_loss'].mean():.2f}")

            # Per coin breakdown
            summary.append(f"\n{'─' * 50}")
            summary.append("PER COIN:")
            for epic in closed["epic"].unique():
                coin_trades = closed[closed["epic"] == epic]
                coin_pl = coin_trades["profit_loss"].sum()
                coin_wins = len(coin_trades[coin_trades["profit_loss"] > 0])
                summary.append(f"  {epic}: {len(coin_trades)} handler, P/L: €{coin_pl:.2f}, "
                               f"Win rate: {coin_wins/len(coin_trades)*100:.0f}%")

        # Open positions
        if not open_trades.empty:
            summary.append(f"\n{'─' * 50}")
            summary.append("ÅBNE POSITIONER:")
            for _, trade in open_trades.iterrows():
                summary.append(f"  {trade['epic']}: {trade['direction']} x{trade['size']} @ €{trade['entry_price']:.2f}")

        summary.append("=" * 50)
        return "\n".join(summary)

    def export_csv(self, filename="trades_export.csv"):
        """Export all trades to CSV for external analysis."""
        df = self.get_all_trades()
        path = os.path.join(self.export_dir, filename)
        df.to_csv(path, index=False)
        logger.info(f"Trades exported to {path}")
        return path

    def export_json(self, filename="trades_export.json"):
        """Export all trades to JSON."""
        df = self.get_all_trades()
        path = os.path.join(self.export_dir, filename)
        df.to_json(path, orient="records", indent=2)
        logger.info(f"Trades exported to {path}")
        return path

    def get_daily_performance(self):
        """Get daily P/L summary."""
        conn = self._connect()
        df = pd.read_sql_query("""
            SELECT
                DATE(timestamp) as date,
                COUNT(*) as trades,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losses,
                COALESCE(SUM(profit_loss), 0) as daily_pl
            FROM trades
            WHERE status = 'CLOSED'
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        """, conn)
        conn.close()
        return df

    def get_signal_analysis(self):
        """Analyze which signals lead to the best trades."""
        df = self.get_all_trades()
        closed = df[df["status"] == "CLOSED"].copy()
        if closed.empty:
            return "Ingen lukkede handler at analysere."

        # Direction analysis
        buy_trades = closed[closed["direction"] == "BUY"]
        sell_trades = closed[closed["direction"] == "SELL"]

        analysis = []
        analysis.append("SIGNAL ANALYSE:")
        if not buy_trades.empty:
            analysis.append(f"  LONG trades: {len(buy_trades)}, "
                            f"Avg P/L: €{buy_trades['profit_loss'].mean():.2f}, "
                            f"Win rate: {len(buy_trades[buy_trades['profit_loss']>0])/len(buy_trades)*100:.0f}%")
        if not sell_trades.empty:
            analysis.append(f"  SHORT trades: {len(sell_trades)}, "
                            f"Avg P/L: €{sell_trades['profit_loss'].mean():.2f}, "
                            f"Win rate: {len(sell_trades[sell_trades['profit_loss']>0])/len(sell_trades)*100:.0f}%")

        return "\n".join(analysis)
