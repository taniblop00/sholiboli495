"""Offline test of v6 fast exits and the quality gate (no network). Runs on a temporary COPY of the repo state,
so the real state.db is never touched.   python tests/test_exits_offline.py"""
import os, sys, json, shutil, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="mt_test_")
for f in ("config.json", "config.strict.json", "state.db"):
    if os.path.exists(os.path.join(ROOT, f)): shutil.copy(os.path.join(ROOT, f), TMP)
os.environ["MT_HOME"] = TMP; os.environ["MT_NO_STDOUT"] = "1"; sys.path.insert(0, ROOT)
import run, scalp, export_state
run.fee_usd = lambda: 0.05
run.sim_sell = lambda mint, tokens, mark, dec: (tokens*mark*0.97, 0.1, "mock")
PX = {}; LIQ = {}
run.jup_prices = lambda mints: {m: PX[m] for m in mints if m in PX}
run.ds_tokens = lambda mints: {m: {"priceUsd": PX[m], "liquidity": {"usd": LIQ[m]}, "txns": {"m5": {"buys": 50, "sells": 10}}} for m in mints if m in PX}
c = run.db()
def openpos(mint, tier, entry=1.0):
    f = {"tier": tier}
    cur = c.execute("""INSERT INTO positions(mint,symbol,name,pair,dex,opened_at,entry_mark,entry_eff,tokens,tokens_left,decimals,cost_usd,fees_usd,entry_liq,entry_mcap,score,features,reasoning,status,peak_mark,last_mark,last_checked,strategy)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?,'scalp')""", (mint, mint, mint, "pair"+mint, "pumpswap", run.iso(), entry, entry*1.025, 3.0/(entry*1.025), 3.0/(entry*1.025), 6, 3.0, 0.05, 40000, 20000, 70, json.dumps(f), "test", entry, entry, run.iso()))
    run.set_cash(c, run.cash(c)-3.05); c.commit(); PX[mint]=entry; LIQ[mint]=40000; return cur.lastrowid
openpos("WIN", "burned"); openpos("STOPP", "burned"); openpos("LOCK", "burned"); openpos("GLITCH", "bonding_curve")
PX.update(WIN=1.11, STOPP=0.93, LOCK=1.07, GLITCH=1.0)
scalp.update(c)
PX["LOCK"] = 1.02   # was +7%, now about +2%, more than 4% off the peak
PX["GLITCH"] = 9.0
scalp.update(c)
for r in c.execute("SELECT symbol,status,exit_reason,round(pnl_pct,1) FROM positions WHERE symbol IN ('WIN','STOPP','LOCK','GLITCH')"):
    print(tuple(r))
rows = {r[0]: r for r in c.execute("SELECT symbol,status,exit_reason,pnl_pct FROM positions WHERE symbol IN ('WIN','STOPP','LOCK','GLITCH')")}
assert rows["WIN"][1] == "closed" and rows["WIN"][2] == "scalp_take_profit_full"
assert rows["STOPP"][1] == "closed" and rows["STOPP"][2] == "scalp_stop_loss"
assert rows["LOCK"][1] == "closed" and rows["LOCK"][2] == "scalp_profit_lock"
assert rows["GLITCH"][2] == "scalp_liquidity_pull_suspected" and rows["GLITCH"][3] < 0
base = {"age_min": 5, "price": 0.001, "quote": "SOL", "vol_m5": 4000, "buys_m5": 50, "sells_m5": 20,
        "pc_m5": 8, "accel": 1.2, "has_social": True, "liq": 20000, "mcap": 20000}
curve = {**base, "dex": "pumpfun", "liq": None, "mcap": 20000}
assert scalp.market_filter(curve) is None
assert scalp.market_filter({**curve, "has_social": False}) is None  # social ranks higher; DexScreener rarely has it yet
assert scalp.market_filter({**curve, "price": 0}) == "no_reliable_price"
assert scalp.market_filter({**curve, "mcap": 3000}) == "mcap_range"
assert scalp.market_filter({**curve, "dex": "meteora"}) == "blocked_dex"
assert scalp.classify_tier({}, "mintpump", "pumpfun") == "bonding_curve"
assert scalp.classify_tier({"lp_locked_pct": 100, "pump_amm_lp_locked_pct": 100}, "mintpump", "pumpswap") == "burned"
assert scalp.quality_gate(base, {"holders": 40, "risk_names": []}, "bonding_curve") == "few_holders"
assert scalp.quality_gate(base, {"holders": 80, "risk_names": ["Snipers detected"]}, "bonding_curve") == "sniper_or_bundle"
dust = [
    {"marketType": "pump_fun_amm", "lp": {"lpLockedPct": 0.0, "lpLockedUSD": 0.0, "lpLocked": 101, "lpUnlocked": 5.3e13}},
    {"marketType": "meteora_damm_v2", "lp": {"lpLockedPct": 100, "lpLockedUSD": 0.03, "lpLocked": 8e18, "lpUnlocked": 0}},
]
assert run.lp_locked_pct(dust) < 1
assert run.CFG["scalp"]["version"] == "v8"
assert run.CFG["scalp"]["tiers"]["creator_pool"]["enabled"] is False
assert run.CFG["scalp"]["tiers"]["bonding_curve"]["enabled"] is True
assert run.CFG["scalp"]["exits"]["tp1_sell_fraction"] == 1.0
assert run.CFG["scalp"]["exits"]["stop_loss_gross_pct"] >= -8
print("OK - v6 exit path still books full take-profit, stop, lock, curve tier and quality gate; engine version is v8 (temp dir", TMP, ")")
