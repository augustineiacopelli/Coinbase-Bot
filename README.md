# Coinbase Trading Bot — Paper Trading Research Instrument

**This repo runs in PAPER TRADING mode only. It does not place real orders and never will as part of this codebase.**

The question this project answers is: *does any strategy actually clear its costs* — fees, bid/ask spread, and capital gains tax — not "make me money automatically." A key output is the minimum capital a strategy would need to overcome those costs, if any amount is enough at all.

## What's here

- **`threshold_bot.py`** — the main bot. Runs against live Coinbase market data, simulates fills honestly (spread-aware, fees deducted), tracks FIFO lots for long/short capital gains estimates, logs every simulated trade to a per-tax-year CSV, and can email daily results.
- **`bot_state.json`** — per-asset state (anchors, FIFO lots, strategy assignment, trade counts). Reset before any meaningful paper run; see `reset_state.py`.
- **`setup_instructions_and_requirements.txt`** — install steps, `.env` template, and a post-install test checklist.
- **`app/`, `Dockerfile`, `Procfile`** — a separate FastAPI price-service scaffold (health check, price lookup, watchlist, an OpenAI chat endpoint). It is not the trading bot and is likely vestigial; confirm before relying on or removing it.

## Setup

See `setup_instructions_and_requirements.txt` for full install and run instructions. In short:

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # fill in your keys
python -u .\threshold_bot.py
```

## Secrets

Secrets live only in a local `.env` file and a local `.pem` key file. Never commit them, never back them up to cloud storage, never print them to logs or console. `.gitignore` excludes `.env`, `*.pem`, `*.pem.json`, and secret/password patterns — don't weaken it.

## Scope

This bot simulates trades against live market data; it does not place real orders. Fills model the bid/ask spread rather than the mid-price, and fees are deducted at realistic rates, because an optimistic simulation would hide the exact failure mode that sank the original version of this bot: spread eating the profits. Live order placement is out of scope for this repo — see `CLAUDE.md` for the full working constraints.
