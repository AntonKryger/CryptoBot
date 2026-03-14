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
            "Copy config.example.yaml to config.yaml and fill in your details."
        )
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Apply risk profile preset if specified
    profile_name = config.get("risk", {}).get("profile")
    if profile_name and profile_name in config.get("profiles", {}):
        preset = config["profiles"][profile_name]
        for key, value in preset.items():
            if key not in config["risk"] or key == "profile":
                continue
            # Only override if user hasn't set a custom value different from default
            config["risk"].setdefault(key, value)

    # Normalize exchange config: ensure 'capital' key exists for backward compatibility
    # New format uses 'exchange', legacy uses 'capital'. Both work.
    if "exchange" in config and "capital" not in config:
        ex = config["exchange"]
        config["capital"] = {
            "email": ex.get("email", ""),
            "password": ex.get("password", ""),
            "api_key": ex.get("api_key", ""),
            "demo": ex.get("demo", True),
            "account_name": ex.get("account_name"),
        }

    logger.info(f"Config loaded from {config_path}")

    # Print startup identity banner
    print_identity_banner(config, config_path)

    return config


def _get_exchange_cfg(config):
    """Get exchange credentials from new or legacy config format."""
    exchange_cfg = config.get("exchange", {})
    capital_cfg = config.get("capital", {})
    return {
        "email": exchange_cfg.get("email") or capital_cfg.get("email", "NOT SET"),
        "api_key": exchange_cfg.get("api_key") or capital_cfg.get("api_key", ""),
        "demo": exchange_cfg.get("demo", capital_cfg.get("demo", True)),
        "account_name": exchange_cfg.get("account_name") or capital_cfg.get("account_name", "default"),
        "provider": exchange_cfg.get("provider", "capital"),
    }


def print_identity_banner(config, config_path="?"):
    """Print a clear identity banner at startup so operator can verify credentials."""
    bot_cfg = config.get("bot", {})
    ex_cfg = _get_exchange_cfg(config)
    tg_cfg = config.get("telegram", {})

    bot_id = bot_cfg.get("id", "UNKNOWN")
    bot_name = bot_cfg.get("name", "Unknown Bot")
    bot_type = bot_cfg.get("type", "unknown")
    email = ex_cfg["email"]
    demo = ex_cfg["demo"]
    api_key = ex_cfg["api_key"]
    account_name = ex_cfg["account_name"]
    tg_token = tg_cfg.get("bot_token", "")

    # Create a fingerprint from credentials for quick comparison
    cred_hash = hashlib.md5(f"{email}:{api_key}".encode()).hexdigest()[:8]

    mode = "DEMO" if demo else "🔴 LIVE 🔴"

    banner = f"""
╔══════════════════════════════════════════════════╗
║  BOT IDENTITY                                    ║
╠══════════════════════════════════════════════════╣
║  Bot ID:      {bot_id:<35}║
║  Bot Name:    {bot_name:<35}║
║  Bot Type:    {bot_type:<35}║
║  Mode:        {mode:<35}║
║  Account:     {email:<35}║
║  Sub-account: {str(account_name):<35}║
║  Cred Hash:   {cred_hash:<35}║
║  Telegram:    {tg_token[-10:] if tg_token else 'DISABLED':<35}║
║  Config:      {os.path.basename(config_path):<35}║
╚══════════════════════════════════════════════════╝"""
    logger.info(banner)


def apply_profile(config, profile_name):
    """Switch risk profile at runtime."""
    # Check config-defined profiles first, then built-in defaults
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        profiles = BUILTIN_PROFILES
    if profile_name not in profiles:
        raise ValueError(f"Unknown profile: {profile_name}. Available: {list(BUILTIN_PROFILES.keys())}")

    preset = profiles[profile_name]
    config["risk"].update(preset)
    config["risk"]["profile"] = profile_name
    logger.info(f"Risk profile switched to: {profile_name}")
    return config


# 7 built-in risk profiles for variant testing
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
