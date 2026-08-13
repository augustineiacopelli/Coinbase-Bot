import os, sys, textwrap
from dotenv import load_dotenv
from coinbase.rest import RESTClient

print("=== Coinbase Advanced Trade Debug ===")
load_dotenv()

api_key = os.getenv("COINBASE_API_KEY")
secret_path = os.getenv("COINBASE_API_SECRET_FILE")

print(f"Working dir: {os.getcwd()}")
print(f"COINBASE_API_KEY set: {bool(api_key)}")
print(f"COINBASE_API_SECRET_FILE: {secret_path}")

if not api_key or not secret_path:
    print("Missing env vars. Check your .env file location and names.")
    sys.exit(1)

if not os.path.exists(secret_path):
    print("PEM file not found at the given path. Check COINBASE_API_SECRET_FILE.")
    sys.exit(1)

with open(secret_path, "r", encoding="utf-8") as f:
    pem = f.read()

print("PEM starts correctly:", pem.strip().startswith("-----BEGIN EC PRIVATE KEY-----"))
print("PEM ends correctly:", pem.strip().endswith("-----END EC PRIVATE KEY-----"))
print("PEM newline count (should be > 2):", pem.count("\n"))

# 1) PUBLIC call (no keys)
try:
    pub_client = RESTClient()  # no auth
    p = pub_client.get_product("BTC-USD")
    print("Public BTC price OK:", p.get("price"))
except Exception as e:
    print("Public call error (unexpected):", e)

# 2) AUTH call (with keys)
try:
    priv_client = RESTClient(api_key=api_key, api_secret=pem)
    accts = priv_client.get_accounts()
    print("Authenticated accounts OK. Keys work.")
    # show just currency codes to avoid exposing balances
    d = accts.to_dict() if hasattr(accts, "to_dict") else accts
    currencies = [a.get("currency") for a in d.get("accounts", [])]
    print("Found account currencies:", currencies[:10])
except Exception as e:
    print("Authenticated call error:", e)
