"""
Abstract base class for all KrakenBot strategies.

Each strategy implements its own scan logic but shares the same
adapter, risk manager, and execution pipeline.
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Interface that every strategy must implement."""

    def __init__(self, config):
        self.config = config
        self.strategy_cfg = config.get("strategy", {})
        self.strategy_type = self.strategy_cfg.get("type", "unknown")

        # Set externally by main_kraken.py after init
        self.client = None          # Exchange adapter
        self.risk_manager = None    # Risk manager
        self.coordinator = None     # Bot coordinator
        self.notifier = None        # Telegram notifier

    @abstractmethod
    def scan(self, epic: str, prices_data: dict) -> Optional[dict]:
        """Analyze price data and return a trade signal or None.

        Args:
            epic: Instrument identifier (e.g., "BTC/USD")
            prices_data: Raw price data from adapter.get_prices()

        Returns:
            None if no trade signal, or a dict:
            {
                "direction": "BUY" or "SELL",
                "epic": str,
                "confidence": int (1-10),
                "entry_price": float,
                "stop_loss": float,
                "take_profit": float,
                "size": float (optional, strategy can suggest),
                "signal_type": str (e.g., "GRID_BUY", "TREND_LONG"),
                "reasons": list[str],
                "details": dict (strategy-specific data),
            }
        """

    @abstractmethod
    def on_position_opened(self, position_info: dict):
        """Called when a position is opened by this strategy.
        Allows strategies to update internal state (e.g., grid levels).
        """

    @abstractmethod
    def on_position_closed(self, position_info: dict, exit_price: float, profit_loss: float):
        """Called when a position is closed.
        Allows strategies to react (e.g., place next grid order).
        """

    @abstractmethod
    def get_active_regime(self) -> str:
        """Return the market regime this strategy is designed for.
        Used by coordinator to decide which bots are active.

        Returns: "RANGING", "TRENDING", "VOLATILE", or "ANY"
        """

    @abstractmethod
    def should_be_active(self, regime: str, adx: float) -> bool:
        """Check if this strategy should be active in the current market regime.

        Args:
            regime: Current market regime (RANGING, TRENDING_UP, TRENDING_DOWN, NEUTRAL)
            adx: Current ADX value

        Returns: True if strategy should scan for signals
        """

    def prepare_dataframe(self, prices_data: dict) -> Optional[pd.DataFrame]:
        """Convert adapter price data to pandas DataFrame with OHLCV columns."""
        candles = prices_data.get("prices", [])
        if not candles:
            return None

        rows = []
        for c in candles:
            rows.append({
                "timestamp": c["snapshotTime"],
                "open": (c["openPrice"]["bid"] + c["openPrice"]["ask"]) / 2,
                "high": (c["highPrice"]["bid"] + c["highPrice"]["ask"]) / 2,
                "low": (c["lowPrice"]["bid"] + c["lowPrice"]["ask"]) / 2,
                "close": (c["closePrice"]["bid"] + c["closePrice"]["ask"]) / 2,
                "volume": c.get("lastTradedVolume", 0),
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        return df

    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ADX(14) from DataFrame. Used by regime detection."""
        if len(df) < period * 2:
            return 0.0

        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        plus_dm = []
        minus_dm = []
        tr_list = []

        for i in range(1, len(highs)):
            high_diff = highs[i] - highs[i - 1]
            low_diff = lows[i - 1] - lows[i]

            pdm = high_diff if high_diff > low_diff and high_diff > 0 else 0
            mdm = low_diff if low_diff > high_diff and low_diff > 0 else 0

            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )

            plus_dm.append(pdm)
            minus_dm.append(mdm)
            tr_list.append(tr)

        if len(tr_list) < period:
            return 0.0

        smooth_plus_dm = sum(plus_dm[:period])
        smooth_minus_dm = sum(minus_dm[:period])
        smooth_tr = sum(tr_list[:period])

        dx_values = []
        for i in range(period, len(tr_list)):
            smooth_plus_dm = smooth_plus_dm - (smooth_plus_dm / period) + plus_dm[i]
            smooth_minus_dm = smooth_minus_dm - (smooth_minus_dm / period) + minus_dm[i]
            smooth_tr = smooth_tr - (smooth_tr / period) + tr_list[i]

            if smooth_tr == 0:
                continue

            plus_di = 100 * smooth_plus_dm / smooth_tr
            minus_di = 100 * smooth_minus_dm / smooth_tr

            di_sum = plus_di + minus_di
            if di_sum == 0:
                continue

            dx = 100 * abs(plus_di - minus_di) / di_sum
            dx_values.append(dx)

        if len(dx_values) < period:
            return 0.0

        return sum(dx_values[-period:]) / period

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate current ATR value."""
        if len(df) < period + 1:
            return 0.0

        tr_values = []
        for i in range(1, len(df)):
            h = df["high"].iloc[i]
            l = df["low"].iloc[i]
            c_prev = df["close"].iloc[i - 1]
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_values.append(tr)

        if len(tr_values) < period:
            return 0.0

        # Wilder's smoothed ATR
        atr = sum(tr_values[:period]) / period
        for i in range(period, len(tr_values)):
            atr = (atr * (period - 1) + tr_values[i]) / period

        return atr

    def calculate_atr_pct(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR as percentage of current price."""
        atr = self.calculate_atr(df, period)
        if atr == 0 or len(df) == 0:
            return 0.0
        return (atr / df["close"].iloc[-1]) * 100
