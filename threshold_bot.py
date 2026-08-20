# threshold_bot.py — LIVE/DRY trading with FIFO lots, tax estimates, CSV logs, and email on all trades
# Notes:
# - Uses .env for Coinbase keys and Gmail SMTP settings
# - Emails are sent for BUY and SELL in both DRY and LIVE modes
# - SELL emails include gross, fees, long/short tax estimates, and an estimated net after tax
# - CSV logs roll per tax year into logs/fills_<year>.csv

import os, time, json, math, smtplib, csv
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from coinbase.rest import RESTClient
from email.message import EmailMessage

# ---------- Load .env ----------
load_dotenv()

# ---------- Keys / switches ----------
CB_API_KEY = os.getenv("COINBASE_API_KEY")
CB_API_SECRET_FILE = os.getenv("COINBASE_API_SECRET_FILE")
KILL_SWITCH = os.getenv("KILL_SWITCH", "0") == "1"

# ---------- Time helpers ----------
CENTRAL_TZ = None
try:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")
except Exception:
    try:
        from zoneinfo import ZoneInfo
        CENTRAL_TZ = ZoneInfo("America/Chicago")
    except Exception:
        CENTRAL_TZ = None

def utcnow():
    return datetime.now(timezone.utc)

def tax_year_year():
    if CENTRAL_TZ:
        return datetime.now(CENTRAL_TZ).year
    return datetime.now().year

# ---------- Email ----------
def _truthy(val: str) -> bool:
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}

def _email_enabled():
    return _truthy(os.getenv("EMAIL_ENABLED", "0"))

def _parse_recipients(raw: str):
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return [p for p in parts if p]

def send_email(subject, body):
    if not _email_enabled():
        return
    try:
        msg = EmailMessage()
        msg["From"] = os.getenv("EMAIL_FROM")
        msg["To"] = ", ".join(_parse_recipients(os.getenv("EMAIL_TO", "")))
        msg["Subject"] = subject
        msg.set_content(body)

        host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        user = os.getenv("EMAIL_USER")
        pwd = os.getenv("EMAIL_PASS")
        use_tls = _truthy(os.getenv("EMAIL_USE_TLS", "1"))

        if not all([host, port, user, pwd, msg["From"], msg["To"]]):
            print("[EMAIL] Skipped. Missing credentials or to/from.")
            return

        with smtplib.SMTP(host, port, timeout=20) as s:
            s.ehlo()
            if use_tls:
                s.starttls()
                s.ehlo()
            s.login(user, pwd)
            s.send_message(msg)
        print(f"[EMAIL] Sent -> {msg['To']}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")

def notify_trade_generic(mode, side, product_id, size, price, order_type, order_id, fees=0.0, extra_note=""):
    subj = f"[{mode}] {side} {product_id} {size:.8f}@{price:.8f} ({order_type})"
    body = (
        f"Mode: {mode}\n"
        f"Side: {side}\n"
        f"Product: {product_id}\n"
        f"Size: {size:.8f}\n"
        f"Price: {price:.8f}\n"
        f"Order Type: {order_type}\n"
        f"Order ID: {order_id or '(n/a)'}\n"
        f"Est. Fees: {fees:.8f}\n"
        f"{('Note: ' + extra_note + '\\n') if extra_note else ''}"
        f"Time: {utcnow().isoformat()}\n"
    )
    send_email(subj, body)

def notify_trade_sell_with_tax(mode, product_id, size, price, order_type, order_id, fees, breakdown, net_after_tax):
    base, quote = product_id.split("-")
    gross = (breakdown['long']['proceeds'] + breakdown['short']['proceeds'])
    lt = breakdown['long']
    st = breakdown['short']
    lt_tax_rate = CONFIG["tax"]["cap_gains_rate_long"]
    st_tax_rate = CONFIG["tax"]["cap_gains_rate_short"]
    lt_tax = max(lt["pnl"], 0.0) * lt_tax_rate
    st_tax = max(st["pnl"], 0.0) * st_tax_rate

    subj = f"[{mode}] SELL {product_id} {size:.8f}@{price:.8f} ({order_type})"
    body = (
        f"Mode: {mode}\n"
        f"Side: SELL\n"
        f"Product: {product_id}\n"
        f"Size: {size:.8f}\n"
        f"Price: {price:.8f}\n"
        f"Order Type: {order_type}\n"
        f"Order ID: {order_id or '(n/a)'}\n"
        f"Gross Proceeds: {gross:.8f} {quote}\n"
        f"Est. Fees: {fees:.8f} {quote}\n\n"
        f"Long-Term Portion:\n"
        f"  Qty: {lt['qty']:.8f}\n"
        f"  Proceeds: {lt['proceeds']:.8f} {quote}\n"
        f"  Basis: {lt['basis']:.8f} {quote}\n"
        f"  PnL: {lt['pnl']:.8f} {quote}\n"
        f"  Est. LT Cap Gains Tax @ {lt_tax_rate:.2%}: {lt_tax:.8f} {quote}\n\n"
        f"Short-Term Portion:\n"
        f"  Qty: {st['qty']:.8f}\n"
        f"  Proceeds: {st['proceeds']:.8f} {quote}\n"
        f"  Basis: {st['basis']:.8f} {quote}\n"
        f"  PnL: {st['pnl']:.8f} {quote}\n"
        f"  Est. ST Cap Gains Tax @ {st_tax_rate:.2%}: {st_tax:.8f} {quote}\n\n"
        f"Estimated Net After Tax (PnL - fees - taxes): {net_after_tax:.8f} {quote}\n"
        f"Time: {utcnow().isoformat()}\n"
    )
    send_email(subj, body)

