#!/usr/bin/env python3
"""
Pre-flight check: validates all bot configs before starting docker-compose.
Run this BEFORE 'docker compose up' to catch credential mismatches.

Supports both legacy paths and new hybrid architecture.
Can also read from variants.yaml for auto-discovery.

Usage: python preflight_check.py
"""

import yaml
import os
import sys
from collections import defaultdict

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

# Type directory mapping (hybrid architecture)
TYPE_DIRS = {
    "rule": "RuleBot",
    "scalper": "ScalpingBot",
    "ai": "AIBot",
    "coach": "AICoach",
}

# Coach subdirectory mapping
COACH_DIRS = {
    "ai": "AC1",
    "rule": "RuleCoach/RC1",
    "scalper": "ScalpCoach/SC1",
    "master": "MasterCoach/MC1",
}

# Variant ID → path within type directory
VARIANT_PATHS = {
    "RL1": "Live/RL1",
    "RD1": "Demo/RD1",
    "RD2": "Demo/RD2",
    "RD3": "Demo/RD3",
    "SD1": "Demo/SD1",
    "SD2": "Demo/SD2",
    "SD3": "Demo/SD3",
    "SD4": "Demo/SD4",
    "AD1": "Demo/AD1",
    "AD2": "Demo/AD2",
    "AC1": "AC1",
    "RC1": "RuleCoach/RC1",
    "SC1": "ScalpCoach/SC1",
    "MC1": "MasterCoach/MC1",
}


def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def discover_configs():
    """Discover bot configs from variants.yaml or fallback to known paths."""
    configs = {}

    # Try variants.yaml first
    variants_path = os.path.join(CONFIG_DIR, "variants.yaml")
    if os.path.exists(variants_path):
        data = load_yaml(variants_path)
        variants = data.get("variants", {})
        for variant_id, vcfg in variants.items():
            if vcfg.get("status") != "active":
                continue
            bot_type = vcfg.get("type", "rule")

            if bot_type == "coach":
                coach_for = vcfg.get("coach_for", "ai")
                type_dir = TYPE_DIRS.get("coach", "AICoach")
                sub_path = COACH_DIRS.get(coach_for, variant_id)
            else:
                type_dir = TYPE_DIRS.get(bot_type, "RuleBot")
                sub_path = VARIANT_PATHS.get(variant_id, f"Demo/{variant_id}")

            config_path = os.path.join(CONFIG_DIR, type_dir, sub_path, "config.yaml")
            if os.path.exists(config_path):
                configs[variant_id] = load_yaml(config_path)

    # Fallback: scan known legacy paths
    if not configs:
        legacy_paths = {
            "RL1": "RuleBot/Live/RL1/config.yaml",
            "RD1": "RuleBot/Demo/RD1/config.yaml",
            "AD1": "AIBot/Demo/AD1/config.yaml",
            "SD1": "ScalpingBot/Demo/SD1/config.yaml",
            "SD2": "ScalpingBot/Demo/SD2/config.yaml",
            "AC1": "AICoach/AC1/config.yaml",
        }
        for bot_id, rel_path in legacy_paths.items():
            path = os.path.join(CONFIG_DIR, rel_path)
            if os.path.exists(path):
                configs[bot_id] = load_yaml(path)

    return configs


def main():
    print("=" * 70)
    print("  PREFLIGHT CHECK — Bot Credential & Exchange Validation")
    print("=" * 70)

    configs = discover_configs()

    if not configs:
        print("\n[X] No config files found. Nothing to check.")
        sys.exit(1)

    print(f"\n  Found {len(configs)} bot configs")

    # Print credential table
    print(f"\n{'Bot ID':<8} {'Type':<10} {'Exchange':<12} {'Mode':<6} {'Identifier':<35} {'API Key (last 6)':<18} {'Account':<15}")
    print("-" * 110)

    credential_map = defaultdict(list)  # "provider:identifier:api_key" -> [bot_ids]

    for bot_id, cfg in sorted(configs.items()):
        bot_cfg = cfg.get("bot", {})
        ex_cfg = cfg.get("exchange", {})
        cap_cfg = cfg.get("capital", {})

        bot_type = bot_cfg.get("type", "?")
        provider = ex_cfg.get("provider", "capital" if cap_cfg else "?").upper()

        if provider == "KRAKEN":
            identifier = ex_cfg.get("api_key", "NOT SET")[:20] + "..."
            api_key = ex_cfg.get("api_key", "")
            mode = ex_cfg.get("mode", "spot").upper()
            account_name = ex_cfg.get("mode", "spot")
        else:
            identifier = ex_cfg.get("email") or cap_cfg.get("email", "NOT SET")
            api_key = ex_cfg.get("api_key") or cap_cfg.get("api_key", "")
            mode = "DEMO" if ex_cfg.get("demo", cap_cfg.get("demo", True)) else "LIVE"
            account_name = ex_cfg.get("account_name") or cap_cfg.get("account_name", "-")

        cred_key = f"{provider}:{api_key}"
        credential_map[cred_key].append(bot_id)

        print(
            f"{bot_id:<8} {bot_type:<10} {provider:<12} {mode:<6} "
            f"{str(identifier)[:35]:<35} ...{api_key[-6:] if api_key else 'NONE':<15} "
            f"{str(account_name):<15}"
        )

    # Check for duplicates
    print("\n" + "=" * 70)
    errors = []
    warnings = []

    for cred_key, bot_ids in credential_map.items():
        provider = cred_key.split(":")[0]

        if len(bot_ids) > 1:
            if provider == "KRAKEN":
                # Kraken: same API key for multiple bots is OK (no sub-accounts)
                warnings.append(
                    f"[!] {', '.join(bot_ids)} share the same Kraken API key -- "
                    f"ensure they trade different coins to avoid conflicts"
                )
            else:
                # Capital.com: check sub-accounts
                sub_accounts = set()
                for bot_id in bot_ids:
                    c = configs[bot_id]
                    acct = (c.get("exchange", {}).get("account_name")
                            or c.get("capital", {}).get("account_name", "default"))
                    sub_accounts.add(acct)

                if len(sub_accounts) <= 1:
                    errors.append(
                        f"[X] DUPLICATE CREDENTIALS: {', '.join(bot_ids)} share the same "
                        f"Capital.com login AND same sub-account!"
                    )
                else:
                    warnings.append(
                        f"[!] {', '.join(bot_ids)} share login but use different "
                        f"sub-accounts: {sub_accounts}"
                    )

    for w in warnings:
        print(w)

    if errors:
        print()
        for err in errors:
            print(err)
        print(f"\n[FAIL] PREFLIGHT FAILED -- Fix credential conflicts before starting bots!")
        sys.exit(1)
    else:
        print(f"\n[OK] All credentials validated. {len(configs)} bots ready.")
        print("   Safe to start: docker compose up -d --build")
        sys.exit(0)


if __name__ == "__main__":
    main()
