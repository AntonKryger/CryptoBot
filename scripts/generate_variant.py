#!/usr/bin/env python3
"""
Variant Generator — reads variants.yaml and generates:
1. Per-variant config.yaml files (deep-merged from template + overrides)
2. docker-compose.generated.yml with all active variants
3. Auto-calculated scan_offset_seconds per variant

Usage:
    python scripts/generate_variant.py                      # generate all active
    python scripts/generate_variant.py --batch A             # only batch A
    python scripts/generate_variant.py --variant RD2         # only RD2
    python scripts/generate_variant.py --dry-run             # show what would be generated
"""

import argparse
import copy
import math
import os
import sys

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Bot type → directory mapping
TYPE_DIRS = {
    "rule": "RuleBot",
    "scalper": "ScalpingBot",
    "ai": "AIBot",
    "coach": "AICoach",
}

# Bot type → template config file
TYPE_TEMPLATES = {
    "rule": "RuleBot/config.example.yaml",
    "scalper": "ScalpingBot/config.example.yaml",
    "ai": "AIBot/config.example.yaml",
    "coach": "AICoach/config.example.yaml",
}

# Coach type → subdirectory mapping
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


def load_variants_yaml():
    path = os.path.join(PROJECT_ROOT, "variants.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def load_template(bot_type):
    template_path = os.path.join(PROJECT_ROOT, TYPE_TEMPLATES[bot_type])
    if not os.path.exists(template_path):
        print(f"  WARNING: Template not found: {template_path}")
        return {}
    with open(template_path) as f:
        return yaml.safe_load(f)


def deep_merge(base, override):
    """Deep merge override into base. Override wins on conflicts."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def apply_dotted_overrides(config, overrides):
    """Apply dotted key overrides like 'risk.stop_loss: 3.5' to nested config."""
    for dotted_key, value in overrides.items():
        parts = dotted_key.split(".")
        target = config
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value
    return config


def apply_profile_to_config(config, profile_name, profiles):
    """Apply profile preset values to config risk section."""
    if profile_name not in profiles:
        return config
    preset = profiles[profile_name]
    if "risk" not in config:
        config["risk"] = {}
    for key, value in preset.items():
        if key == "min_rr_ratio":
            # min_rr_ratio goes under trading, not risk
            config.setdefault("trading", {})["min_rr_ratio"] = value
        elif key == "circuit_breaker_losses":
            config.setdefault("trading", {})["circuit_breaker_losses"] = value
        else:
            config["risk"][key] = value
    config["risk"]["profile"] = profile_name
    return config


def get_variant_dir(variant_id, variant_cfg):
    """Get the directory path for a variant."""
    bot_type = variant_cfg["type"]
    if bot_type == "coach":
        coach_for = variant_cfg.get("coach_for", "ai")
        type_dir = TYPE_DIRS["coach"]
        sub_path = COACH_DIRS.get(coach_for, variant_id)
        return os.path.join(PROJECT_ROOT, type_dir, sub_path)
    else:
        type_dir = TYPE_DIRS[bot_type]
        sub_path = VARIANT_PATHS.get(variant_id, f"Demo/{variant_id}")
        return os.path.join(PROJECT_ROOT, type_dir, sub_path)


def calculate_scan_offsets(variants):
    """Distribute API calls evenly across scan interval."""
    # Group by type (each type has its own API session)
    by_type = {}
    for vid, vcfg in variants.items():
        if vcfg.get("type") == "coach":
            continue
        t = vcfg["type"]
        by_type.setdefault(t, []).append(vid)

    offsets = {}
    for bot_type, variant_ids in by_type.items():
        n = len(variant_ids)
        interval = 300  # default scan_interval
        step = interval / max(n, 1)
        for i, vid in enumerate(sorted(variant_ids)):
            offsets[vid] = round(i * step)
    return offsets


def generate_config(variant_id, variant_cfg, profiles, scan_offsets, dry_run=False):
    """Generate config.yaml for a single variant."""
    bot_type = variant_cfg["type"]

    if bot_type == "coach":
        # Coaches have simpler configs
        return generate_coach_config(variant_id, variant_cfg, dry_run)

    template = load_template(bot_type)
    if not template:
        return None

    config = copy.deepcopy(template)

    # Set bot identity
    config.setdefault("bot", {})
    config["bot"]["id"] = variant_id
    mode = variant_cfg.get("mode", "demo")
    bot_type_name = {"rule": "Rule Bot", "scalper": "Scalper Bot", "ai": "AI Bot"}
    mode_label = "Live" if mode == "live" else "Demo"
    num = variant_id[-1] if variant_id[-1].isdigit() else "1"
    config["bot"]["name"] = f"{bot_type_name.get(bot_type, 'Bot')} {mode_label} {num:>02}"
    config["bot"]["type"] = bot_type

    # Set exchange/demo mode (support both new and legacy format)
    if "exchange" in config:
        config["exchange"]["demo"] = mode != "live"
        config["exchange"]["account_name"] = variant_id
    else:
        config.setdefault("capital", {})
        config["capital"]["demo"] = mode != "live"
        config["capital"]["account_name"] = variant_id

    # Set coins
    if "coins" in variant_cfg:
        config.setdefault("trading", {})["coins"] = variant_cfg["coins"]

    # Apply profile
    profile = variant_cfg.get("profile", "moderate")
    config = apply_profile_to_config(config, profile, profiles)

    # Apply dotted overrides (these take precedence over profile)
    overrides = variant_cfg.get("overrides", {})
    if overrides:
        config = apply_dotted_overrides(config, overrides)

    # Apply scan offset
    if variant_id in scan_offsets:
        config.setdefault("trading", {})["scan_offset_seconds"] = scan_offsets[variant_id]

    # Write config
    variant_dir = get_variant_dir(variant_id, variant_cfg)
    config_path = os.path.join(variant_dir, "config.yaml")

    if dry_run:
        print(f"  [DRY-RUN] Would write: {config_path}")
        return config

    os.makedirs(variant_dir, exist_ok=True)
    os.makedirs(os.path.join(variant_dir, "data"), exist_ok=True)
    os.makedirs(os.path.join(variant_dir, "logs"), exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"  Generated: {os.path.relpath(config_path, PROJECT_ROOT)}")
    return config


def generate_coach_config(variant_id, variant_cfg, dry_run=False):
    """Generate config for a coach variant."""
    coach_for = variant_cfg.get("coach_for", "ai")
    template = load_template("coach")
    config = copy.deepcopy(template) if template else {}

    config.setdefault("bot", {})
    config["bot"]["id"] = variant_id
    coach_names = {
        "ai": "AI Coach",
        "rule": "Rule Coach",
        "scalper": "Scalp Coach",
        "master": "Master Coach",
    }
    config["bot"]["name"] = f"{coach_names.get(coach_for, 'Coach')} 01"
    config["bot"]["type"] = "coach"

    # Coach-specific config
    config["coach"] = {
        "type": coach_for,
        "analysis_days": 30 if coach_for != "master" else 14,
        "schedule": "daily" if coach_for != "master" else "weekly",
    }

    variant_dir = get_variant_dir(variant_id, variant_cfg)
    config_path = os.path.join(variant_dir, "config.yaml")

    if dry_run:
        print(f"  [DRY-RUN] Would write: {config_path}")
        return config

    os.makedirs(variant_dir, exist_ok=True)
    os.makedirs(os.path.join(variant_dir, "data"), exist_ok=True)
    os.makedirs(os.path.join(variant_dir, "logs"), exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"  Generated: {os.path.relpath(config_path, PROJECT_ROOT)}")
    return config


def generate_docker_compose(variants, profiles):
    """Generate docker-compose.generated.yml for all active variants."""
    services = {}

    # Group trading bots by type for shared build context
    for variant_id, vcfg in sorted(variants.items()):
        if vcfg.get("status") != "active":
            continue

        bot_type = vcfg["type"]
        service_name = variant_id.lower()

        if bot_type == "coach":
            coach_for = vcfg.get("coach_for", "ai")
            type_dir = TYPE_DIRS["coach"]
            sub_path = COACH_DIRS.get(coach_for, variant_id)
            variant_dir = f"./{type_dir}/{sub_path}"

            service = {
                "build": {"context": f"./{type_dir}"},
                "container_name": f"cryptobot-{service_name}",
                "restart": "always",
                "volumes": [
                    f"{variant_dir}/config.yaml:/app/config.yaml:ro",
                    f"{variant_dir}/data:/app/data",
                    f"{variant_dir}/logs:/app/logs",
                ],
            }

            # Mount bot data directories for coaches to read
            if coach_for == "master":
                # Master coach reads from all other coaches
                for other_id, other_cfg in variants.items():
                    if other_cfg["type"] == "coach" and other_cfg.get("coach_for") != "master":
                        other_dir = get_variant_dir(other_id, other_cfg)
                        rel = os.path.relpath(other_dir, PROJECT_ROOT).replace("\\", "/")
                        service["volumes"].append(
                            f"./{rel}/data:/app/coach_data/{other_id.lower()}:ro"
                        )
            else:
                # Type-specific coaches read their bot type's data
                for other_id, other_cfg in variants.items():
                    if other_cfg["type"] != "coach" and other_cfg.get("type") == coach_for:
                        other_dir = get_variant_dir(other_id, other_cfg)
                        rel = os.path.relpath(other_dir, PROJECT_ROOT).replace("\\", "/")
                        service["volumes"].append(
                            f"./{rel}/data:/app/bot_data/{other_id.lower()}:ro"
                        )

        else:
            type_dir = TYPE_DIRS[bot_type]
            sub_path = VARIANT_PATHS.get(variant_id, f"Demo/{variant_id}")
            variant_dir = f"./{type_dir}/{sub_path}"

            service = {
                "build": {"context": f"./{type_dir}"},
                "container_name": f"cryptobot-{service_name}",
                "restart": "always",
                "volumes": [
                    f"{variant_dir}/config.yaml:/app/config.yaml:ro",
                    f"{variant_dir}/data:/app/data",
                    f"{variant_dir}/logs:/app/logs",
                ],
            }

        services[service_name] = service

    # Add dashboard service (always uses RuleBot build context)
    services["dashboard"] = {
        "build": {"context": "./RuleBot"},
        "container_name": "cryptobot-dashboard",
        "restart": "always",
        "command": [
            "gunicorn", "--bind", "0.0.0.0:5000",
            "--workers", "2", "--timeout", "30",
            "dashboard:app",
        ],
        "ports": ["0.0.0.0:5000:5000"],
        "environment": [
            "BOT_DATA_DIR=/app/bot_data",
        ],
        "volumes": [],
    }

    # Mount all trading bot data dirs to dashboard
    for variant_id, vcfg in sorted(variants.items()):
        if vcfg.get("status") != "active" or vcfg["type"] == "coach":
            continue
        vdir = get_variant_dir(variant_id, vcfg)
        rel = os.path.relpath(vdir, PROJECT_ROOT).replace("\\", "/")
        services["dashboard"]["volumes"].append(
            f"./{rel}/data:/app/bot_data/{variant_id.lower()}:ro"
        )

    compose = {"services": services}

    output_path = os.path.join(PROJECT_ROOT, "docker-compose.generated.yml")
    with open(output_path, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\n  Generated: docker-compose.generated.yml ({len(services)} services)")
    return compose


def main():
    parser = argparse.ArgumentParser(description="Generate variant configs + docker-compose")
    parser.add_argument("--batch", help="Only generate variants from this batch")
    parser.add_argument("--variant", help="Only generate a specific variant ID")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--no-compose", action="store_true", help="Skip docker-compose generation")
    args = parser.parse_args()

    data = load_variants_yaml()
    profiles = data.get("profiles", {})
    all_variants = data.get("variants", {})

    # Filter variants
    variants = {}
    for vid, vcfg in all_variants.items():
        if args.variant and vid != args.variant:
            continue
        if args.batch and vcfg.get("batch") != args.batch:
            continue
        if vcfg.get("status") != "active":
            continue
        variants[vid] = vcfg

    if not variants:
        print("No matching active variants found.")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print(f"  VARIANT GENERATOR — {len(variants)} variants")
    print(f"{'=' * 60}")

    # Calculate scan offsets for all active variants (not just filtered)
    all_active = {vid: vcfg for vid, vcfg in all_variants.items() if vcfg.get("status") == "active"}
    scan_offsets = calculate_scan_offsets(all_active)

    # Generate configs
    print("\n  Generating configs...")
    for vid, vcfg in sorted(variants.items()):
        generate_config(vid, vcfg, profiles, scan_offsets, dry_run=args.dry_run)

    # Generate docker-compose (always uses all active variants)
    if not args.no_compose and not args.dry_run:
        print("\n  Generating docker-compose...")
        generate_docker_compose(all_active, profiles)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Scan offsets (seconds):")
    for vid, offset in sorted(scan_offsets.items()):
        if vid in variants:
            print(f"    {vid}: {offset}s")
    print(f"{'=' * 60}")
    print(f"\n  Next steps:")
    print(f"    1. Fill in Capital.com credentials in each config.yaml")
    print(f"    2. python preflight_check.py")
    print(f"    3. docker compose -f docker-compose.generated.yml up -d --build")
    print()


if __name__ == "__main__":
    main()
