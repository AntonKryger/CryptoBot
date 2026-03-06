import yaml
import os
import logging

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
    return config


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
