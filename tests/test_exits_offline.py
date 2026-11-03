"""Offline test of v2 quote exits and rug_escape (no network). Uses a temp copy of state.
    python tests/test_exits_offline.py
"""
import os, sys, json, shutil, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="mt_test_")
for f in ("config.json", "config.strict.json", "state.db"):
    if os.path.exists(os.path.join(ROOT, f)):
        shutil.copy(os.path.join(ROOT, f), TMP)
os.environ["MT_HOME"] = TMP
os.environ["MT_NO_STDOUT"] = "1"
sys.path.insert(0, ROOT)
import run, scalp

run.fee_usd = lambda: 0.01
QUOTES = {}
def fake_sell(p):
    q = QUOTES.get(p["symbol"])
    if not q:
        return None
    usd, impact = q
    tokens = p["tokens_left"] or 1
    return {"usd": usd, "eff": usd / tokens, "impact": impact, "source": "jupiter_quote"}
scalp.sell_fill = fake_sell
scalp.holder_rug = lambda c, mint, feat: None
PX = {}
LIQ = {}
run.jup_prices = lambda mints: {m: PX[m] for m in mints if m in PX}
run.ds_tokens = lambda mints: {m: {"priceUsd": PX[m], "liquidity": {"usd": LIQ[m]}, "txns": {"m5": {"buys": 40, "sells": 25}}} for m in mints if m in PX}
c = run.db()

def openpos(sym, entry=1.0, liq=40000):
    feat = {"tier": "creator_pool", "creator_pct": 1.0, "top1_ex_pools": 6.0,
            "last_quote_eff": entry, "last_liq": liq, "rug_holder_ts": time.time()}
    tokens = 3.5 / entry
    cur = c.execute("""INSERT INTO positions(mint,symbol,name,pair,dex,opened_at,entry_mark,entry_eff,tokens,tokens_left,decimals,cost_usd,fees_usd,entry_liq,entry_mcap,score,features,reasoning,status,peak_mark,last_mark,last_checked,strategy)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?,'scalp')""",
      (sym, sym, sym, "pair"+sym, "pumpswap", run.iso(), entry, entry, tokens, tokens, 6, 3.5, 0.01, liq, 80000, 70,
       json.dumps(feat), "test", entry, entry, run.iso()))
    run.set_cash(c, run.cash(c) - 3.51)
    c.commit()
    PX[sym] = entry
    LIQ[sym] = liq
    return cur.lastrowid

# Mark says +40%. The sell quote is only +10%. v2 must NOT take profit on the mark.
openpos("MARK")
PX["MARK"] = 1.40
QUOTES["MARK"] = (3.5 * 1.10, 0.1)
scalp.update(c)
row = c.execute("SELECT status, tp1_done, exit_reason FROM positions WHERE symbol='MARK'").fetchone()
assert row["status"] == "open" and not row["tp1_done"], tuple(row)

# Quote +16% sells half at the quote, with one priority fee and no second haircut.
openpos("HALF")
QUOTES["HALF"] = (3.5 * 1.16, 0.2)
scalp.update(c)
row = c.execute("SELECT status, tp1_done, tokens_left FROM positions WHERE symbol='HALF'").fetchone()
fill = c.execute("SELECT usd, source FROM fills WHERE side='SELL' ORDER BY id DESC").fetchone()
assert row["status"] == "open" and row["tp1_done"] == 1, tuple(row)
assert abs(fill["usd"] - (3.5 * 1.16 * 0.5 - 0.01)) < 1e-9, tuple(fill)
assert fill["source"] == "jupiter_quote"

# Liquidity down 25% from entry exits immediately at the (still healthy) quote.
openpos("LIQ")
LIQ["LIQ"] = 30000
QUOTES["LIQ"] = (3.5 * 1.02, 0.3)
scalp.update(c)
row = c.execute("SELECT status, exit_reason, pnl_usd FROM positions WHERE symbol='LIQ'").fetchone()
fill = c.execute("SELECT usd, source FROM fills WHERE side='SELL' ORDER BY id DESC").fetchone()
assert row["status"] == "closed" and row["exit_reason"] == "scalp_rug_escape", tuple(row)
assert abs(fill["usd"] - (3.5 * 1.02 - 0.01)) < 1e-9, tuple(fill)

