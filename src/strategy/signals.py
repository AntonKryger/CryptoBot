import pandas as pd
import pandas_ta as ta
import logging

logger = logging.getLogger(__name__)


class SignalEngine:
    """Generates trading signals based on multiple technical indicators."""

    def __init__(self, config):
        signals_cfg = config.get("signals", {})
        self.ema_fast = signals_cfg.get("ema_fast", 9)
        self.ema_slow = signals_cfg.get("ema_slow", 21)
        self.rsi_period = signals_cfg.get("rsi_period", 14)
        self.rsi_overbought = signals_cfg.get("rsi_overbought", 70)
        self.rsi_oversold = signals_cfg.get("rsi_oversold", 30)
        self.volume_multiplier = signals_cfg.get("volume_multiplier", 1.5)

    def prepare_dataframe(self, prices_data):
        """Convert Capital.com price data to a pandas DataFrame with indicators."""
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

    def calculate_indicators(self, df):
        """Add all technical indicators to the dataframe."""
        # EMA
        df[f"ema_{self.ema_fast}"] = ta.ema(df["close"], length=self.ema_fast)
        df[f"ema_{self.ema_slow}"] = ta.ema(df["close"], length=self.ema_slow)

        # RSI
        df["rsi"] = ta.rsi(df["close"], length=self.rsi_period)

        # VWAP (reset each day)
        df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])

        # Volume moving average
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        df["volume_spike"] = df["volume"] > (df["volume_ma"] * self.volume_multiplier)

        # EMA crossover
        ema_fast_col = f"ema_{self.ema_fast}"
        ema_slow_col = f"ema_{self.ema_slow}"
        df["ema_bullish"] = df[ema_fast_col] > df[ema_slow_col]
        df["ema_cross_up"] = df["ema_bullish"] & ~df["ema_bullish"].shift(1).fillna(False)
        df["ema_cross_down"] = ~df["ema_bullish"] & df["ema_bullish"].shift(1).fillna(True)

        return df

    def get_signal(self, df):
        """
        Analyze the latest data and return a trading signal.
        Returns: 'BUY', 'SELL', or 'HOLD'
        """
        if df is None or len(df) < self.ema_slow + 5:
            return "HOLD", {}

        df = self.calculate_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        ema_fast_col = f"ema_{self.ema_fast}"
        ema_slow_col = f"ema_{self.ema_slow}"

        details = {
            "close": latest["close"],
            "ema_fast": latest[ema_fast_col],
            "ema_slow": latest[ema_slow_col],
            "rsi": latest["rsi"],
            "volume_spike": latest["volume_spike"],
            "vwap": latest.get("vwap"),
        }

        # ── BUY signal (long) ──
        buy_conditions = [
            latest["ema_bullish"],                          # EMA fast > slow
            latest["rsi"] < self.rsi_overbought,            # Not overbought
            latest["volume_spike"],                         # Volume confirmation
            latest["close"] > latest.get("vwap", 0),       # Price above VWAP
        ]

        # ── SELL signal (short) ──
        sell_conditions = [
            not latest["ema_bullish"],                      # EMA fast < slow
            latest["rsi"] > self.rsi_oversold,              # Not oversold
            latest["volume_spike"],                         # Volume confirmation
            latest["close"] < latest.get("vwap", float("inf")),  # Price below VWAP
        ]

        if all(buy_conditions):
            logger.info(f"BUY signal generated: {details}")
            return "BUY", details

        if all(sell_conditions):
            logger.info(f"SELL signal generated: {details}")
            return "SELL", details

        return "HOLD", details