# ---------- CSV logging ----------
def log_trade_csv(
    product_id: str,
    side: str,
    size_base: float,
    price_quote_per_base: float,
    mode: str,                      # "DRY" | "LIVE"
    order_type: str,                # "LIMIT" | "MARKET" | "SIMULATED"
    client_order_id: str = "",
    order_id: str = "",
    fee_quote: float = 0.0,
    fee_rate: float = 0.0,
    note: str = ""
):
    os.makedirs("logs", exist_ok=True)
    year = tax_year_year()
    filename = f"logs/fills_{year}.csv"
    new_file = not os.path.exists(filename)

    now_utc = datetime.now(timezone.utc)
    if CENTRAL_TZ:
        try:
            now_ct = now_utc.astimezone(CENTRAL_TZ).isoformat()
        except Exception:
            now_ct = ""
    else:
        now_ct = ""

    base, quote = product_id.split("-")
    notional_quote = (size_base or 0.0) * (price_quote_per_base or 0.0)

    with open(filename, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow([
                "timestamp_utc","timestamp_ct","product_id","base","quote",
                "side","order_type","mode",
                "size_base","price_quote_per_base","notional_quote",
                "client_order_id","order_id",
                "fee_quote","fee_rate",
                "note"
            ])
        w.writerow([
            now_utc.isoformat(), now_ct, product_id, base, quote,
            side, order_type, mode,
            f"{size_base:.8f}",
            f"{(price_quote_per_base or 0.0):.8f}",
            f"{notional_quote:.8f}",
            client_order_id or "", order_id or "",
            f"{fee_quote:.8f}", f"{fee_rate:.8f}",
            note or ""
        ])

# ---------- Config ----------
CONFIG = {
    "assets": {
        "BTC-USDC":  {"up_pct": 0.005, "down_pct": 0.005, "tranche_pct": 0.25, "min_gap_min": 2},
        "ETH-USDC":  {"up_pct": 0.006, "down_pct": 0.006, "tranche_pct": 0.25, "min_gap_min": 2},
        "DOGE-USDC": {"up_pct": 0.010, "down_pct": 0.010, "tranche_pct": 0.20, "min_gap_min": 3},
    },
    "min_hours_between_trades": 4,
    "max_trades_per_day": 3,
    "max_global_trades_per_day": 6,
    "poll_seconds": 30,
    "dry_run": True,                # paper trading only in this repo; DRY_RUN env can override
    "state_file": "bot_state.json",

    # Maker behavior
    "maker_offset": 0.0005,         # 0.05% off mid for post-only limit
    "maker_wait_sec": 60,
    "enable_market_fallback": False,

    # Risk buffers
    "risk": {
        "min_quote_reserve": 50.0,
        "min_base_reserve": {
            "BTC": 0.00010,
            "ETH": 0.002,
            "DOGE": 100.0
        }
    },

    # Strategy engine
    "momentum_cfg": {
        "ema_fast_len": 20, "ema_slow_len": 50,
        "breakout_lookback": 20, "trailing_stop_mult": 2.0
    },
    "atr_cfg": {
        "atr_len": 14, "sma_len": 20, "atr_mult": 1.6,
        "quiet_filter_len": 20, "quiet_atr_max": 0.012
    },
    "candles": {"granularity": "ONE_MINUTE", "limit": 200},

    # Strategy discipline
    "strategy_overrides": {},
    "strategy_min_hold_minutes": 60,
    "strategy_change_margin": 0.0025,

    # Fees (bps estimates)
    "fees": {"maker_bps": 6, "taker_bps": 10},

    # Simple tax model rates
    "tax": {"cap_gains_rate_short": 0.24, "cap_gains_rate_long": 0.15},

    # Logging / visibility
    "verbose": True,
    "products": {}
}

# DRY_RUN env can confirm paper mode but never disable it. This repo is
# paper-only (see CLAUDE.md); it must not be possible to flip dry_run to
# False via the environment.
if os.getenv("DRY_RUN") is not None and not _truthy(os.getenv("DRY_RUN")):
    print("[WARN] DRY_RUN=false in env is ignored; this repo is paper-only.")
CONFIG["dry_run"] = True

# ---------- Utils ----------
def round_down(value: float, step: float) -> float:
    if step is None or step <= 0:
        return value
    return math.floor(value / step) * step

def load_state():
    if os.path.exists(CONFIG["state_file"]):
        with open(CONFIG["state_file"], "r") as f:
            return json.load(f)
    return {"per_asset": {}, "date": utcnow().date().isoformat()}

def save_state(state):
    with open(CONFIG["state_file"], "w") as f:
        json.dump(state, f, indent=2)

# ---------- Coinbase client ----------
def cb_client():
    pem = None
    if CB_API_SECRET_FILE and os.path.exists(CB_API_SECRET_FILE):
        with open(CB_API_SECRET_FILE, "r", encoding="utf-8") as f:
            pem = f.read()
    if CB_API_KEY and pem:
        return RESTClient(api_key=CB_API_KEY, api_secret=pem)
    return RESTClient()

def get_product(product_id: str) -> dict:
    resp = cb_client().get_product(product_id)
    return resp.to_dict() if hasattr(resp, "to_dict") else resp

def hydrate_products():
    print("Hydrating product specs from Coinbase Advanced...")
    for pid in CONFIG["assets"].keys():
        d = get_product(pid) or {}
        base = d.get("base_currency_id") or d.get("base_currency") or pid.split("-")[0]
        quote = d.get("quote_currency_id") or d.get("quote_currency") or pid.split("-")[1]
        base_inc = float(d.get("base_increment") or 0.00000001)
        quote_inc = float(d.get("quote_increment") or 0.01)
        base_min = float(d.get("base_min_size") or 0.0)
        quote_min = float(d.get("quote_min_size") or d.get("min_market_funds") or 10.0)

        CONFIG["products"][pid] = {
            "base": base,
            "quote": quote,
            "base_increment": base_inc,
            "quote_increment": quote_inc,
            "base_min_size": base_min,
            "quote_min_size": quote_min,
        }
        print(f" - {pid}: base_inc={base_inc} quote_inc={quote_inc} base_min={base_min} quote_min={quote_min}")

def get_accounts_balances() -> dict:
    out = {"USD": 0.0, "USDC": 0.0, "BTC": 0.0, "ETH": 0.0, "DOGE": 0.0}
    resp = cb_client().get_accounts()
    d = resp.to_dict() if hasattr(resp, "to_dict") else resp
    for acct in d.get("accounts", []):
        curr = acct.get("currency")
        bal = float(acct.get("available_balance", {}).get("value", 0.0))
        if curr in out:
            out[curr] = bal
    return out

def get_price(product_id: str) -> float:
    d = get_product(product_id) or {}
    p = d.get("price") or d.get("best_bid") or d.get("best_ask")
    return float(p) if p is not None else None

# ---------- Candles + indicators ----------
def get_candles(product_id: str, granularity: str, limit: int):
    try:
        path = f"/api/v3/brokerage/products/{product_id}/candles"
        params = {"granularity": granularity, "limit": str(limit)}
        resp = cb_client().get(path, params=params)
        data = resp if isinstance(resp, dict) else getattr(resp, "to_dict", lambda: {})()
        c = data.get("candles", [])
        c = sorted(c, key=lambda x: x.get("start"))
        ts, o, h, l, cl = [], [], [], [], []
        for k in c:
            ts.append(k.get("start"))
            o.append(float(k.get("open", 0)))
            h.append(float(k.get("high", 0)))
            l.append(float(k.get("low", 0)))
            cl.append(float(k.get("close", 0)))
        return ts, o, h, l, cl
    except Exception as e:
        print(f"[CANDLES ERROR] {product_id}: {e}")
        return [], [], [], [], []

def ema(series, length):
    if not series or length <= 0:
        return 0.0
    k = 2 / (length + 1)
    e = series[0]
    for p in series[1:]:
        e = p * k + e * (1 - k)
    return e

def atr(highs, lows, closes, length):
    if len(closes) < length + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)
    return ema(trs[-length:], length)

