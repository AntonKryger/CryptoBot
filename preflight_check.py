#!/usr/bin/env python3
"""
Pre-flight check: validates all bot configs before starting docker-compose.
Run this BEFORE 'docker compose up' to catch credential mismatches.

Usage: python preflight_check.py
"""

import yaml
import os
import sys
from collections import defaultdict

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

# Each bot's config.yaml path relative to project root
BOT_CONFIGS = {
    "RL1": "RuleBot/Live/RL1/config.yaml",
    "RD1": "RuleBot/Demo/RD1/config.yaml",
    "AD1": "AIBot/Demo/AD1/config.yaml",
    "SD1": "ScalpingBot/Demo/SD1/config.yaml",
    "SD2": "ScalpingBot/Demo/SD2/config.yaml",
    "AC1": "AICoach/AC1/config.yaml",
}


def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    print("=" * 60)
    print("  PREFLIGHT CHECK — Bot Credential Validation")
    print("=" * 60)

    configs = {}
    missing = []

    for bot_id, rel_path in BOT_CONFIGS.items():
        path = os.path.join(CONFIG_DIR, rel_path)
        if not os.path.exists(path):
            missing.append(f"{bot_id} ({rel_path})")
            continue
        configs[bot_id] = load_yaml(path)

    if missing:
        print(f"\n⚠️  Missing config files: {', '.join(missing)}")

    if not configs:
        print("\n❌ No config files found. Nothing to check.")
        sys.exit(1)

    # Print credential table
    print(f"\n{'Bot ID':<8} {'Type':<10} {'Mode':<6} {'Email':<35} {'API Key (last 6)':<18} {'Sub-account':<20} {'Telegram (last 10)'}")
    print("-" * 130)

    credential_map = defaultdict(list)  # "email:api_key" -> [bot_ids]

    for bot_id, cfg in sorted(configs.items()):
        bot_cfg = cfg.get("bot", {})
        cap_cfg = cfg.get("capital", {})
        tg_cfg = cfg.get("telegram", {})

        bot_type = bot_cfg.get("type", "?")
        email = cap_cfg.get("email", "NOT SET")
        api_key = cap_cfg.get("api_key", "")
        demo = "DEMO" if cap_cfg.get("demo", True) else "LIVE"
        account_name = cap_cfg.get("account_name", "-")
        tg_token = tg_cfg.get("bot_token", "")

        cred_key = f"{email}:{api_key}"
        credential_map[cred_key].append(bot_id)

        print(f"{bot_id:<8} {bot_type:<10} {demo:<6} {email:<35} ...{api_key[-6:] if api_key else 'NONE':<15} {str(account_name):<20} ...{tg_token[-10:] if tg_token else 'DISABLED'}")

    # Check for duplicates
    print("\n" + "=" * 60)
    errors = []

    for cred_key, bot_ids in credential_map.items():
        if len(bot_ids) > 1:
            email = cred_key.split(":")[0]
            sub_accounts = set()
            for bot_id, cfg in configs.items():
                if bot_id in bot_ids:
                    sub_accounts.add(cfg.get("capital", {}).get("account_name", "default"))

            if len(sub_accounts) <= 1:
                errors.append(
                    f"❌ DUPLICATE CREDENTIALS: {', '.join(bot_ids)} share the same "
                    f"Capital.com login ({email}) AND same sub-account!"
                )
            else:
                print(f"⚠️  {', '.join(bot_ids)} share login ({email}) but use different sub-accounts: {sub_accounts}")

    if errors:
        print()
        for err in errors:
            print(err)
        print(f"\n🛑 PREFLIGHT FAILED — Fix credential conflicts before starting bots!")
        sys.exit(1)
    else:
        print("\n✅ All credentials are unique or use different sub-accounts.")
        print("   Safe to start: docker compose up -d --build")
        sys.exit(0)


if __name__ == "__main__":
    main()
