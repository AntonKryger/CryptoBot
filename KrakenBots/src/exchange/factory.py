"""
Exchange adapter factory for KrakenBots.
KrakenBots only supports Kraken — this exists for interface consistency.
"""

import logging

from .base_adapter import BaseExchangeAdapter

logger = logging.getLogger(__name__)


def get_adapter(config) -> BaseExchangeAdapter:
    """Create and return the Kraken exchange adapter."""
    provider = config.get("exchange", {}).get("provider", "kraken")

    if provider != "kraken":
        raise ValueError(
            f"KrakenBots only supports Kraken exchange, got: '{provider}'"
        )

    from .kraken_adapter import KrakenAdapter
    adapter = KrakenAdapter(config)
    mode = config.get("exchange", {}).get("mode", "spot")
    logger.info(f"Exchange adapter: Kraken ({mode} mode)")
    return adapter