def realized_volatility(closes, window=50):
    if len(closes) < window + 1:
        return 0.0
    import math as _math
    rets = []
    for i in range(1, window+1):
        if closes[-i-1] > 0:
            r = _math.log(closes[-i] / closes[-i-1])
            rets.append(r)
    if not rets:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / max(len(rets) - 1, 1)
    return var ** 0.5

# ---------- Strategies ----------
def strategy_threshold_signal(price, per, cfg):
    if per.get("anchor") is None:
        per["anchor"] = price
        return None
    up_trigger = per["anchor"] * (1 + cfg["up_pct"])
    down_trigger = per["anchor"] * (1 - cfg["down_pct"])
    if price >= up_trigger:
        return "SELL"
    if price <= down_trigger:
        return "BUY"
    return None

def strategy_momentum_signal(prices, highs, lows, cfg):
    need = max(cfg["ema_fast_len"], cfg["ema_slow_len"], cfg["breakout_lookback"]) + 2
    if len(prices) < need:
        return None
    ema_fast = ema(prices[-cfg["ema_fast_len"]:], cfg["ema_fast_len"])
    ema_slow = ema(prices[-cfg["ema_slow_len"]:], cfg["ema_slow_len"])
    trend_up = ema_fast > ema_slow
    breakout_level = max(highs[-cfg["breakout_lookback"]:])
    last_price = prices[-1]
    if trend_up and last_price > breakout_level:
        return "BUY"
    if last_price < ema_slow:
        return "SELL"
    return None

