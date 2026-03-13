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

    logger.info(f"Config loaded from {config_path}")

    # Print startup identity banner
    print_identity_banner(config, config_path)

    return config


def print_identity_banner(config, config_path="?"):
    """Print a clear identity banner at startup so operator can verify credentials."""
    bot_cfg = config.get("bot", {})
    cap_cfg = config.get("capital", {})
    tg_cfg = config.get("telegram", {})

    bot_id = bot_cfg.get("id", "UNKNOWN")
    bot_name = bot_cfg.get("name", "Unknown Bot")
    bot_type = bot_cfg.get("type", "unknown")
    email = cap_cfg.get("email", "NOT SET")
    demo = cap_cfg.get("demo", True)
    api_key = cap_cfg.get("api_key", "")
    account_name = cap_cfg.get("account_name", "default")
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
    profiles = config.get("profiles", {})
    if profile_name not in profiles:
        raise ValueError(f"Unknown profile: {profile_name}. Available: {list(profiles.keys())}")

    preset = profiles[profile_name]
    config["risk"].update(preset)
    config["risk"]["profile"] = profile_name
    logger.info(f"Risk profile switched to: {profile_name}")
    return config
