# CLAUDE.md

## Project
Coinbase trading bot. Python, not Apps Script. Originally built Oct 2025, revived Aug 2026. The goal is a PAPER TRADING research instrument: run strategies against live market data, simulate trades honestly, and email daily results with fees, spread, and capital gains tax accounted for. The question it answers is "does any strategy actually clear its costs," not "make me money automatically."

## Scope: paper trading only in this repo
- This bot runs in PAPER / DRY_RUN mode only. It simulates trades; it does not place real orders.
- Do not add, enable, or restore live order placement. Do not flip dry_run to False. Do not write new code paths that place real orders.
- Any existing live-trading code should be disabled or removed, not activated.
- Stino may choose to pursue live trading independently in the future once a strategy is proven. That is his decision to make deliberately and elsewhere. It is not something to build, enable, or drift into as part of the work done here.
- A key purpose of this instrument is determining what minimum capital a strategy would require to overcome fees and spread. That analysis is fully in scope; executing on it is not.

## Secrets (mandatory, learned the hard way)
- A Coinbase private key was previously exposed by being backed up to Google Drive in plaintext. That key has been revoked.
- Secrets live ONLY in a local .env file and a local .pem key file. Never commit them. Never back them up to cloud storage. Never print them to logs or console.
- .gitignore already excludes .env, *.pem, *.pem.json, and secret/password patterns. Do not weaken it.
- .env.example is the committed template with placeholders only.

## Honest simulation
- Paper trading is only useful if it models reality. Fills must account for the bid/ask spread, not mid-price. Fees must be subtracted at realistic rates.
- The original strategy failed because spread ate the profits. Optimistic simulation would hide that. When in doubt, simulate pessimistically.

## Architecture notes
- threshold_bot.py is the main bot: DRY/LIVE modes, FIFO lot tracking, long/short cap gains estimates, CSV logs per tax year, email notifications.
- bot_state.json holds per-asset state: anchors, FIFO lots, strategy, trade counts. Current contents are stale (Oct 2025) and should be reset before meaningful paper runs.
- The app/ folder, Dockerfile, and Procfile are a separate FastAPI scaffold, likely vestigial. Confirm before relying on or removing.
- Intended eventual deployment: Raspberry Pi, always on.
- Long-term goal: run multiple strategies side by side for comparison. Structure changes so that stays easy to add, but do not build it prematurely.

## Environment
- Python with a local venv (not committed). Dependencies in requirements.txt.
- The Coinbase SDK version may have drifted since Oct 2025. Expect API changes and verify against current SDK before assuming code is correct.

## Working style with me
- When you find a real problem, tell me and let me decide. Do not make unrequested changes.
- Explain what you are about to change before you change it.
- Real money and real market data are involved even in paper mode. Be careful and be honest about uncertainty.