def strategy_atr_breakout_signal(prices, highs, lows, closes, cfg):
    need = max(cfg["atr_len"], cfg["sma_len"]) + 5
    if len(prices) < need:
        return None
    a = atr(highs, lows, closes, cfg["atr_len"])
    sma_len = cfg["sma_len"]
    sma = sum(prices[-sma_len:]) / max(sma_len, 1)
    upper = sma + cfg["atr_mult"] * a
    lower = sma - cfg["atr_mult"] * a
    last_close = closes[-1]

    quiet_ok = True
    if cfg.get("quiet_filter_len") and cfg.get("quiet_atr_max") is not None and len(prices) >= cfg["quiet_filter_len"] + cfg["atr_len"] + 2:
        qlen = cfg["quiet_filter_len"]
        for i in range(len(prices) - qlen, len(prices)):
            idx = max(0, i - cfg["atr_len"] - 1)
            sub_a = atr(highs[idx:i+1], lows[idx:i+1], closes[idx:i+1], cfg["atr_len"])
            if sub_a > cfg["quiet_atr_max"]:
                quiet_ok = False
                break

    if quiet_ok and last_close > upper:
        return "BUY"
    if quiet_ok and last_close < lower:
        return "SELL"
    return None

# ---------- Strategy selection ----------
def compute_asset_stats(prices, cfg_mom):
    vol = realized_volatility(prices, window=50)
    if len(prices) >= max(cfg_mom["ema_fast_len"], cfg_mom["ema_slow_len"]) + 1:
        efast = ema(prices[-cfg_mom["ema_fast_len"]:], cfg_mom["ema_fast_len"])
        eslow = ema(prices[-cfg_mom["ema_slow_len"]:], cfg_mom["ema_slow_len"])
        trend = efast - eslow
    else:
        trend = 0.0
    return {"vol": vol, "trend": trend}

def biased_choice_with_margin(stats, last_strategy):
    margin = CONFIG.get("strategy_change_margin", 0.0)
    vol = stats["vol"]
    trend = stats["trend"]
    if vol < (0.01 - margin) and abs(trend) < (0.005 + margin):
        return "threshold"
    if trend > (0.005 + margin) and vol >= (0.01 - margin):
        return "momentum"
    if vol >= (0.02 - margin):
        return "atr_breakout"
    return last_strategy or "threshold"

# ---------- Sizing, steps, orders ----------
def price_to_step(price: float, pid: str) -> float:
    step = CONFIG["products"].get(pid, {}).get("quote_increment", 0.01)
    return round_down(price, step)

def size_to_step(size: float, pid: str) -> float:
    step = CONFIG["products"].get(pid, {}).get("base_increment", 0.00000001)
    return round_down(size, step)

def tranche_size(product_id: str, balances: dict, tranche_pct: float, side: str, price: float) -> float:
    base, quote = product_id.split("-")
    if side == "BUY":
        quote_bal = balances.get(quote, 0.0)
        quote_to_spend = quote_bal * tranche_pct
        return max(quote_to_spend / max(price, 1e-12), 0.0)
    else:
        base_bal = balances.get(base, 0.0)
        return max(base_bal * tranche_pct, 0.0)

def place_market_order(side: str, product_id: str, base_size: float):
    body = {
        "client_order_id": f"thr-{product_id}-{int(time.time())}",
        "product_id": product_id,
        "side": side,
        "order_configuration": {
            "market_market_ioc": {"base_size": f"{base_size:.8f}"}
        }
    }
    return cb_client().post("/api/v3/brokerage/orders", data=body)

