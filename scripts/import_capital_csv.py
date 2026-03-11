"""
Import Capital.com funds history CSV into the dashboard database.
Maps instrument names to epic codes and imports TRADE entries with P&L.

Usage:
    python scripts/import_capital_csv.py <csv_file> <db_path> <bot_name>

Example:
    python scripts/import_capital_csv.py funds_history.csv data_ai/trades.db ai
"""

import csv
import sqlite3
import sys
from datetime import datetime

# Map Capital.com instrument symbols to our epic codes
INSTRUMENT_MAP = {
    "BTC/USD": "BTCUSD",
    "ETH/USD": "ETHUSD",
    "SOL/USD": "SOLUSD",
    "XRP/USD": "XRPUSD",
    "ADA/USD": "ADAUSD",
    "DOT/USD": "DOTUSD",
    "LINK/USD": "LINKUSD",
    "AVAX/USD": "AVAXUSD",
    "DOGE/USD": "DOGEUSD",
    "MATIC/USD": "MATICUSD",
    "UNI/USD": "UNIUSD",
}


def import_csv(csv_path, db_path, bot_name):
    """Import Capital.com CSV into the trades database."""

    # Read CSV
    trades = []
    balance_snapshots = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry_type = row["Type"].strip()
            amount = float(row["Amount"])
            balance = float(row["Balance"])
            modified = row["Modified"].strip()
            instrument = row["Instrument Symbol"].strip()
            trade_id = row["Trade Id"].strip()

            # Parse timestamp
            ts = datetime.strptime(modified, "%Y-%m-%d %H:%M:%S")

            # Always create a balance snapshot
            balance_snapshots.append({
                "timestamp": ts.isoformat(),
                "balance": balance,
                "available": balance,
                "profit_loss": amount if entry_type == "TRADE" else 0,
                "bot_name": bot_name,
            })

            if entry_type == "TRADE" and instrument:
                epic = INSTRUMENT_MAP.get(instrument, instrument.replace("/", ""))
                trades.append({
                    "timestamp": ts.isoformat(),
                    "epic": epic,
                    "direction": "BUY" if amount >= 0 else "SELL",  # Approximation
                    "size": 0,  # Unknown from CSV
                    "entry_price": 0,  # Unknown from CSV
                    "stop_loss": 0,
                    "take_profit": 0,
                    "deal_id": trade_id or f"csv_import_{ts.timestamp()}",
                    "status": "CLOSED",
                    "exit_price": 0,
                    "exit_timestamp": ts.isoformat(),
                    "profit_loss": amount,
                    "signal_details": f"Imported from Capital.com CSV ({bot_name})",
                    "balance_after": balance,
                })

    # Connect to DB
    db = sqlite3.connect(db_path)

    # Ensure tables exist
    db.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            epic TEXT NOT NULL,
            direction TEXT NOT NULL,
            size REAL NOT NULL,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            deal_id TEXT,
            status TEXT DEFAULT 'OPEN',
            exit_price REAL,
            exit_timestamp TEXT,
            profit_loss REAL,
            signal_details TEXT,
            balance_after REAL
        )
    """)
    # Add balance_after column if missing (migration)
    try:
        db.execute("ALTER TABLE trades ADD COLUMN balance_after REAL")
    except Exception:
        pass
    db.execute("""
        CREATE TABLE IF NOT EXISTS balance_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            balance REAL NOT NULL,
            available REAL,
            profit_loss REAL,
            bot_name TEXT DEFAULT 'rule'
        )
    """)

    # Check existing trade deal_ids to avoid duplicates
    existing = set()
    for row in db.execute("SELECT deal_id FROM trades"):
        existing.add(row[0])

    # Import trades
    imported_trades = 0
    skipped = 0
    for t in trades:
        if t["deal_id"] in existing:
            # Update existing trade with P&L and balance if missing
            db.execute("""
                UPDATE trades SET profit_loss = ?, exit_timestamp = ?, status = 'CLOSED',
                    balance_after = ?
                WHERE deal_id = ? AND (profit_loss IS NULL OR profit_loss = 0)
            """, (t["profit_loss"], t["exit_timestamp"], t["balance_after"], t["deal_id"]))
            skipped += 1
        else:
            db.execute("""
                INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                    stop_loss, take_profit, deal_id, status, exit_price,
                    exit_timestamp, profit_loss, signal_details, balance_after)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t["timestamp"], t["epic"], t["direction"], t["size"],
                t["entry_price"], t["stop_loss"], t["take_profit"],
                t["deal_id"], t["status"], t["exit_price"],
                t["exit_timestamp"], t["profit_loss"], t["signal_details"],
                t["balance_after"],
            ))
            imported_trades += 1

    # Import balance snapshots (dedupe by timestamp)
    existing_ts = set()
    for row in db.execute("SELECT timestamp FROM balance_snapshots WHERE bot_name = ?", (bot_name,)):
        existing_ts.add(row[0])

    imported_balances = 0
    for snap in balance_snapshots:
        if snap["timestamp"] not in existing_ts:
            db.execute("""
                INSERT INTO balance_snapshots (timestamp, balance, available, profit_loss, bot_name)
                VALUES (?, ?, ?, ?, ?)
            """, (snap["timestamp"], snap["balance"], snap["available"],
                  snap["profit_loss"], snap["bot_name"]))
            imported_balances += 1

    db.commit()
    db.close()

    print(f"Import complete for {bot_name}:")
    print(f"  Trades: {imported_trades} imported, {skipped} updated/skipped")
    print(f"  Balance snapshots: {imported_balances} imported")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python scripts/import_capital_csv.py <csv_file> <db_path> <bot_name>")
        print("Example: python scripts/import_capital_csv.py funds_history.csv data_ai/trades.db ai")
        sys.exit(1)

    import_csv(sys.argv[1], sys.argv[2], sys.argv[3])
