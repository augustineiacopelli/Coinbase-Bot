# reset_state.py
"""
Safely reset your trading bot state between tests.

What this does (per asset):
- anchor = None
- last_cross = None
- last_trade_time = None
- trades_today = 0
- (keeps) strategy, strategy_since, pos_base, avg_cost, last_buy_ts

Usage (from the bot folder):
  (venv) PS C:\path\to\coinbase_always_on_bot> python .\reset_state.py
  # or specify a custom state file
  (venv) PS ...> python .\reset_state.py --state bot_state.json
"""

import json
import os
import argparse
from datetime import datetime

DEFAULT_STATE_FILE = "bot_state.json"

def load_state(path: str):
    if not os.path.exists(path):
        return {"per_asset": {}, "date": datetime.utcnow().date().isoformat()}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(path: str, state: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def reset_state(path: str):
    state = load_state(path)
    per_asset = state.get("per_asset", {})
    if not isinstance(per_asset, dict):
        per_asset = {}
        state["per_asset"] = per_asset

    affected = 0
    for pid, per in per_asset.items():
        if not isinstance(per, dict):
            continue
        per["anchor"] = None
        per["last_cross"] = None
        per["last_trade_time"] = None
        per["trades_today"] = 0
        # preserve strategy fields and inventory fields
        per.setdefault("strategy", "threshold")
        per.setdefault("strategy_since", datetime.utcnow().isoformat())
        per.setdefault("pos_base", 0.0)
        per.setdefault("avg_cost", 0.0)
        per.setdefault("last_buy_ts", None)
        affected += 1

    # reset current date to today so a fresh trading day begins
    state["date"] = datetime.utcnow().date().isoformat()
    save_state(path, state)
    print(f"[RESET OK] Cleared anchors/cooldowns for {affected} assets in '{path}'.")
    return affected

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", dest="state_file", default=DEFAULT_STATE_FILE, help="Path to state file (default bot_state.json)")
    args = ap.parse_args()
    path = args.state_file
    count = reset_state(path)
    if count == 0:
        print("[NOTE] No assets found. If this is unexpected, confirm you're running from the same folder as threshold_bot.py.")

if __name__ == "__main__":
    main()