def place_post_only_limit(side: str, product_id: str, base_size: float, limit_price: float):
    base_size = size_to_step(base_size, product_id)
    limit_price = price_to_step(limit_price, product_id)
    body = {
        "client_order_id": f"thr-{product_id}-{int(time.time())}",
        "product_id": product_id,
        "side": side,
        "order_configuration": {
            "limit_limit_gtc": {
                "base_size": f"{base_size:.8f}",
                "limit_price": f"{limit_price:.8f}",
                "post_only": True
            }
        }
    }
    return cb_client().post("/api/v3/brokerage/orders", data=body)

# ---------- Trading guardrails ----------
def can_trade_now(per, product_id, balances, side, price):
    if per.get("trades_today", 0) >= CONFIG["max_trades_per_day"]:
        print(f"[{product_id}] daily per-asset trade limit reached.")
        return False
    lt = per.get("last_trade_time")
    if lt:
        if (utcnow() - datetime.fromisoformat(lt)) < timedelta(hours=CONFIG["min_hours_between_trades"]):
            print(f"[{product_id}] cooldown active.")
            return False
    base = product_id.split("-")[0]
    quote = product_id.split("-")[1]
    if side == "BUY":
        min_q = CONFIG["risk"]["min_quote_reserve"]
        if balances.get(quote, 0.0) <= min_q:
            print(f"[{product_id}] quote reserve guard. {quote} <= min reserve.")
            return False
    else:
        min_b = CONFIG["risk"]["min_base_reserve"].get(base, 0.0)
        if balances.get(base, 0.0) <= min_b:
            print(f"[{product_id}] base reserve guard. {base} <= min reserve.")
            return False
    return True

def total_trades_today(state):
    return sum(p.get("trades_today", 0) for p in state["per_asset"].values())

# ---------- Lots (FIFO) ----------
def ensure_lots_seeded(per: dict, base_bal: float, seed_cost_per_unit: float, seed_date_iso: str):
    lots = per.setdefault("lots", [])
    if lots:
        return
    qty = max(float(base_bal), 0.0)
    if qty <= 0:
        return
    lots.append({
        "qty": qty,
        "cost": float(seed_cost_per_unit),
        "acquired_at": seed_date_iso
    })
    per["pos_base"] = qty
    per.setdefault("avg_cost", float(seed_cost_per_unit))

def add_buy_lot(per: dict, qty: float, cost_per_unit: float, ts_iso: str):
    if qty <= 0:
        return
    lots = per.setdefault("lots", [])
    lots.append({"qty": float(qty), "cost": float(cost_per_unit), "acquired_at": ts_iso})

def fifo_consume_sell(per: dict, sell_qty: float, sell_price: float):
    lots = per.setdefault("lots", [])
    realized_long = realized_short = 0.0
    proceeds_long = proceeds_short = 0.0
    basis_long = basis_short = 0.0
    long_qty = short_qty = 0.0
    sell_remaining = float(sell_qty)
    now = utcnow()

    new_lots = []
    for lot in lots:
        if sell_remaining <= 0:
            new_lots.append(lot)
            continue
        take = min(lot["qty"], sell_remaining)
        hold_period = now - datetime.fromisoformat(lot["acquired_at"])
        is_long = hold_period.days > 365

        proceeds = take * sell_price
        basis = take * lot["cost"]
        pnl = proceeds - basis

        if is_long:
            realized_long += pnl
            proceeds_long += proceeds
            basis_long += basis
            long_qty += take
        else:
            realized_short += pnl
            proceeds_short += proceeds
            basis_short += basis
            short_qty += take

        remain = lot["qty"] - take
        sell_remaining -= take
        if remain > 0:
            new_lots.append({"qty": remain, "cost": lot["cost"], "acquired_at": lot["acquired_at"]})

    per["lots"] = new_lots
    per["pos_base"] = max(per.get("pos_base", 0.0) - sell_qty, 0.0)
    if per["pos_base"] <= 0:
        per["avg_cost"] = 0.0

    return {
        "long": {"qty": long_qty, "proceeds": proceeds_long, "basis": basis_long, "pnl": realized_long},
        "short": {"qty": short_qty, "proceeds": proceeds_short, "basis": basis_short, "pnl": realized_short}
    }

def estimate_tax_from_breakdown(breakdown: dict):
    lt_rate = CONFIG["tax"]["cap_gains_rate_long"]
    st_rate = CONFIG["tax"]["cap_gains_rate_short"]
    lt_tax = max(breakdown["long"]["pnl"], 0.0) * lt_rate
    st_tax = max(breakdown["short"]["pnl"], 0.0) * st_rate
    return lt_tax, st_tax

