# quick_check.py (fixed)
from dotenv import load_dotenv
import os
from coinbase.rest import RESTClient

load_dotenv()
with open(os.getenv("COINBASE_API_SECRET_FILE"), "r", encoding="utf-8") as f:
    pem = f.read()

c = RESTClient(api_key=os.getenv("COINBASE_API_KEY"), api_secret=pem)

# Accounts / balances
accts = c.get_accounts().to_dict()["accounts"]
print("Accounts:", [(a["currency"], a["available_balance"]["value"]) for a in accts])

# Safe helper to read product price from SDK object or dict
def price_of(pid: str) -> str:
    resp = c.get_product(pid)
    if hasattr(resp, "to_dict"):
        return resp.to_dict().get("price")
    # some versions expose attributes directly
    return getattr(resp, "price", None)

for pid in ["BTC-USD", "ETH-USD"]:
    print(pid, "price:", price_of(pid))