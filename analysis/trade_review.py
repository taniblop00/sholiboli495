#!/usr/bin/env python3
"""Full review of every closed PAPER trade (all sessions) + replay of alternative exits on the logged 5-8 s tick paths.
Usage: python3 analysis/trade_review.py [state.db] [cycle.log]   (paths default to repo root)"""
import sqlite3, json, re, sys, os, statistics as st, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "state.db")
LOG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "logs", "cycle_history_until_2026-11-02.log")
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
def session(o):
    t = o[:16]
    if t < "2026-11-02T06:40": return "night"
    if t < "2026-11-02T08:10": return "v2"
    return "v3"
rows = []
for p in c.execute("SELECT * FROM positions WHERE status='closed' ORDER BY opened_at"):
    f = json.loads(p["features"] or "{}")
    rc = c.execute("SELECT data FROM rc_cache WHERE mint=?", (p["mint"],)).fetchone()
    d = json.loads(rc[0]) if rc else {}
    lp = ((d.get("markets") or [{}])[0] or {}).get("lp") or {}
    o = dt.datetime.fromisoformat(p["opened_at"]); cl = dt.datetime.fromisoformat(p["closed_at"])
    th = d.get("topHolders") or []
    rows.append(dict(id=p["id"], strat=p["strategy"], sess=session(p["opened_at"]), sym=p["symbol"], mint=p["mint"], dex=f.get("dex"),
        age=f.get("age_min") if f.get("age_min") is not None else (f.get("age_h") or 0) * 60, mcap=f.get("mcap"), liq=f.get("liq"),
        liq_mcap=(f.get("liq") or 0) / max(1, f.get("mcap") or 1), vol5=f.get("vol_m5"), bs5=(f.get("buys_m5") or 0) / max(1, f.get("sells_m5") or 1),
        tx5=(f.get("buys_m5") or 0) + (f.get("sells_m5") or 0), pc5=f.get("pc_m5"), pch1=f.get("pc_h1"), holders=f.get("holders"),
        top10=f.get("top10_ex_pools"), top1=f.get("top1_ex_pools"), cost=f.get("entry_cost_pct"),
        lp_locked=lp.get("lpLockedPct"), pct_reserve=lp.get("pctReserve"), pool_top1=(th[0]["pct"] if th else None),
        holder2=(th[1]["pct"] if len(th) > 1 else None), pump_mint=p["mint"].endswith("pump"),
        reason=(p["exit_reason"] or "").replace("scalp_", ""), pnl=p["pnl_pct"], usd=p["pnl_usd"], hold=(cl - o).total_seconds() / 60,
        opened=o, closed=cl))
for r in rows:
    r["creator_pool"] = (r["lp_locked"] is not None and r["lp_locked"] < 1 and not r["pump_mint"])
    r["pull"] = r["reason"] == "liquidity_drop" and r["pnl"] < -30
    r["big_loss"] = r["pnl"] <= -20
def pf(rs):
    w = sum(r["usd"] for r in rs if r["usd"] > 0); l = -sum(r["usd"] for r in rs if r["usd"] <= 0); return w / l if l else float("inf")
def summ(name, rs):
    if not rs: print(f"{name}: n=0"); return
    W = [r for r in rs if r["pnl"] > 0]; L = [r for r in rs if r["pnl"] <= 0]
    print(f"{name:34s} n={len(rs):2d} WR={100*len(W)/len(rs):3.0f}% avgW={st.mean([r['pnl'] for r in W]) if W else 0:+6.1f}% "
          f"avgL={st.mean([r['pnl'] for r in L]) if L else 0:+6.1f}% PF={pf(rs):.2f} net=${sum(r['usd'] for r in rs):+.2f} pulls={sum(r['pull'] for r in rs)}")