# ---------- Verbose status ----------
def _fmt(x):
    try:
        return f"{x:.8f}"
    except Exception:
        return str(x)

def debug_status(product_id, price, per, chosen, stats, signal, asset_cfg):
    anchor = per.get("anchor")
    vol = stats.get("vol", 0.0)
    trend = stats.get("trend", 0.0)
    base_line = (
        f"[{product_id}] strat={chosen} price={_fmt(price)} "
        f"anchor={_fmt(anchor) if anchor is not None else 'None'} "
        f"signal={signal} vol={vol:.4f} trend={trend:.6f}"
    )
    print(base_line)
    if chosen == "threshold" and anchor is not None and asset_cfg:
        up = anchor * (1 + asset_cfg.get("up_pct", 0.0))
        dn = anchor * (1 - asset_cfg.get("down_pct", 0.0))
        print(
            f"[{product_id}] threshold up={_fmt(up)} (+{asset_cfg.get('up_pct',0.0)*100:.3f}%) "
            f"down={_fmt(dn)} (-{asset_cfg.get('down_pct',0.0)*100:.3f}%) "
            f"min_gap_min={asset_cfg.get('min_gap_min')}"
        )

# ---------- Fees and inventory ----------
def _fee_estimate(quote_notional: float, order_type: str) -> float:
    bps = CONFIG["fees"]["maker_bps"] if order_type == "LIMIT" else CONFIG["fees"]["taker_bps"]
    return quote_notional * (bps / 10_000.0)

def _update_inventory_on_buy(per: dict, base_size: float, price: float):
    old_pos = per.get("pos_base", 0.0)
    old_cost = per.get("avg_cost", 0.0)
    buy_quote = base_size * price
    new_pos = old_pos + base_size
    if new_pos > 0:
        new_cost = ((old_pos * old_cost) + buy_quote) / new_pos
    else:
        new_cost = 0.0
    per["pos_base"] = new_pos
    per["avg_cost"] = new_cost
    per["last_buy_ts"] = utcnow().isoformat()

