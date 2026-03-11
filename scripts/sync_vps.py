"""
Sync trade databases from VPS to local for the dashboard.
Runs every 5 minutes in the background.
"""

import subprocess
import time
import logging
import os
import sys

# Setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(BASE_DIR, "logs", "sync_vps.log")

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("VPS-Sync")

VPS_HOST = "root@91.98.26.70"
SSH_KEY = os.path.expanduser("~/.ssh/id_ed25519")
SYNC_INTERVAL = 300  # 5 minutes

# DB paths: (VPS remote path, local path)
DB_FILES = [
    ("/root/cryptobot/data/trades.db", os.path.join(BASE_DIR, "data", "trades.db")),
    ("/root/cryptobot/data_ai/trades.db", os.path.join(BASE_DIR, "data_ai", "trades.db")),
    ("/root/cryptobot/data_demo/trades.db", os.path.join(BASE_DIR, "data_demo", "trades.db")),
]


def sync_once():
    """Download all DB files from VPS."""
    synced = 0
    for remote_path, local_path in DB_FILES:
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            result = subprocess.run(
                [
                    "scp", "-i", SSH_KEY,
                    "-o", "ConnectTimeout=10",
                    "-o", "StrictHostKeyChecking=no",
                    f"{VPS_HOST}:{remote_path}",
                    local_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                synced += 1
            else:
                logger.warning(f"SCP failed for {remote_path}: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            logger.warning(f"SCP timeout for {remote_path}")
        except Exception as e:
            logger.error(f"Sync error for {remote_path}: {e}")

    logger.info(f"Synced {synced}/{len(DB_FILES)} databases")
    return synced


def main():
    logger.info("VPS database sync started (interval: %ds)", SYNC_INTERVAL)

    while True:
        try:
            sync_once()
        except Exception as e:
            logger.error(f"Sync cycle error: {e}")

        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
