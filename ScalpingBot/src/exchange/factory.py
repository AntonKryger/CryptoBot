"""
Exchange adapter factory.

Returns the correct adapter based on config.
Supports both new `exchange.provider` format and legacy `capital` format.
"""

import logging

from .base_adapter import BaseExchangeAdapter

logger = logging.getLogger(__name__)


def get_adapter(config) -> BaseExchangeAdapter:
    """Create and return the appropriate exchange adapter.

    Config format (new):
        exchange:
          provider: capital   # capital / binance / kraken
          api_key: ...
          api_secret: ...
          demo: true

    Legacy format (still supported):
        capital:
          email: ...
          password: ...
          api_key: ...
          demo: true
    """
    # Determine provider: new format takes precedence
    provider = config.get("exchange", {}).get("provider", "")

    if not provider:
        # Fallback: if legacy capital config exists, use capital adapter
        if "capital" in config:
            provider = "capital"
        else:
            raise ValueError(
                "No exchange configured. Set exchange.provider in config.yaml "
                "or provide legacy capital config."
            )

    provider = provider.lower()

    if provider == "capital":
        from .capital_adapter import CapitalAdapter
        adapter = CapitalAdapter(config)
        logger.info(f"Exchange adapter: Capital.com ({'demo' if adapter.demo else 'live'})")
        return adapter

    elif provider == "binance":
        from .binance_adapter import BinanceAdapter
        adapter = BinanceAdapter(config)
        logger.info("Exchange adapter: Binance (stub — not yet implemented)")
        return adapter

    elif provider == "kraken":
        from .kraken_adapter import KrakenAdapter
        adapter = KrakenAdapter(config)
        mode = config.get("exchange", {}).get("mode", "spot")
        logger.info(f"Exchange adapter: Kraken ({mode} mode)")
        return adapter

    else:
        raise ValueError(
            f"Unknown exchange provider: '{provider}'. "
            f"Supported: capital, binance, kraken"
        )