# ---------- Execute trade ----------
def maybe_trade(side: str, product_id: str, price: float, balances: dict, cfg: dict, per: dict):
    base = product_id.split("-")[0]
    size = tranche_size(product_id, balances, cfg["tranche_pct"], side, price)
    if size <= 0:
        print(f"[{product_id}] no size for {side}.")
        return False

    # DRY path
    if CONFIG["dry_run"]:
        client_id = f"thr-{product_id}-{int(time.time())}"
        print(f"[DRY] {product_id} {side} {size:.8f} @ ~{price:.8f} (anchor={per.get('anchor')})")
        order_type = "SIMULATED"
        fees = _fee_estimate(size * price, order_type)

        if side == "BUY":
            _update_inventory_on_buy(per, size, price)
            add_buy_lot(per, size, price, utcnow().isoformat())
            note = "BUY lot added; no tax until sold."
            notify_trade_generic("DRY", "BUY", product_id, size, price, order_type, client_id, fees, note)
        else:
            breakdown = fifo_consume_sell(per, size, price)
            gross = breakdown["long"]["proceeds"] + breakdown["short"]["proceeds"]
            lt_tax, st_tax = estimate_tax_from_breakdown(breakdown)
            net_after_tax = (breakdown["long"]["pnl"] + breakdown["short"]["pnl"]) - fees - lt_tax - st_tax
            long_qty = breakdown["long"]["qty"]
            short_qty = breakdown["short"]["qty"]
            lt_pnl = breakdown["long"]["pnl"]
            st_pnl = breakdown["short"]["pnl"]
            note = (
                f"LT: qty={long_qty:.8f}, pnl={lt_pnl:.8f}; "
                f"ST: qty={short_qty:.8f}, pnl={st_pnl:.8f}; "
                f"est_tax(LT)={lt_tax:.8f}; est_tax(ST)={st_tax:.8f}; "
                f"est_net_after_tax={net_after_tax:.8f}"
            )
            notify_trade_sell_with_tax("DRY", product_id, size, price, order_type, client_id, fees, breakdown, net_after_tax)

        log_trade_csv(
            product_id=product_id, side=side, size_base=size,
            price_quote_per_base=price, mode="DRY", order_type=order_type,
            client_order_id=client_id, order_id="",
            fee_quote=fees, fee_rate=0.0, note=note
        )
        per["anchor"] = price
        return True

    # LIVE path
    client_id = f"thr-{product_id}-{int(time.time())}"
    offset = CONFIG["maker_offset"]
    limit_price = price * (1 - offset) if side == "BUY" else price * (1 + offset)
    limit_price = price_to_step(limit_price, product_id)

    order_id = ""
    order_type = "LIMIT"
    placed_price_for_email = limit_price
    try:
        resp = place_post_only_limit(side, product_id, size, limit_price)
        if isinstance(resp, dict):
            order_id = resp.get("success_response", {}).get("order_id") or resp.get("order_id", "")
        print(f"[LIVE] Limit {side} {product_id} {size:.8f} @ {limit_price:.8f} id={order_id}")
    except Exception as e:
        print(f"[WARN] post-only place failed: {e}")
        if CONFIG["enable_market_fallback"]:
            print("[FALLBACK] placing market order")
            try:
                resp = place_market_order(side, product_id, size)
                order_type = "MARKET"
                placed_price_for_email = price
                if isinstance(resp, dict):
                    order_id = resp.get("success_response", {}).get("order_id") or resp.get("order_id", "")
            except Exception as ee:
                print(f"[ERROR] market fallback failed: {ee}")
                return False
        else:
            return False

    if side == "BUY":
        _update_inventory_on_buy(per, size, placed_price_for_email)
        add_buy_lot(per, size, placed_price_for_email, utcnow().isoformat())
        fees = _fee_estimate(size * placed_price_for_email, order_type)
        note = "BUY lot added; tax only when sold."
        notify_trade_generic("LIVE", "BUY", product_id, size, placed_price_for_email, order_type, order_id, fees, note)
    else:
        breakdown = fifo_consume_sell(per, size, placed_price_for_email)
        gross = breakdown["long"]["proceeds"] + breakdown["short"]["proceeds"]
        fees = _fee_estimate(gross, order_type)
        lt_tax, st_tax = estimate_tax_from_breakdown(breakdown)
        net_after_tax = (breakdown["long"]["pnl"] + breakdown["short"]["pnl"]) - fees - lt_tax - st_tax
        long_qty = breakdown["long"]["qty"]
        short_qty = breakdown["short"]["qty"]
        lt_pnl = breakdown["long"]["pnl"]
        st_pnl = breakdown["short"]["pnl"]
        note = (
            f"LT: qty={long_qty:.8f}, pnl={lt_pnl:.8f}; "
            f"ST: qty={short_qty:.8f}, pnl={st_pnl:.8f}; "
            f"est_tax(LT)={lt_tax:.8f}; est_tax(ST)={st_tax:.8f}; "
            f"est_net_after_tax={net_after_tax:.8f}"
        )
        notify_trade_sell_with_tax("LIVE", product_id, size, placed_price_for_email, order_type, order_id, fees, breakdown, net_after_tax)

    log_trade_csv(
        product_id=product_id,
        side=side,
        size_base=size,
        price_quote_per_base=placed_price_for_email if order_type == "LIMIT" else price,
        mode="LIVE",
        order_type=order_type,
        client_order_id=client_id,
        order_id=order_id,
        fee_quote=fees,
        fee_rate=0.0,
        note=note
    )
    return True

