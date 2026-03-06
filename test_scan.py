"""Dry-run: scan all coins for signals without trading."""

from src.config import load_config
from src.api.capital_client import CapitalClient
from src.strategy.signals import SignalEngine

config = load_config()
client = CapitalClient(config)
signals = SignalEngine(config)

print("Forbinder til Capital.com...")
client.start_session()

balance = client.get_account_balance()
print(f"Balance: EUR {balance['balance']:.2f}\n")

coins = config["trading"]["coins"]
print(f"Scanner {len(coins)} coins...\n")
print(f"{'Coin':<12} {'Pris':>12} {'EMA9':>12} {'EMA21':>12} {'RSI':>8} {'Vol Spike':>10} {'Signal':>8}")
print("-" * 76)

for epic in coins:
    try:
        prices = client.get_prices(epic, resolution="MINUTE_15", max_count=200)
        df = signals.prepare_dataframe(prices)

        if df is None or len(df) < 25:
            print(f"{epic:<12} {'Ikke nok data':>12}")
            continue

        signal, details = signals.get_signal(df)

        price = details.get("close", 0)
        ema_f = details.get("ema_fast", 0)
        ema_s = details.get("ema_slow", 0)
        rsi = details.get("rsi", 0)
        vol = "JA" if details.get("volume_spike") else "nej"

        signal_display = signal
        if signal == "BUY":
            signal_display = ">> BUY <<"
        elif signal == "SELL":
            signal_display = ">> SELL <<"

        print(f"{epic:<12} {price:>12.2f} {ema_f:>12.2f} {ema_s:>12.2f} {rsi:>8.1f} {vol:>10} {signal_display:>8}")

    except Exception as e:
        print(f"{epic:<12} FEJL: {e}")

print("\n(Dry-run - ingen handler udfoert)")
