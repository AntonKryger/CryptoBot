#!/usr/bin/env python3
"""
Nuke and reimport: Delete all trade rows and reimport from Capital.com API.
Keeps balance_snapshots intact. Creates backup before nuking.

Usage:
    python scripts/nuke_reimport_api.py --config config.yaml --db data/trades.db
    python scripts/nuke_reimport_api.py --config config_ai.yaml --db data_ai/trades.db
    python scripts/nuke_reimport_api.py --config config_demo.yaml --db data_demo/trades.db

Run on VPS after SSH:
    cd /root/cryptobot
    docker compose exec cryptobot python scripts/nuke_reimport_api.py --config config.yaml --db data/trades.db
"""

import argparse
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.api.capital_client import CapitalClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nuke_reimport")


def backup_db(db_path):
    """Create a timestamped backup of the database."""
    if not os.path.exists(db_path):
        logger.warning(f"DB not found: {db_path}, will create fresh")
        return
    backup_path = f"{db_path}.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"Backup created: {backup_path}")


def nuke_trades(db_path):
    """Delete ALL rows from trades table. Keep balance_snapshots."""
    db = sqlite3.connect(db_path)
    count = db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    db.execute("DELETE FROM trades")
    # Add source column if missing
    try:
        db.execute("ALTER TABLE trades ADD COLUMN source TEXT DEFAULT 'bot'")
    except Exception:
        pass
    db.commit()
    db.close()
    logger.info(f"Nuked {count} trades from {db_path}")


def fetch_all_transactions(client, days=90):
    """Fetch all 'Trade closed' transactions from Capital.com API.

    Returns list of dicts with keys: epic, pl, date, dealId, direction, size.
    """
    all_transactions = []

    # Fetch in 30-day windows (API limit)
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    while start < end:
        window_end = min(start + timedelta(days=30), end)
        from_date = start.strftime("%Y-%m-%dT%H:%M:%S")
        to_date = window_end.strftime("%Y-%m-%dT%H:%M:%S")

        try:
            resp = client._request("GET", "/api/v1/history/transactions", params={
                "from": from_date,
                "to": to_date,
                "maxSpanSeconds": "2592000",
            })
            transactions = resp.get("transactions", [])
            logger.info(f"Fetched {len(transactions)} transactions for {from_date[:10]} to {to_date[:10]}")

            for tx in transactions:
                if tx.get("transactionType") != "TRADE":
                    continue
                note = tx.get("note", "")
                epic = tx.get("instrumentName", "")
                deal_id = tx.get("dealId", "")
                date_utc = tx.get("dateUtc", "")
                size_val = float(tx.get("size", 0))

                if "Trade closed" in note:
                    all_transactions.append({
                        "type": "close",
                        "epic": epic,
                        "pl": size_val,  # size field contains P/L in EUR for closes
                        "date": date_utc,
                        "dealId": deal_id,
                    })
                elif "Trade opened" in note:
                    # Parse direction and size from the note or reference
                    direction = tx.get("direction", "")
                    all_transactions.append({
                        "type": "open",
                        "epic": epic,
                        "size": abs(size_val),
                        "date": date_utc,
                        "dealId": deal_id,
                        "direction": direction,
                    })

        except Exception as e:
            logger.error(f"Failed to fetch transactions for {from_date[:10]}: {e}")

        start = window_end

    return all_transactions


