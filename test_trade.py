"""Test: open a single XRP position (1 unit) on demo account."""

from src.config import load_config
from src.api.capital_client import CapitalClient

config = load_config()
client = CapitalClient(config)

print("Forbinder til Capital.com...")
client.start_session()

balance = client.get_account_balance()
print(f"Balance foer: EUR {balance['balance']:.2f}\n")

# Get current XRP price
prices = client.get_prices("XRPUSD", resolution="MINUTE_15", max_count=1)
latest = prices["prices"][-1]
bid = latest["closePrice"]["bid"]
ask = latest["closePrice"]["ask"]
print(f"XRP pris: Bid {bid} / Ask {ask}\n")

# Open BUY position: 1 XRP
print("Aabner position: BUY 1 XRPUSD...")
try:
    result = client.create_position(
        epic="XRPUSD",
        direction="BUY",
        size=1,
    )
    print(f"Resultat: {result}")
except Exception as e:
    print(f"Fejl: {e}")

# Check positions
print("\nAabne positioner:")
positions = client.get_positions()
for pos in positions.get("positions", []):
    epic = pos["market"]["epic"]
    direction = pos["position"]["direction"]
    size = pos["position"]["size"]
    print(f"  {epic}: {direction} x{size}")

balance = client.get_account_balance()
print(f"\nBalance efter: EUR {balance['balance']:.2f}")
