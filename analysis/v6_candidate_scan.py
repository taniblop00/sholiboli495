#!/usr/bin/env python3
"""PAPER dry scan. Counts how many live pools pass the v6 quality gate. No orders."""
import collections, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import run, scalp

def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "yoni-paper-v6", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def universe():
    mints = []
    def add(path):
        try:
            d = get("https://api.geckoterminal.com/api/v2/networks/solana/" + path)
            for p in d.get("data") or []:
                m = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
                if m not in mints: mints.append(m)
        except Exception as e:
            print("WARN", path, e)
        time.sleep(2.05)
    add("new_pools?page=1"); add("new_pools?page=2"); add("new_pools?page=3")
    add("dexes/pump-fun/pools?sort=h24_tx_count_desc&page=1")
    add("dexes/pumpswap/pools?sort=h24_tx_count_desc&page=1")
    add("trending_pools?duration=5m&page=1")
    pairs = {}
    dex = collections.Counter()
    for i in range(0, len(mints), 10):
        chunk = mints[i:i + 10]
        try:
            got = get("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(chunk))
        except Exception as e:
            print("WARN ds", e); continue
        for p in got or []:
            m = (p.get("baseToken") or {}).get("address")
            if not m: continue
            dex[p.get("dexId")] += 1
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if m not in pairs or liq > ((pairs[m].get("liquidity") or {}).get("usd") or 0):
                pairs[m] = p
        time.sleep(0.2)
    return pairs, dex

def one_pass(rug_cap=12):
    pairs, dex = universe()
    reasons = collections.Counter()
    passed = []
    for m, p in pairs.items():
        f = scalp.feats(p); f["mint"] = m
        r = scalp.market_filter(f)
        if r: reasons[r] += 1
        else:
            f["rank"] = scalp.rank(f); passed.append((m, f))
    print(f"pairs {len(pairs)} dex {dex.most_common(6)}")
    print(f"pre-rugcheck pass {len(passed)} rejects {reasons.most_common(8)}")
    qual = []
    for m, f in sorted(passed, key=lambda x: -x[1]["rank"])[:rug_cap]:
        try:
            rc = get(f"https://api.rugcheck.xyz/v1/tokens/{m}/report")
        except Exception as e:
            print("  rc fail", f["symbol"], e); continue
        s = run.safety_features(rc, m)
        tier = scalp.classify_tier(s, m, f["dex"])
        gate = run.safety_filter(s, run.CFG["scalp"]["safety"])
        qg = scalp.quality_gate(f, s, tier) if not gate else None
        enabled = (run.CFG["scalp"]["tiers"].get(tier) or {}).get("enabled", True)
        ok = not gate and not qg and enabled
        flag = "QUAL" if ok else (gate or qg or f"tier_disabled:{tier}")
        print(f"  {flag:22} {str(f['symbol'])[:14]:14} {tier:14} age={f['age_min']:.0f} m5={f['pc_m5']} bs={f['buys_m5']}/{f['sells_m5']} mcap={int(f['mcap'] or 0)} holders={s['holders']} top10={s['top10_ex_pools']} dev={s['creator_pct']} social={f['has_social']}")
        if ok: qual.append(m)
        time.sleep(0.4)
    return qual, len(passed)

if __name__ == "__main__":
    rounds = 4 if "--once" not in sys.argv else 1
    seen = set(); pre = []
    for i in range(rounds):
        print(f"\n=== round {i+1}/{rounds} {time.strftime('%H:%M:%S')} ===")
        qual, npre = one_pass()
        seen.update(qual); pre.append(npre)
        if i + 1 < rounds:
            time.sleep(200)
    minutes = 16 if rounds > 1 else 4
    print(f"\nunique quality passes over ~{minutes} min: {len(seen)}")
    print(f"implied per hour: {len(seen) * (60/minutes):.1f}")
    print(f"pre-rugcheck counts per round: {pre}")
