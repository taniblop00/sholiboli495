#!/usr/bin/env python3
"""One-shot PAPER scan of public DexScreener / GeckoTerminal / RugCheck data.

Counts how many pools would pass the v5 burned-LP filters on a single snapshot and
turns that into an entries-per-hour estimate. Reads only. Never trades.
"""
import json, time, urllib.request, collections, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run, scalp

def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "yoni-paper-v5-scan", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def gt_mints(path):
    out = []
    try:
        d = get("https://api.geckoterminal.com/api/v2/networks/solana/" + path)
        for p in d.get("data") or []:
            out.append(p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1])
    except Exception as e:
        print(f"WARN {path}: {e}")
    time.sleep(2.1)
    return out

mints = []
def add(xs):
    for m in xs:
        if m and m not in mints:
            mints.append(m)

print("fetching public pools...")
add(gt_mints("trending_pools?duration=5m&page=1"))
add(gt_mints("trending_pools?duration=1h&page=1"))
add(gt_mints("dexes/pumpswap/pools?sort=h24_tx_count_desc&page=1"))
add(gt_mints("dexes/pumpswap/pools?sort=h24_tx_count_desc&page=2"))
add(gt_mints("dexes/pumpswap/pools?sort=h24_volume_usd_desc&page=1"))
for i in range(1, 4):
    add(gt_mints(f"new_pools?page={i}"))
for path in ("token-profiles/latest/v1", "token-boosts/latest/v1"):
    try:
        for t in get("https://api.dexscreener.com/" + path) or []:
            if t.get("chainId") == "solana" and t.get("tokenAddress") not in mints:
                mints.append(t["tokenAddress"])
    except Exception as e:
        print("WARN ds", path, e)
print(f"universe {len(mints)}  pump-suffix {sum(m.endswith('pump') for m in mints)}")

pairs = {}
for i in range(0, len(mints), 10):
    chunk = mints[i:i + 10]
    try:
        got = get("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(chunk))
    except Exception as e:
        print("WARN ds batch", e); continue
    for p in got or []:
        m = (p.get("baseToken") or {}).get("address")
        if m not in chunk: continue
        liq = (p.get("liquidity") or {}).get("usd") or 0
        if m not in pairs or liq > ((pairs[m].get("liquidity") or {}).get("usd") or 0):
            pairs[m] = p
    time.sleep(0.25)

def evaluate():
    reasons = collections.Counter()
    passed = []
    for m, p in pairs.items():
        f = scalp.feats(p)
        r = scalp.market_filter(f)
        if r:
            reasons[r] += 1
            continue
        f["mint"] = m
        f["pump"] = m.endswith("pump")
        passed.append((m, f))
    return reasons, passed

# Near-miss table: pools inside the v5 age span, so we can see which single gate removes them.
print("\ninside 3 min–24h (first failing gate):")
near = collections.Counter()
examples = []
for m, p in pairs.items():
    f = scalp.feats(p)
    age = f["age_min"]
    if age is None or not (3 <= age <= 1440):
        continue
    r = scalp.market_filter(f)
    near[r or "PASS"] += 1
    if len(examples) < 25:
        bs = f["buys_m5"] / max(1, f["sells_m5"])
        examples.append((r or "PASS", f["symbol"], f["dex"], age, f["mcap"], f["liq"], f["pc_m5"], bs, f["vol_m5"], f["buys_m5"] + f["sells_m5"], f["accel"], m.endswith("pump")))
print(dict(near))
for row in sorted(examples, key=lambda x: (x[0] != "PASS", x[3] or 0))[:25]:
    print(f"  {str(row[0]):18} {str(row[1])[:12]:12} {str(row[2]):10} age={row[3]:.0f} mcap={int(row[4] or 0)} liq={int(row[5] or 0)} m5={row[6]} bs={row[7]:.2f} vol5={int(row[8] or 0)} tx5={row[9]} accel={row[10]} pump={row[11]}")

reasons, passed = evaluate()
print(f"\npre-LP pass {len(passed)}  (pump {sum(1 for _,f in passed if f['pump'])})")
print("top rejects:", reasons.most_common(12))
bands = collections.Counter()
for _, f in passed:
    age = f["age_min"] or 0
    bands["3-120m" if age <= 120 else "surge 2-24h"] += 1
print("bands:", dict(bands))

# RugCheck the passers, graduates first, capped so this stays a snapshot not a crawl.
order = sorted(passed, key=lambda x: (not x[1]["pump"], -x[1]["rank"]))[:28]
print(f"\nrugcheck {len(order)} of {len(passed)} passers")
qual = []
tier_n = collections.Counter()
safe_fail = collections.Counter()
for m, f in order:
    try:
        rc = get(f"https://api.rugcheck.xyz/v1/tokens/{m}/report", timeout=12)
    except Exception as e:
        safe_fail["rugcheck_down"] += 1
        print(f"  fail {f['symbol']} {e}")
        continue
    s = run.safety_features(rc, m)
    tier = scalp.classify_tier(s, m)
    tier_n[tier] += 1
    gate = run.safety_filter(s, run.CFG["scalp"]["safety"])
    flag = "QUAL" if tier == "burned" and not gate else tier
    if tier == "burned" and not gate:
        qual.append((m, f, s))
    elif gate:
        safe_fail[gate] += 1
    print(f"  {flag:22} {str(f['symbol'])[:12]:12} age={f['age_min']:.0f}m m5={f['pc_m5']} bs={f['buys_m5']}/{f['sells_m5']} liq={int(f['liq'] or 0)} lp={s['lp_locked_pct']:.0f} pumpAmm={s['pump_amm_lp_locked_pct']:.0f} holders={s['holders']} {gate or ''}")
    time.sleep(0.45)

print(f"\nrugchecked tiers: {dict(tier_n)}")
print(f"safety rejects: {safe_fail.most_common(8)}")
print(f"qualified burned+safety in the checked set: {len(qual)}")
if order:
    rate = len(qual) / len(order)
    est_stock = rate * len(passed)
else:
    est_stock = 0
# A 5-minute momentum print stays inside the band for roughly 10 minutes, so the
# snapshot stock turns over about 6 times an hour. That is an upper-ish arrival rate;
# the engine also caps entries (2 per scan, 3 open, 30 min cooldown per mint).
print(f"estimated qualified stock across the whole pre-LP set: {est_stock:.1f}")
print(f"estimated entries/hour if a signal lasts ~10 min: {est_stock * 6:.1f}  (before the 2-per-scan cap)")
young = [q for q in qual if (q[1]["age_min"] or 0) <= 30]
print(f"qualified with age<=30m in the checked set: {len(young)}  -> about {len(young) * (60/30):.1f}/hour if that bucket refreshes every 30 min")