# ---------- Main ----------
def main():
    print(f"RUNNING FILE: {os.path.abspath(__file__)}")
    print("CONFIG dry_run =", CONFIG["dry_run"], type(CONFIG["dry_run"]))
    print("Threshold bot starting...", flush=True)
    print("DRY_RUN =", CONFIG["dry_run"], "KILL_SWITCH =", KILL_SWITCH, flush=True)
    print(f"[LOGGING] trades -> logs/fills_{tax_year_year()}.csv", flush=True)
    hydrate_products()
    state = load_state()

    while True:
        try:
            if KILL_SWITCH:
                print("[KILL_SWITCH] Enabled. Sleeping...")
                time.sleep(CONFIG["poll_seconds"])
                continue

            # date boundary reset
            today = utcnow().date().isoformat()
            if state.get("date") != today:
                state["date"] = today
                for k in state["per_asset"].keys():
                    state["per_asset"][k]["trades_today"] = 0
                save_state(state)

            # optional global cap
            if isinstance(CONFIG.get("max_global_trades_per_day"), int):
                if total_trades_today(state) >= CONFIG["max_global_trades_per_day"]:
                    print("[GLOBAL LIMIT] Daily cap reached.")
                    time.sleep(CONFIG["poll_seconds"])
                    continue

            balances = get_accounts_balances()
            print(f"[{utcnow().isoformat()}] tick balances={balances}", flush=True)

            # portfolio snapshot
            def _safe_px(pid):
                try:
                    return get_price(pid) or 0.0
                except Exception:
                    return 0.0

            btc_px = _safe_px("BTC-USDC")
            eth_px = _safe_px("ETH-USDC")
            doge_px = _safe_px("DOGE-USDC")

            btc_val = balances.get("BTC", 0.0) * btc_px
            eth_val = balances.get("ETH", 0.0) * eth_px
            doge_val = balances.get("DOGE", 0.0) * doge_px
            usdc_val = balances.get("USDC", 0.0)
            total_val = btc_val + eth_val + doge_val + usdc_val
            print(
                f"[PORTFOLIO] BTC=${btc_val:,.2f}  ETH=${eth_val:,.2f}  DOGE=${doge_val:,.2f}  "
                f"USDC=${usdc_val:,.2f}  → TOTAL=${total_val:,.2f}",
                flush=True
            )

            # per asset loop
            for product_id, asset_cfg in CONFIG["assets"].items():
                per = state["per_asset"].setdefault(product_id, {
                    "anchor": None,
                    "trades_today": 0,
                    "last_trade_time": None,
                    "strategy": "threshold",
                    "strategy_since": utcnow().isoformat(),
                    "pos_base": 0.0,
                    "avg_cost": 0.0,
                    "last_buy_ts": None,
                    "lots": [],
                    "signal_ts": {"BUY": None, "SELL": None}
                })

                # Seed lots once if needed (assuming existing holdings are long-term)
                base = product_id.split("-")[0]
                cur_bal_base = balances.get(base, 0.0)
                seed_date = "2023-01-01T00:00:00+00:00"
                cur_px = btc_px if base == "BTC" else eth_px if base == "ETH" else doge_px
                ensure_lots_seeded(per, cur_bal_base, seed_cost_per_unit=cur_px or 0.0, seed_date_iso=seed_date)

                # fetch market data
                price = get_price(product_id)
                if price is None:
                    print(f"[{product_id}] no price, skip.")
                    continue

                ts, opens, highs, lows, closes = get_candles(
                    product_id,
                    CONFIG["candles"]["granularity"],
                    CONFIG["candles"]["limit"]
                )
                if not closes:
                    closes = [price]
                    highs = [price]
                    lows = [price]
                    opens = [price]

                prices = closes
                stats = compute_asset_stats(prices, CONFIG["momentum_cfg"])

                # choose strategy with margin, apply override, enforce min hold time
                last_strategy = per.get("strategy")
                chosen = biased_choice_with_margin(stats, last_strategy)
                override = CONFIG.get("strategy_overrides", {}).get(product_id)
                if override:
                    chosen = override
                hold_min = CONFIG.get("strategy_min_hold_minutes", 0)
                since_iso = per.get("strategy_since")
                since = datetime.fromisoformat(since_iso) if since_iso else utcnow()
                if hold_min > 0 and (utcnow() - since) < timedelta(minutes=hold_min):
                    chosen = last_strategy
                if chosen != last_strategy:
                    per["strategy"] = chosen
                    per["strategy_since"] = utcnow().isoformat()
                else:
                    per.setdefault("strategy_since", utcnow().isoformat())

                # produce signal
                signal = None
                if chosen == "threshold":
                    signal = strategy_threshold_signal(price, per, asset_cfg)
                elif chosen == "momentum":
                    signal = strategy_momentum_signal(prices, highs, lows, CONFIG["momentum_cfg"])
                elif chosen == "atr_breakout":
                    signal = strategy_atr_breakout_signal(prices, highs, lows, prices, CONFIG["atr_cfg"])

                # Verbose per-tick status
                if CONFIG.get("verbose", False):
                    debug_status(product_id, price, per, chosen, stats, signal, asset_cfg)

                # per-side min-gap
                if signal in ("BUY", "SELL"):
                    sig_ts = per.setdefault("signal_ts", {"BUY": None, "SELL": None})
                    last_sig = sig_ts.get(signal)
                    if last_sig:
                        elapsed = utcnow() - datetime.fromisoformat(last_sig)
                        if elapsed < timedelta(minutes=asset_cfg["min_gap_min"]):
                            print(f"[{product_id}] skip {signal}: MIN_GAP {elapsed.total_seconds()/60:.2f}m < {asset_cfg['min_gap_min']}m")
                            save_state(state)
                            continue

                # guardrails and execute
                if signal in ("BUY", "SELL"):
                    if not can_trade_now(per, product_id, balances, signal, price):
                        continue
                    traded = maybe_trade(signal, product_id, price, balances, asset_cfg, per)
                    if traded:
                        per["trades_today"] = per.get("trades_today", 0) + 1
                        per["last_trade_time"] = utcnow().isoformat()
                        per.setdefault("signal_ts", {"BUY": None, "SELL": None})[signal] = utcnow().isoformat()
                        save_state(state)

        except Exception as e:
            print("Error:", repr(e), flush=True)

        time.sleep(CONFIG["poll_seconds"])

if __name__ == "__main__":
    main()