print("=" * 30, "SESSIONS"); 
for s in ("night", "v2", "v3"): summ(f"{s} all", [r for r in rows if r["sess"] == s])
summ("ALL", rows); summ("scalp only", [r for r in rows if r["strat"] == "scalp"])
sc = [r for r in rows if r["strat"] == "scalp"]
summ("scalp creator-pool (LP unlocked)", [r for r in sc if r["creator_pool"]]); summ("scalp other", [r for r in sc if not r["creator_pool"]])
summ("scalp meteora", [r for r in sc if r["dex"] == "meteora"]); summ("scalp pumpswap", [r for r in sc if r["dex"] == "pumpswap"])
print("\n" + "=" * 30, "FEATURES: median winners / losers / pulls (scalp, excl session_end)")
S = [r for r in sc if r["reason"] != "session_end"]
W = [r for r in S if r["pnl"] > 0]; L = [r for r in S if r["pnl"] <= 0]; P = [r for r in S if r["pull"]]; NP = [r for r in S if not r["pull"]]
def med(rs, k):
    v = [r[k] for r in rs if isinstance(r[k], (int, float))]; return st.median(v) if v else float("nan")
print(f"{'feature':12s} {'win':>9s} {'loss':>9s} {'pull':>9s} {'non-pull':>9s}")
for k in ["age", "mcap", "liq", "liq_mcap", "vol5", "tx5", "bs5", "pc5", "pch1", "holders", "top10", "top1", "holder2", "cost", "hold"]:
    print(f"{k:12s} {med(W,k):9.3g} {med(L,k):9.3g} {med(P,k):9.3g} {med(NP,k):9.3g}")
print("\nexit reasons:")
er = {}
for r in sc: er.setdefault(r["reason"], []).append(r)
for k, v in sorted(er.items(), key=lambda x: sum(r["usd"] for r in x[1])):
    print(f"  {k:24s} n={len(v):2d} sum=${sum(r['usd'] for r in v):+.2f} avg={st.mean([r['pnl'] for r in v]):+.1f}%")
print("\nall losses (scalp):")
for r in sorted([r for r in sc if r["pnl"] <= 0], key=lambda r: r["pnl"]):
    print(f"  #{r['id']} {r['sess']:5s} {r['sym'][:10]:10s} {r['dex']:9s} {r['reason']:22s} {r['pnl']:+6.1f}% held {r['hold']:4.1f}m age {r['age']:5.1f} bs5 {r['bs5']:.1f} pc5 {r['pc5']} creator_pool={r['creator_pool']}")

# ---------- tick paths ----------
ticks = []
for line in open(LOG, errors="ignore"):
    m = re.match(r"\[(\S+ \S+)\] \[scalp\] tick: (.*)", line)
    if not m: continue
    ts = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    parts = []
    for part in m.group(2).split(" | "):
        mm = re.match(r"(.+?) ([+-]\d+\.\d)% \(pk", part.strip())
        if mm: parts.append((mm.group(1), float(mm.group(2))))
    ticks.append((ts, parts))
TZ = dt.timedelta(hours=2)
def path_of(r):
    o, cl = r["opened"].replace(tzinfo=None) + TZ, r["closed"].replace(tzinfo=None) + TZ
    same = sorted([q for q in sc if q["sym"] == r["sym"] and q["opened"] <= r["closed"] and q["closed"] >= r["opened"]], key=lambda q: q["opened"])
    idx = same.index(r); out = []
    for ts, parts in ticks:
        if o <= ts <= cl + dt.timedelta(seconds=3):
            occ = [g for s, g in parts if s == r["sym"]]
            if len(occ) > idx and abs(occ[idx]) < 500: out.append(((ts - o).total_seconds() / 60, occ[idx]))
    return out
for r in sc: r["path"] = path_of(r)
paths = [r for r in sc if r["sess"] in ("v2", "v3") and len(r["path"]) >= 3]
print(f"\n{'='*30} REPLAY on {len(paths)} v2/v3 tick paths (6-8 s resolution). Pull = remaining position -> -100% at pull time.")
def net(g, cost): return ((1 + g / 100) * (1 - cost / 100) - 1) * 100
def sim(r, X, cost=6.0):
    """X: sl, tp1, f1, tp2 (None=no second leg -> sell all at tp1 when f1==1), be, trail, tmax"""
    rem, pnl, hit1, peak = 1.0, 0.0, False, 0.0
    stop = X["sl"]
    for t, g in r["path"]:
        peak = max(peak, g)
        if g <= stop: pnl += rem * net(g, cost); return pnl, t, "stop"
        if not hit1 and g >= X["tp1"]:
            pnl += X["f1"] * net(g, cost); rem -= X["f1"]; hit1 = True; stop = max(stop, X.get("be", stop))
            if rem <= 1e-9: return pnl, t, "tp"
        if hit1 and X.get("tp2") and g >= X["tp2"]: pnl += rem * net(g, cost); return pnl, t, "tp2"
        if hit1 and X.get("trail") and g <= peak - X["trail"] * (1 + peak / 100): pnl += rem * net(g, cost); return pnl, t, "trail"
        if t >= X["tmax"]: pnl += rem * net(g, cost); return pnl, t, "time"
        if not hit1 and X.get("tstop") and t >= X["tstop"] and g < X.get("tstop_gain", 4): pnl += rem * net(g, cost); return pnl, t, "tstop"
    # path ended before any rule fired
    if r["pull"] and r["hold"] <= X["tmax"] + 0.2: pnl += rem * -100; return pnl, r["hold"], "PULL"
    g = r["path"][-1][1]; pnl += rem * net(g, cost); return pnl, r["path"][-1][0], "end"
