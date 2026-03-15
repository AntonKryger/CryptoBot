"""
Configuration loading for KrakenBots multi-strategy system.
Loads strategy type, risk profile, coordinator settings, etc.
"""

import yaml
import os
import logging
import hashlib

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


def load_config(path=None):
    config_path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Create a config.yaml for this bot variant."
        )
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Apply risk profile preset if specified
    profile_name = config.get("risk", {}).get("profile")
    if profile_name and profile_name in BUILTIN_PROFILES:
        preset = BUILTIN_PROFILES[profile_name]
        risk_cfg = config.setdefault("risk", {})
        for key, value in preset.items():
            risk_cfg.setdefault(key, value)

    logger.info(f"Config loaded from {config_path}")
    print_identity_banner(config, config_path)
    return config


def print_identity_banner(config, config_path="?"):
    """Print a clear identity banner at startup."""
    bot_cfg = config.get("bot", {})
    ex_cfg = config.get("exchange", {})
    tg_cfg = config.get("telegram", {})
    strategy_cfg = config.get("strategy", {})

    bot_id = bot_cfg.get("id", "UNKNOWN")
    bot_name = bot_cfg.get("name", "Unknown Bot")
    strategy_type = strategy_cfg.get("type", "unknown")
    api_key = ex_cfg.get("api_key", "")
    mode = ex_cfg.get("mode", "spot")
    demo = ex_cfg.get("demo", False)
    tg_token = tg_cfg.get("bot_token", "")

    cred_hash = hashlib.md5(f"kraken:{api_key}".encode()).hexdigest()[:8]
    mode_str = "DEMO" if demo else "LIVE"

    banner = f"""
╔══════════════════════════════════════════════════╗
║  KRAKEN BOT IDENTITY                             ║
╠══════════════════════════════════════════════════╣
║  Bot ID:      {bot_id:<35}║
║  Bot Name:    {bot_name:<35}║
║  Strategy:    {strategy_type:<35}║
║  Mode:        {mode_str} ({mode}){' ' * (28 - len(mode))}║
║  Cred Hash:   {cred_hash:<35}║
║  Telegram:    {tg_token[-10:] if tg_token else 'DISABLED':<35}║
║  Config:      {os.path.basename(config_path):<35}║
╚══════════════════════════════════════════════════╝"""
    logger.info(banner)


BUILTIN_PROFILES = {
    "ultra_conservative": {
        "stop_loss": 1.5,
        "take_profit": 3.5,
        "max_open_positions": 2,
        "daily_loss_limit": 3.0,
        "allocation": {"max_total_exposure": 10},
    },
    "conservative": {
        "stop_loss": 2.0,
        "take_profit": 5.0,
        "max_open_positions": 2,
        "daily_loss_limit": 3.0,
        "allocation": {"max_total_exposure": 30},
    },
    "balanced": {
        "stop_loss": 2.5,
        "take_profit": 5.0,
        "max_open_positions": 3,
        "daily_loss_limit": 4.0,
        "allocation": {"max_total_exposure": 50},
    },
    "moderate": {
        "stop_loss": 3.5,
        "take_profit": 6.0,
        "max_open_positions": 4,
        "daily_loss_limit": 5.0,
        "allocation": {"max_total_exposure": 70},
    },
    "moderate_aggressive": {
        "stop_loss": 4.0,
        "take_profit": 7.0,
        "max_open_positions": 5,
        "daily_loss_limit": 5.0,
        "allocation": {"max_total_exposure": 80},
    },
    "aggressive": {
        "stop_loss": 5.0,
        "take_profit": 10.0,
        "max_open_positions": 6,
        "daily_loss_limit": 7.0,
        "allocation": {"max_total_exposure": 90},
    },
    "ultra_aggressive": {
        "stop_loss": 6.0,
        "take_profit": 12.0,
        "max_open_positions": 8,
        "daily_loss_limit": 10.0,
        "allocation": {"max_total_exposure": 95},
    },
}
