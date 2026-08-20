# SESSION HANDOFF — coinbase-bot

Written 2026-08-20 (updated same day, end of a Claude Code session in VS Code). Supersedes the earlier version of this file — that session's full commit queue is done.

Read CLAUDE.md first. It is authoritative. This file is the work queue.

---

## Scope reminder (non-negotiable)

This repo is a PAPER TRADING research instrument. It never places live orders. Do not enable, restore, or write code paths that place real orders. Do not set `dry_run` to False. If a task in this file appears to conflict with that, stop and ask Stino.

---

## State as of this handoff

`main` is pushed to `https://github.com/augustineiacopelli/Coinbase-Bot`, private-by-assumption (confirm visibility on GitHub if unsure). Working tree is clean.

```
345a264 Add SESSION_HANDOFF.md
9ff58cf Fix candles call: add required start/end params
9711c7d Model bid/ask spread in DRY fills
5e547a1 Fix _fee_estimate KeyError and reorder anchor assignment
97fecb2 Add .dockerignore to keep secrets out of image layers
7a876db Clamp DRY_RUN env override to paper-only
3464ea6 Invert dry_run default to True, fix .env.example
b50c85f Remove contradictory going-live instructions, rewrite README
83547d3 Added CLAUDE.md file to git.
7e2fa2c Initial commit: Coinbase trading bot from Drive backup
```

One historical note: when the remote was first added it already had a GitHub-auto-generated "Initialize with README" commit with no shared history. That was overwritten with `git push --force-with-lease` to land the real history — a deliberate one-time exception to the "never force-push" default, done with Stino's explicit go-ahead. Not expected to recur.

The full commit queue from the prior handoff is done: docs no longer contradict the paper-only scope, `dry_run` defaults to `True` and the `DRY_RUN` env var is clamped so it can only confirm paper mode (never disable it), `.dockerignore` exists, the `_fee_estimate` KeyError is fixed (DRY trades were crashing on every attempt before this), DRY fills now model the bid/ask spread (buy at ask, sell at bid, fees deducted), and the candles call has the `start`/`end` params it was missing (momentum/atr_breakout strategies can now actually receive data).

**None of the Commit 4–6 fixes have been verified against live Coinbase data yet** — no `.env` exists in this environment, so everything was checked with `py_compile` and mocked unit tests of the changed functions only. First real run should be watched closely.

---

## Working discipline (hold to this)

1. Investigate before editing. Read the surrounding code, do not pattern match.
2. Explain what you are about to change before changing it. Wait for Stino's go ahead.
3. One logical change per commit.
4. Review diffs with `git diff`, not the terminal preview.
5. Verify Python with `python -m py_compile threshold_bot.py` from inside the venv before declaring a change good.
6. Never push without being asked. Confirmed default for this project has become: push when Stino says so explicitly (not automatically after every commit).
7. When you find a real problem that is not on this list, report it and let Stino decide. Do not fix it unrequested.

---

## Next queue — getting to a live supervised paper run

Stino's stated end goal: this running continuously, checking live prices with a real API key, executing simulated (paper) buy/sells, to find out which strategy actually clears its costs.

### 1. Create `.env` (Stino does this, not the agent)

Copy `.env.example` → `.env`, fill in `COINBASE_API_KEY` and `COINBASE_API_SECRET_FILE` (path to the `.pem`). Leave `DRY_RUN=1`. Do not paste the key or PEM contents into a Claude Code session — write it directly into the file.

### 2. Open decision: `reset_state.py` doesn't fully reset state

Read during this session: `reset_state.py` clears `anchor`, `last_cross`, `last_trade_time`, and `trades_today`, but does **not** touch `lots`, `pos_base`, or `avg_cost`. CLAUDE.md says `bot_state.json` (stale from Oct 2025: anchors, FIFO lots, strategy, trade counts) "should be reset before meaningful paper runs" — which implies the lots/position fields too, not just anchors/cooldowns. This is unimplemented and undecided. Options to raise with Stino:
- Extend `reset_state.py` to also zero `lots`, `pos_base`, `avg_cost` for a true clean slate.
- Or: start from a fresh/empty `bot_state.json` instead of "resetting" the stale one.
- Or: deliberately keep Oct 2025 lots as a seeded starting position — but confirm this is intentional, not an oversight.

Do not implement either fix without Stino's go-ahead — this changes what "day one" P&L looks like.

### 3. Reset state, then one supervised foreground run

Once `.env` exists and the reset-state decision is made: run `python -u .\threshold_bot.py` in the foreground (not backgrounded yet) and watch for:
- No `[CANDLES ERROR]` spam (would mean the SDK's `get_candles` signature drifted again).
- No `[WARN] DRY_RUN=false...` (would mean env var contents are wrong, not a code issue).
- At least one full DRY BUY and SELL cycle logging correctly to `logs/fills_<year>.csv`, with fees and a bid/ask-based fill price that differs from the tape price.
- `[GLOBAL LIMIT]` / cooldown messages behaving sanely against `CONFIG`'s trade caps.

### 4. Decide the 24/7 deployment target

Two paths, not yet decided:
- **Quick**: scheduled task / long-running background process on the current Windows machine. Fast to set up, doesn't survive reboot/sleep without extra work.
- **Per CLAUDE.md's stated intent**: deploy to the Raspberry Pi that already runs the Tilt Hydrometer — the actual "always on" target. Bigger lift (Docker/Pi setup), not scoped yet.

### 5. Known gap: "best strategy" comparison isn't side-by-side yet

The bot currently auto-picks *one* strategy per asset via `biased_choice_with_margin` (with optional per-asset overrides in `CONFIG["strategy_overrides"]`). It does not run threshold/momentum/atr_breakout in parallel on the same asset for a clean head-to-head. CLAUDE.md flags true side-by-side comparison as a long-term goal, explicitly not to be built prematurely. Worth being clear-eyed that today's results will reflect the *selector's* choices, not an apples-to-apples strategy comparison, until/unless that's built out.

---

## After the queue

Longer term, once the above is running cleanly: let it accumulate paper trades across strategies/assets, then analyze `logs/fills_<year>.csv` to answer the core question — does any strategy clear its costs (fees + spread + tax), and at what minimum capital.
