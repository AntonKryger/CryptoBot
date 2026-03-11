"""
Clean reimport of all 3 Capital.com CSV files into correct databases.
Clears old CSV-imported data first, then imports fresh.

Exclusions:
- LIVE BOT: Skip SOL/USD -29.92 (manual trade)
- AI BOT: Skip BTC/USD -2242.42 (manual trade) + DEMO_TRANSFER rows
- Demo BOT: Skip DEMO_TRANSFER rows
- All: Skip SWAP rows (overnight fees, not trades)
"""

import csv
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INSTRUMENT_MAP = {
    "BTC/USD": "BTCUSD", "ETH/USD": "ETHUSD", "SOL/USD": "SOLUSD",
    "XRP/USD": "XRPUSD", "ADA/USD": "ADAUSD", "DOT/USD": "DOTUSD",
    "LINK/USD": "LINKUSD", "AVAX/USD": "AVAXUSD", "DOGE/USD": "DOGEUSD",
    "MATIC/USD": "MATICUSD", "UNI/USD": "UNIUSD",
}

IMPORTS = [
    {
        "csv": r"C:\Hjem\Capital\Rapporter\funds_history_09.03.2026-11.03.2026 LIVE BOT.csv",
        "db": os.path.join(BASE_DIR, "data", "trades.db"),
        "bot": "rule",
        "skip": [("SOLUSD", -29.92)],  # manual trade
    },
    {
        "csv": r"C:\Hjem\Capital\Rapporter\funds_history_08.02.2026-10.03.2026 AI BOT.csv",
        "db": os.path.join(BASE_DIR, "data_ai", "trades.db"),
        "bot": "ai",
        "skip": [("BTCUSD", -2242.42)],  # manual trade
    },
    {
        "csv": r"C:\Hjem\Capital\Rapporter\funds_history_08.02.2026-11.03.2026 BOT.csv",
        "db": os.path.join(BASE_DIR, "data_demo", "trades.db"),
        "bot": "demo",
        "skip": [],
    },
]


def ensure_tables(db):
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
    db.commit()


def clean_import(csv_path, db_path, bot_name, skip_list):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    ensure_tables(db)

    # Clear old CSV-imported data
    deleted_trades = db.execute(
        "DELETE FROM trades WHERE signal_details LIKE '%Imported from Capital.com CSV%'"
    ).rowcount
    deleted_snaps = db.execute(
        "DELETE FROM balance_snapshots WHERE bot_name = ?", (bot_name,)
    ).rowcount
    db.commit()
    print(f"\n{'='*60}")
    print(f"  {bot_name.upper()} BOT — {os.path.basename(csv_path)}")
    print(f"  DB: {db_path}")
    print(f"  Cleared: {deleted_trades} old trades, {deleted_snaps} old snapshots")

    trades = []
    balance_snapshots = []
    skipped_rows = []

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry_type = row["Type"].strip()
            amount = float(row["Amount"])
            balance = float(row["Balance"])
            modified = row["Modified"].strip()
            instrument = row["Instrument Symbol"].strip()
            trade_id = row["Trade Id"].strip()

            # Skip DEMO_TRANSFER
            if entry_type == "DEMO_TRANSFER":
                skipped_rows.append(f"DEMO_TRANSFER: {amount}")
                continue

            # Skip SWAP (overnight fees)
            if entry_type == "SWAP":
                skipped_rows.append(f"SWAP: {instrument} {amount}")
                continue

            ts = datetime.strptime(modified, "%Y-%m-%d %H:%M:%S")

            # Balance snapshot for all non-skipped rows
            balance_snapshots.append({
                "timestamp": ts.isoformat(),
                "balance": balance,
                "available": balance,
                "profit_loss": amount if entry_type == "TRADE" else 0,
                "bot_name": bot_name,
            })

            if entry_type == "TRADE" and instrument:
                epic = INSTRUMENT_MAP.get(instrument, instrument.replace("/", ""))

                # Check skip list (manual trades)
                should_skip = False
                for skip_epic, skip_amount in skip_list:
                    if epic == skip_epic and abs(amount - skip_amount) < 0.01:
                        skipped_rows.append(f"MANUAL: {epic} {amount}")
                        should_skip = True
                        break
                if should_skip:
                    continue

                trades.append({
                    "timestamp": ts.isoformat(),
                    "epic": epic,
                    "direction": "BUY" if amount >= 0 else "SELL",
                    "size": 0,
                    "entry_price": 0,
                    "stop_loss": 0,
                    "take_profit": 0,
                    "deal_id": trade_id or f"csv_{bot_name}_{ts.timestamp()}",
                    "status": "CLOSED",
                    "exit_price": 0,
                    "exit_timestamp": ts.isoformat(),
                    "profit_loss": amount,
                    "signal_details": f"Imported from Capital.com CSV ({bot_name})",
                    "balance_after": balance,
                })

    # Insert trades
    for t in trades:
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

    # Insert balance snapshots
    for snap in balance_snapshots:
        db.execute("""
            INSERT INTO balance_snapshots (timestamp, balance, available, profit_loss, bot_name)
            VALUES (?, ?, ?, ?, ?)
        """, (snap["timestamp"], snap["balance"], snap["available"],
              snap["profit_loss"], snap["bot_name"]))

    db.commit()

    # Summary
    wins = sum(1 for t in trades if t["profit_loss"] > 0)
    losses = sum(1 for t in trades if t["profit_loss"] < 0)
    total_pl = sum(t["profit_loss"] for t in trades)

    print(f"  Imported: {len(trades)} trades, {len(balance_snapshots)} snapshots")
    print(f"  Wins: {wins}, Losses: {losses}, Total P/L: {total_pl:.2f}")
    if skipped_rows:
        print(f"  Skipped: {len(skipped_rows)} rows:")
        for s in skipped_rows:
            print(f"    - {s}")

    db.close()


if __name__ == "__main__":
    print("Clean reimport of Capital.com CSV data")
    for imp in IMPORTS:
        clean_import(imp["csv"], imp["db"], imp["bot"], imp["skip"])
    print(f"\n{'='*60}")
    print("All imports complete!")
