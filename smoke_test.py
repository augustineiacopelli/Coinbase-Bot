# smoke_test.py
import os
from dotenv import load_dotenv
from coinbase.rest import RESTClient

# Load environment variables from .env
load_dotenv()

api_key = os.getenv("COINBASE_API_KEY")
secret_path = os.getenv("COINBASE_API_SECRET_FILE")

# Read the PEM private key file
with open(secret_path, "r", encoding="utf-8") as f:
    api_secret = f.read()

# Initialize the Coinbase REST client
client = RESTClient(api_key=api_key, api_secret=api_secret)

print("=== Testing Coinbase API Connection ===")

# Check account access
try:
    accounts = client.get_accounts()
    print("✅ Accounts retrieved successfully.")
    print(accounts.to_dict() if hasattr(accounts, "to_dict") else accounts)
except Exception as e:
    print("❌ Error getting accounts:", e)

# Check public market data
try:
    btc = client.get_product("BTC-USD")
    print("✅ BTC-USD price:", btc.get("price"))
except Exception as e:
    print("❌ Error getting BTC price:", e)
