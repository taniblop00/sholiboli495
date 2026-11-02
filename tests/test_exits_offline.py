"""Offline test of v4 exits with mocked prices (no network). Runs on a temporary COPY of the repo state,
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
a = openpos("CPOOL", "creator_pool"); b = openpos("BURN", "burned"); g = openpos("GLITCH", "creator_pool")
partial = {}
for step, (pa, pb, pg) in enumerate([(1.05,1.05,1.02),(1.16,1.16,9.0),(1.20,1.22,1.0),(1.26,1.30,1.0),(1.26,1.70,1.0)]):
    PX["CPOOL"], PX["BURN"], PX["GLITCH"] = pa, pb, pg
    scalp.update(c)
    for r in c.execute("SELECT id,symbol,status,tp1_done,tokens_left,exit_reason,round(pnl_pct,1) FROM positions WHERE symbol IN ('CPOOL','BURN','GLITCH')"):
        print(step, tuple(r))
        if r[2] == "open" and r[3] == 1: partial[r[1]] = r[4]
d = export_state.export(c, {"started_ts": 0}, {"state": "test"})
print("open in state.json:", [(p["symbol"], p["tier"], p["gross_pct"], p["live_pnl_pct"], p["tp1_done"]) for p in d["open_positions"]])

rows = {r[0]: r for r in c.execute("SELECT symbol,status,exit_reason,pnl_pct FROM positions WHERE symbol IN ('CPOOL','BURN','GLITCH')")}
assert rows["CPOOL"][2] == "scalp_runner_take_profit" and rows["BURN"][2] == "scalp_runner_take_profit"
assert rows["GLITCH"][2] == "scalp_liquidity_pull_suspected" and rows["GLITCH"][3] < 0, "a broken price must never book a profit"
# creator_pool (disabled, but the code path remains) still sells 70% at +15%. v5 burned sells 40% at +20%.
start_tokens = 3.0 / 1.025
assert abs(partial["CPOOL"] - 0.30 * start_tokens) < 0.02, partial
assert abs(partial["BURN"] - 0.60 * start_tokens) < 0.02, partial
creator = {"lp_locked_pct": 1e-10, "pump_amm_lp_locked_pct": 1e-10, "launchpad": None}
grad = {"lp_locked_pct": 100.0, "pump_amm_lp_locked_pct": 100.0, "launchpad": {"name": "Pump.Fun"}}
hidden = {"lp_locked_pct": 0.0, "pump_amm_lp_locked_pct": 100.0, "launchpad": {"name": "Pump.Fun"}}
assert scalp.classify_tier(creator, "NotAPumpMintxxxx") == "creator_pool"
assert scalp.classify_tier(grad, "RealGraduatepump") == "burned"
assert scalp.classify_tier(hidden, "RealGraduatepump") == "burned", "a burned pump.fun AMM is burned even if another figure is 0"
dust = [
    {"marketType": "pump_fun_amm", "lp": {"lpLockedPct": 0.0, "lpLockedUSD": 0.0, "lpLocked": 101, "lpUnlocked": 5.3e13}},
    {"marketType": "meteora_damm_v2", "lp": {"lpLockedPct": 100, "lpLockedUSD": 0.03, "lpLocked": 8e18, "lpUnlocked": 0}},
]
real = [{"marketType": "pump_fun_amm", "lp": {"lpLockedPct": 100, "lpLockedUSD": 157000, "lpLocked": 4e12, "lpUnlocked": 0}}]
assert run.lp_locked_pct(dust) < 1, run.lp_locked_pct(dust)
assert run.lp_locked_pct(real) >= 99
assert run.CFG["scalp"]["version"] == "v5"
assert run.CFG["scalp"]["tiers"]["creator_pool"]["enabled"] is False
assert run.CFG["scalp"]["tiers"]["burned"]["enabled"] is True
print("OK - v5 burned exits, creator path, LP classification and glitch guard (temp dir", TMP, ")")