# One poll, quote down 10% from the previous quote. Book that quote, not a capped fantasy.
openpos("AIR")
QUOTES["AIR"] = (3.5 * 0.90, 1.0)
scalp.update(c)
row = c.execute("SELECT status, exit_reason, pnl_pct FROM positions WHERE symbol='AIR'").fetchone()
assert row["status"] == "closed" and row["exit_reason"] == "scalp_rug_escape", tuple(row)
assert row["pnl_pct"] < -5, tuple(row)

# Pool is already gone and the sell quote fails: book zero, a real loss.
openpos("GONE", liq=40000)
LIQ["GONE"] = 1000
QUOTES.pop("GONE", None)
scalp.update(c)
row = c.execute("SELECT status, exit_reason, pnl_pct FROM positions WHERE symbol='GONE'").fetchone()
fill = c.execute("SELECT usd, source FROM fills WHERE side='SELL' ORDER BY id DESC").fetchone()
assert row["status"] == "closed" and row["exit_reason"] == "scalp_rug_escape", tuple(row)
assert fill["usd"] == 0 and fill["source"] == "no_sell_quote", tuple(fill)
assert row["pnl_pct"] < -90, tuple(row)

base = {"age_min": 8, "price": 0.001, "quote": "SOL", "vol_m5": 12000, "buys_m5": 40, "sells_m5": 25,
        "pc_m5": 10, "pc_h1": 5, "accel": 1.0, "has_social": False, "liq": 25000, "mcap": 80000, "dex": "pumpswap"}
assert scalp.market_filter(base) is None
assert scalp.market_filter({**base, "dex": "pumpfun"}) == "blocked_dex"
assert scalp.market_filter({**base, "dex": "meteora"}) == "blocked_dex"
assert scalp.market_filter({**base, "age_min": 25}) == "too_old"
assert scalp.market_filter({**base, "mcap": 5000}) == "mcap_range"
assert scalp.market_filter({**base, "pc_h1": -20}) == "h1_down"
assert scalp.market_filter({**base, "price": 0}) == "no_reliable_price"
assert scalp.classify_tier({}, "mintpump", "pumpfun") == "bonding_curve"
assert scalp.classify_tier({"lp_locked_pct": 100, "pump_amm_lp_locked_pct": 100}, "mintpump", "pumpswap") == "burned"
assert scalp.quality_gate(base, {"holders": 40, "risk_names": []}, "bonding_curve") == "few_holders"
dust = [
    {"marketType": "pump_fun_amm", "lp": {"lpLockedPct": 0.0, "lpLockedUSD": 0.0, "lpLocked": 101, "lpUnlocked": 5.3e13}},
    {"marketType": "meteora_damm_v2", "lp": {"lpLockedPct": 100, "lpLockedUSD": 0.03, "lpLocked": 8e18, "lpUnlocked": 0}},
]
assert run.lp_locked_pct(dust) < 1
S = run.CFG["scalp"]
assert S["version"] == "v2"
assert S["version_note"] == "v2 + rug escape"
assert S["tiers"]["creator_pool"]["enabled"] is True
assert S["tiers"]["bonding_curve"]["enabled"] is False
assert S["exits"]["tp1_sell_fraction"] == 0.5
assert S["exits"]["stop_loss_gross_pct"] == -5.0
assert S["exits"]["tp1_gross_pct"] == 15.0
assert S["filters"]["min_age_min"] == 3 and S["filters"]["max_age_min"] == 20
assert S["filters"]["allowed_dexes"] == ["pumpswap"]
assert run.CFG["costs"]["extra_slippage_pct_each_side"] == 0
assert run.CFG["costs"]["wallet_swap_fee_pct"] == 0
print("OK v2 quote exits and rug_escape", TMP)