VARIANTS = {
 "v3 actual rules (50%@15, BE+3, runner 40/trail10, 30m)": dict(sl=-5, tp1=15, f1=0.5, be=3, tp2=40, trail=10, tmax=30, tstop=12),
 "all-out @+10, SL-5, max 10m": dict(sl=-5, tp1=10, f1=1.0, tmax=10, tstop=6, tstop_gain=2),
 "all-out @+12, SL-5, max 10m": dict(sl=-5, tp1=12, f1=1.0, tmax=10, tstop=6, tstop_gain=2),
 "all-out @+15, SL-5, max 10m": dict(sl=-5, tp1=15, f1=1.0, tmax=10, tstop=6, tstop_gain=2),
 "all-out @+20, SL-5, max 12m": dict(sl=-5, tp1=20, f1=1.0, tmax=12, tstop=6, tstop_gain=2),
 "70%@+15, 30% runner to +25 (trail 6), max 10m": dict(sl=-5, tp1=15, f1=0.7, be=8, tp2=25, trail=6, tmax=10, tstop=6, tstop_gain=2),
 "v4: 75%@+15, 25% to +25/BE+8/trail6, SL-4, max 9m": dict(sl=-4, tp1=15, f1=0.75, be=8, tp2=25, trail=6, tmax=9, tstop=5, tstop_gain=3),
}
def stats(res, label):
    v = [x[0] for x in res]; W = [x for x in v if x > 0]; L = [x for x in v if x <= 0]
    pfv = sum(W) / -sum(L) if L and sum(L) else float("inf")
    print(f"  {label:52s} n={len(v)} WR={100*len(W)/len(v):3.0f}% avgW={st.mean(W) if W else 0:+5.1f}% avgL={st.mean(L) if L else 0:+6.1f}% PF={pfv:5.2f} exp={st.mean(v):+5.2f}%/trade hold~{st.mean([x[1] for x in res]):.1f}m")
for cost in (6.0, 7.5):
    print(f" -- round-trip cost {cost}%")
    for k, X in VARIANTS.items(): stats([sim(r, X, cost) for r in paths], k)
# pull timing
print("\nPULL timing (minutes after entry) and gross % just before the pull:")
for r in [r for r in sc if r["pull"]]:
    last = r["path"][-1] if r["path"] else (None, None)
    print(f"  #{r['id']} {r['sym']:10s} pulled at {r['hold']:.1f}m, last tick {last}")
cp = [r for r in sc if r["creator_pool"]]
mins = sum(r["hold"] for r in cp); np_ = sum(r["pull"] for r in cp)
print(f"\nCreator-pool hazard: {np_} pulls over {mins:.0f} position-minutes = {100*np_/mins:.2f}% per minute held "
      f"(-> {100*(1-(1-np_/mins)**5):.0f}% chance in 5 min, {100*(1-(1-np_/mins)**10):.0f}% in 10 min, {100*(1-(1-np_/mins)**15):.0f}% in 15 min)")
# gaps
print("\nSTOP GAPS (stop at -5% gross, actual exit gross):")
for r in [r for r in sc if r["reason"] in ("stop_loss",)]:
    pre = [g for t, g in r["path"]]
    print(f"  #{r['id']} {r['sym']:10s} net {r['pnl']:+.1f}% | ticks {pre[-4:]}")
# sym repeat
from collections import Counter
cnt = Counter(r["sym"] for r in cp)
print("\nRepeated tickers among creator-pool trades:", dict(cnt.most_common(10)))