def match_and_insert(db_path, transactions):
    """Match open/close transactions and insert complete trade records."""
    # Separate opens and closes
    opens = [t for t in transactions if t["type"] == "open"]
    closes = [t for t in transactions if t["type"] == "close"]

    # Sort by date
    opens.sort(key=lambda x: x["date"])
    closes.sort(key=lambda x: x["date"])

    # Build close lookup by dealId
    close_by_deal = {}
    for c in closes:
        close_by_deal[c["dealId"]] = c

    # Also build close lookup by epic for fallback matching
    close_by_epic = {}
    for c in closes:
        epic = c["epic"]
        if epic not in close_by_epic:
            close_by_epic[epic] = []
        close_by_epic[epic].append(c)

    db = sqlite3.connect(db_path)

    inserted = 0
    unmatched_opens = 0

    for op in opens:
        deal_id = op["dealId"]
        epic = op["epic"]

        # Try to find matching close
        close = close_by_deal.get(deal_id)

        if not close:
            # Fallback: find first unused close for same epic after open date
            epic_closes = close_by_epic.get(epic, [])
            for c in epic_closes:
                if c.get("_used"):
                    continue
                if c["date"] >= op["date"]:
                    close = c
                    break

        if close:
            close["_used"] = True
            status = "CLOSED"
            pl = close["pl"]
            exit_ts = close["date"]
        else:
            # No matching close = still open or missed
            status = "OPEN"
            pl = None
            exit_ts = None
            unmatched_opens += 1

        # Determine direction from transaction data
        direction = op.get("direction", "")
        if not direction:
            # Try to infer: positive size usually means BUY
            direction = "BUY" if op.get("size", 0) > 0 else "SELL"

        db.execute("""
            INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                                deal_id, status, profit_loss, exit_timestamp, source)
            VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, 'api_reimport')
        """, (
            op["date"],
            epic,
            direction,
            op.get("size", 0),
            deal_id,
            status,
            pl,
            exit_ts,
        ))
        inserted += 1

    # Also insert closes that had no matching open (trades opened before our window)
    for c in closes:
        if c.get("_used"):
            continue
        db.execute("""
            INSERT INTO trades (timestamp, epic, direction, size, entry_price,
                                deal_id, status, profit_loss, exit_timestamp, source)
            VALUES (?, ?, 'UNKNOWN', 0, NULL, ?, 'CLOSED', ?, ?, 'api_reimport')
        """, (
            c["date"],
            c["epic"],
            c["dealId"],
            c["pl"],
            c["date"],
        ))
        inserted += 1

    db.commit()
    db.close()

    logger.info(f"Inserted {inserted} trades ({unmatched_opens} still open)")
    return inserted


def validate(db_path, client):
    """Compare DB total P/L with Capital.com account balance change."""
    db = sqlite3.connect(db_path)
    row = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(profit_loss), 0) FROM trades WHERE status = 'CLOSED' AND profit_loss IS NOT NULL"
    ).fetchone()
    db_count, db_total_pl = row

    # Check for duplicates
    dupes = db.execute(
        "SELECT deal_id, COUNT(*) FROM trades WHERE deal_id IS NOT NULL "
        "GROUP BY deal_id HAVING COUNT(*) > 1"
    ).fetchall()
    db.close()

    logger.info(f"DB: {db_count} closed trades, total P/L: EUR {db_total_pl:.2f}")
    if dupes:
        logger.warning(f"WARNING: {len(dupes)} duplicate deal_ids found!")
        for d in dupes[:5]:
            logger.warning(f"  deal_id={d[0]}, count={d[1]}")
    else:
        logger.info("No duplicate deal_ids found")

    # Compare with Capital.com
    try:
        balance = client.get_account_balance()
        logger.info(f"Capital.com balance: EUR {balance['balance']:.2f}")
        logger.info(f"Capital.com P/L: EUR {balance.get('profitLoss', 'N/A')}")
    except Exception as e:
        logger.warning(f"Could not fetch Capital.com balance: {e}")


def main():
    parser = argparse.ArgumentParser(description="Nuke trades DB and reimport from Capital.com API")
    parser.add_argument("--config", required=True, help="Config file (config.yaml, config_ai.yaml, etc)")
    parser.add_argument("--db", required=True, help="Database path (data/trades.db, etc)")
    parser.add_argument("--days", type=int, default=90, help="Days of history to fetch (default: 90)")
    parser.add_argument("--dry-run", action="store_true", help="Only fetch and show, don't nuke")
    args = parser.parse_args()

    config = load_config(args.config)
    client = CapitalClient(config)
    client.start_session()

    logger.info(f"Connected to Capital.com ({'DEMO' if config['capital']['demo'] else 'LIVE'})")

    # Step 1: Fetch all transactions
    logger.info(f"Fetching {args.days} days of transaction history...")
    transactions = fetch_all_transactions(client, days=args.days)
    opens = [t for t in transactions if t["type"] == "open"]
    closes = [t for t in transactions if t["type"] == "close"]
    logger.info(f"Found {len(opens)} opens, {len(closes)} closes")

    if args.dry_run:
        total_pl = sum(c["pl"] for c in closes)
        logger.info(f"DRY RUN - Total P/L from API: EUR {total_pl:.2f}")
        logger.info("Rerun without --dry-run to execute")
        return

    # Step 2: Backup
    backup_db(args.db)

    # Step 3: Nuke trades
    nuke_trades(args.db)

    # Step 4: Insert from API
    match_and_insert(args.db, transactions)

    # Step 5: Validate
    validate(args.db, client)

    logger.info("Done! Check dashboard to verify P/L matches Capital.com.")


if __name__ == "__main__":
    main()
