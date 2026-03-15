from .base_strategy import BaseStrategy
from .grid_trader import GridTrader
from .trend_follower import TrendFollower
from .mean_reverter import MeanReverter
from .volatility_trader import VolatilityTrader

STRATEGY_MAP = {
    "grid": GridTrader,
    "trend": TrendFollower,
    "mean_reversion": MeanReverter,
    "volatility": VolatilityTrader,
}


def get_strategy(config):
    """Create and return the appropriate strategy based on config."""
    strategy_type = config.get("strategy", {}).get("type", "trend")
    cls = STRATEGY_MAP.get(strategy_type)
    if cls is None:
        raise ValueError(
            f"Unknown strategy type: '{strategy_type}'. "
            f"Supported: {list(STRATEGY_MAP.keys())}"
        )
    return cls(config)
