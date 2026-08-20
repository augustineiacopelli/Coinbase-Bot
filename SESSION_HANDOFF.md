# SESSION HANDOFF — coinbase-bot

Written 2026-08-20. Source: planning session in Claude chat. Execution moves to Claude Code in VS Code.

Read CLAUDE.md first. It is authoritative. This file is the work queue.

---

## Scope reminder (non-negotiable)

This repo is a PAPER TRADING research instrument. It never places live orders. Do not enable, restore, or write code paths that place real orders. Do not set `dry_run` to False. If a task in this file appears to conflict with that, stop and ask Stino.

---

## State as of this handoff

Two commits exist on `main`:

```
83547d3 Added CLAUDE.md file to git.
7e2fa2c Initial commit: Coinbase trading bot from Drive backup
```

No remote is configured yet. Git history has been audited: no `.env`, no `.pem`, and no credential file was ever committed. Every committed Python file reads credentials from the environment. The repo is safe to push to a private GitHub remote.

Nothing from the audit has been fixed yet. Every item below is still open.

---

## Working discipline (hold to this)

1. Investigate before editing. Read the surrounding code, do not pattern match.
2. Explain what you are about to change before changing it. Wait for Stino's go ahead.
3. One logical change per commit.
4. Review diffs with `git diff`, not the terminal preview.
5. Verify Python with `python -m py_compile threshold_bot.py` from inside the venv before declaring a change good.
6. Never push. Stino pushes after reviewing.
7. When you find a real problem that is not on this list, report it and let Stino decide. Do not fix it unrequested.

---

## Commit queue

### Commit 1 — Remove contradictory going-live instructions

The repo currently tells a reader to do the one thing CLAUDE.md forbids.

**`setup_instructions_and_requirements.txt`**: delete section 6 in its entirety ("GOING LIVE (WHEN READY)", which instructs flipping `CONFIG['dry_run']` to False). Keep sections 1 through 5, 7, and 8. Section 5, the post-install checklist, is genuinely useful and should survive.

**`README.md`**: currently describes the FastAPI price service scaffold in `app/` as if it were the project. Rewrite it to describe the actual project: a paper trading research instrument answering whether any strategy clears its costs after fees and spread, and what minimum capital it would need. Note the `app/` folder, Dockerfile, and Procfile as a separate, likely vestigial FastAPI scaffold. State the paper-only constraint prominently.

Rationale: an agent reading this repo for context finds the scope constraint in one file and step-by-step instructions for violating it in another. Fix the contradiction before doing anything else.

### Commit 2 — Invert the `dry_run` default (audit item 1)

`threshold_bot.py` line ~204 currently reads:

```python
    "dry_run": False,               # set to False for LIVE trading (can override with DRY_RUN env)
```

Replace with:

```python
    "dry_run": True,                # paper trading only in this repo; DRY_RUN env can override
```

Running the script as-is with valid credentials would currently attempt live orders. Paper mode only engages through a `DRY_RUN` env var that is not documented anywhere.

In the same commit, replace `.env.example` entirely. The current template is wrong: it lists `COINBASE_API_SECRET`, but `threshold_bot.py` line 19 reads `COINBASE_API_SECRET_FILE` and opens it as a PEM path. Only the `app/` scaffold uses the inline secret. The template is also missing `DRY_RUN`, `KILL_SWITCH`, and the whole email block.

```
# Copy to .env and fill values. Do not commit real keys.

# Coinbase Advanced Trade
COINBASE_API_KEY=your_key_here
COINBASE_API_SECRET_FILE=C:\path\to\cb_secret.pem

# Paper trading. Leave at 1. This repo is research only and does not place live orders.
DRY_RUN=1

# Pause the trading loop without stopping the process
KILL_SWITCH=0

# Email notifications
EMAIL_ENABLED=0
EMAIL_FROM=me@example.com
EMAIL_TO=me@example.com
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USER=me@example.com
EMAIL_PASS=app_password_here
EMAIL_USE_TLS=1

# Only used by the app/ FastAPI scaffold
OPENAI_API_KEY=your_openai_key_here
```

Verify: run `python -u .\threshold_bot.py` far enough to see the startup line at line ~769 print `CONFIG dry_run = True`, then stop it.

### Commit 3 — Add `.dockerignore`

The Dockerfile does `COPY . .` and there is no `.dockerignore`. `.gitignore` protects git and does nothing for a Docker build, so building an image on a machine with a real `.env` or PEM present would bake the secret into an image layer. Dormant today, live the moment the Raspberry Pi deployment starts.

```
.env
.env.*
!.env.example
*.pem
*.pem.json
venv/
__pycache__/
.git/
logs/
```

### Open decision, do not implement without Stino

With the default inverted, the override block at `threshold_bot.py` line ~250 still lets `DRY_RUN=false` in the environment turn on live order placement. That sits against the repo's hard constraint. The tightest fix keeps reading the env var but clamps it so it can only ever confirm paper mode and never disable it. This is a distinct decision with its own reasoning. Raise it after commit 2 lands and let Stino choose.

### Commit 4 — Fix `_fee_estimate` KeyError (audit item 2)

`_fee_estimate` references `CONFIG["taker_bps"]`; the correct path is `CONFIG["fees"]["taker_bps"]`. This fires on every DRY trade because `order_type` is hardcoded to `"SIMULATED"`, and the exception is swallowed by the top-level handler.

The serious part: `per["anchor"] = price` executes before the crash. The anchor moves while no trade is logged, so strategy state corrupts silently. DRY mode has most likely never completed a single trade.

Investigate whether the ordering of the anchor assignment relative to the fee calculation needs to change as part of this fix, or whether correcting the key path is sufficient. Report the finding before editing.

### Commit 5 — Model the spread (audit item 3)

There is no spread modeling at all. Fills use `get_price()`, the last-trade tape price, for both buys and sells. The `best_bid` and `best_ask` fallbacks are dead code; those fields do not exist on the current SDK response.

Required behavior: buys fill at the ask, sells fill at the bid, fees actually deducted. This needs a small research task first, since the SDK has drifted since October 2025. Find where the current `coinbase-advanced-py` exposes bid and ask, likely the product book or ticker endpoint. Verify against the installed version rather than assuming. Report what you find before writing the fill logic.

This item is the whole point of the project. The original bot failed in real trading because spread ate the profits, and optimistic simulation would hide exactly that. When uncertain, simulate pessimistically.

### Commit 6 — Fix the candles call (audit item 4)

The candles call is missing required `start` and `end` parameters and fails every tick, swallowed. Consequence: the momentum and atr_breakout strategies never receive data and never run. Only `threshold` has ever executed. Verify the required parameter shape against the installed SDK version.

---

## After the queue

`bot_state.json` holds stale state from October 2025: anchors, FIFO lots, strategy assignments, trade counts. Reset it before any meaningful paper run. `reset_state.py` exists; confirm it does what its name implies before trusting it.

Then the real work begins: run strategies against live market data with honest fills and find out whether any of them clears its costs, and at what capital level.

Longer term, run multiple strategies side by side, and deploy to the Raspberry Pi that currently hosts the Tilt Hydrometer.

---

## GitHub setup (Stino does this, not the agent)

```powershell
git remote add origin https://github.com/<yourname>/coinbase-bot.git
git branch -M main
git push -u origin main
```

Private repo. The revoked key makes the blast radius small, but the repo will hold strategy logic and state files and there is no upside to publishing them.
