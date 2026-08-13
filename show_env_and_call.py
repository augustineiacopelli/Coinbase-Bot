# show_env_and_call.py
import os
from dotenv import load_dotenv
from coinbase.rest import RESTClient

print("=== Inspect env + attempt auth ===")
load_dotenv()

api_key = os.getenv("COINBASE_API_KEY")
secret_path = os.getenv("COINBASE_API_SECRET_FILE")
print("API_KEY prefix:", (api_key or "")[:48])
print("PEM path:", secret_path)

if not api_key or not secret_path:
    raise SystemExit("Missing env vars. Check .env")

# Read the PEM exactly as the SDK will
with open(secret_path, "rb") as f:
    pem_bytes = f.read()
print("PEM bytes:", len(pem_bytes))
print("PEM head:", pem_bytes[:40])
print("PEM tail:", pem_bytes[-40:])

pem = pem_bytes.decode("utf-8")

# Try an authenticated call
try:
    c = RESTClient(api_key=api_key, api_secret=pem)
    accts = c.get_accounts()
    print("✅ Authenticated; got", len(accts.to_dict().get("accounts", [])), "accounts")
except Exception as e:
    print("❌ Auth call error:", e)
