# reset_cooldowns.py
import json, datetime, pathlib

p = pathlib.Path("bot_state.json")
if not p.exists():
    print("No bot_state.json found.")
    raise SystemExit(0)

state = json.load(p.open())
per = state.get("per_asset", {})

# Zero daily counters and wipe recency fields so trading is allowed immediately
for pid, v in per.items():
    v["trades_today"] = 0
    v["last_trade_time"] = None
    v["last_cross"] = None

# Ensure the date is today so daily reset logic won’t override your edits
state["date"] = datetime.date.today().isoformat()

json.dump(state, p.open("w"), indent=2)
print("Cooldowns cleared. Anchors preserved.")