"""Quick test: verify Capital.com API connection and fetch basic data."""

from src.config import load_config
from src.api.capital_client import CapitalClient

config = load_config()
client = CapitalClient(config)

print("Forbinder til Capital.com...")
client.start_session()
print("Session startet!\n")

# Account balance
balance = client.get_account_balance()
print(f"Balance: €{balance['balance']:.2f}")
print(f"Tilgængelig: €{balance['available']:.2f}")
print(f"P/L: €{balance['profit_loss']:.2f}\n")

# Test: fetch BTC price
print("Henter BTC prisdata...")
prices = client.get_prices("BTCUSD", resolution="MINUTE_15", max_count=5)
if prices and "prices" in prices:
    latest = prices["prices"][-1]
    bid = latest["closePrice"]["bid"]
    ask = latest["closePrice"]["ask"]
    print(f"BTC seneste pris: Bid €{bid:.2f} / Ask €{ask:.2f}")
    print(f"Antal candles hentet: {len(prices['prices'])}")
else:
    print("Kunne ikke hente prisdata - tjek epic navn")

print("\nAPI-forbindelse virker!")
