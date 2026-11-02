#!/usr/bin/env python3
"""SCALP mode for the memetrader PAPER engine. Simulation only: never signs or sends anything.
v5: burned / locked LP only. creator_pool stays in the code but is disabled (its liquidity can be pulled).
  * "burned"       - dominant pool LP >= 90% locked, or a pump.fun graduate whose PumpSwap LP was burned
  * "creator_pool" - LP unlocked. Disabled by default.
Age for burned: 3-120 min on the normal momentum band, or 2h-24h only on a fresh surge.
  python3 scalp.py scan | update | report
"""
import json, time, datetime, math, os, sys
import run
from run import log, get, iso, now, local, SOL

def C(): return run.CFG["scalp"]
STATUS = {}   # live scanner status for docs/data/state.json (filled by scan())

def rugcheck_cached(c, mint, ttl=600):
    r = c.execute("SELECT ts, data FROM rc_cache WHERE mint=?", (mint,)).fetchone()
    if r and time.time() - r["ts"] < ttl: return json.loads(r["data"])
    rc = run.rugcheck(mint)
    if rc:
        slim = {k: rc.get(k) for k in ["token", "tokenProgram", "creatorBalance", "topHolders", "knownAccounts", "markets", "risks",
                                       "score_normalised", "totalHolders", "rugged", "transferFee", "graphInsidersDetected",
                                       "launchpad", "deployPlatform", "mintAuthority", "freezeAuthority"]}
        c.execute("INSERT OR REPLACE INTO rc_cache VALUES(?,?,?)", (mint, time.time(), json.dumps(slim))); c.commit()
        return slim
    return None

def discover(c):
    """Universe = (a) GT trending 5m/1h + pump.fun-curve & PumpSwap most active + DexScreener latest profiles/boosts,
    plus (b) a WATCHLIST of tokens seen in GT new_pools (1-5 min old) with early traction, re-checked on later scans
    so they enter the universe once they are 5 min - 12 h old."""
    c.execute("CREATE TABLE IF NOT EXISTS watch(mint TEXT PRIMARY KEY, added REAL, src TEXT)")
    mints, src = [], {}
    def add(m, s):
        if m and m not in run.EXCLUDE:
            if m not in src: mints.append(m); src[m] = []
            src[m].append(s)
    W = C().get("watch", {})
    calls = [("trending_pools?duration=5m&page=1", "gt_trend5m"), ("trending_pools?duration=5m&page=2", "gt_trend5m"),
             ("trending_pools?duration=1h&page=1", "gt_trend1h"),
             ("dexes/pumpswap/pools?sort=h24_volume_usd_desc&page=1", "gt_pumpswap_vol"),
             ("dexes/pump-fun/pools?sort=h24_tx_count_desc&page=1", "gt_pumpfun_curve_tx")]
    calls += [(f"new_pools?page={i}", "gt_new") for i in range(1, W.get("new_pool_pages", 4) + 1)]
    added = 0
    for path, tag in calls:
        try:
            d = get("https://api.geckoterminal.com/api/v2/networks/solana/" + path, retries=1)
            for p in d.get("data", []):
                m = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1]
                if tag == "gt_new":
                    a = p["attributes"]; t5 = (a.get("transactions") or {}).get("m5") or {}
                    quote = a.get("name", "").split(" / ")[-1]
                    if quote in ("SOL", "USDC") and (t5.get("buys") or 0) >= W.get("min_buys_m5", 15) and float(a.get("fdv_usd") or 0) >= W.get("min_fdv_usd", 4000):
                        if c.execute("INSERT OR IGNORE INTO watch VALUES(?,?,?)", (m, time.time(), "gt_new")).rowcount: added += 1
                else:
                    add(m, tag)
        except Exception as e: log(f"WARN scalp gt {tag}: {e}")
        time.sleep(2.1)
    for path, tag in [("token-profiles/latest/v1", "ds_profile"), ("token-boosts/latest/v1", "ds_boost")]:
        try:
            for t in get("https://api.dexscreener.com/" + path, retries=1) or []:
                if t.get("chainId") == "solana": add(t.get("tokenAddress"), tag)
        except Exception as e: log(f"WARN scalp ds {tag}: {e}")
    c.execute("DELETE FROM watch WHERE added<?", (time.time() - 12 * 3600,))
    wl = [r["mint"] for r in c.execute("SELECT mint FROM watch ORDER BY added DESC LIMIT ?", (W.get("max_recheck", 200),))]
    for m in wl: add(m, "watchlist")
    c.commit()
    return mints, src, added, len(wl)

def prune_watch(c, pairs):
    """Drop watchlist tokens that clearly died, to keep re-check cost bounded."""
    dead = 0
    for r in c.execute("SELECT mint, added FROM watch").fetchall():
        age = (time.time() - r["added"]) / 60
        p = pairs.get(r["mint"])
        if p is None:
            if age > 20: c.execute("DELETE FROM watch WHERE mint=?", (r["mint"],)); dead += 1
            continue
        mc = p.get("marketCap") or p.get("fdv") or 0; vh1 = (p.get("volume") or {}).get("h1") or 0
        if (age > 20 and mc < 8000) or (age > 60 and vh1 < 1000):
            c.execute("DELETE FROM watch WHERE mint=?", (r["mint"],)); dead += 1
    c.commit(); return dead

def feats(p):
    tx = p.get("txns") or {}; vol = p.get("volume") or {}; pc = p.get("priceChange") or {}
    m5 = tx.get("m5") or {}; h1 = tx.get("h1") or {}
    created = p.get("pairCreatedAt")
    socials = {s.get("type") for s in (p.get("info") or {}).get("socials") or []}
    vm5, vh1 = vol.get("m5") or 0, vol.get("h1") or 0
    age_min = (time.time() * 1000 - created) / 60000 if created else None
    # acceleration: last-5-min volume pace vs average 5-min volume of the last hour (or of the token's life if younger)
    windows = max(1.0, min(12.0, (age_min or 60) / 5))
    accel = vm5 / max(1e-9, vh1 / windows) if vh1 else 0
    return {"price": float(p.get("priceUsd") or 0), "mcap": p.get("marketCap") or p.get("fdv") or 0,
            "liq": (p.get("liquidity") or {}).get("usd"), "age_min": age_min, "dex": p.get("dexId"),
            "quote": (p.get("quoteToken") or {}).get("symbol"), "pair": p.get("pairAddress"),
            "symbol": (p.get("baseToken") or {}).get("symbol"), "name": (p.get("baseToken") or {}).get("name"),
            "vol_m5": vm5, "vol_h1": vh1, "buys_m5": m5.get("buys") or 0, "sells_m5": m5.get("sells") or 0,
            "buys_h1": h1.get("buys") or 0, "sells_h1": h1.get("sells") or 0,
            "pc_m5": pc.get("m5") or 0, "pc_h1": pc.get("h1") or 0, "pc_h6": pc.get("h6") or 0,
            "accel": round(accel, 2), "has_twitter": "twitter" in socials}

def entry_window(f):
    """v5 age bands. The 3-120 min band uses the normal momentum limits.
    2h-24h is allowed only as a fresh surge (separate, looser b/s and a wider 5m cap)."""
    F = C()["filters"]
    surge = F.get("surge") or {}
    age = f["age_min"]
    if age is None: return "no_age"
    bs = f["buys_m5"] / max(1, f["sells_m5"])
    if F["min_age_min"] <= age <= F["max_age_min"]:
        if f["pc_m5"] > F["max_price_change_m5"]: return "m5_parabolic"
        if bs < F["min_buy_sell_ratio_m5"]: return "m5_sell_pressure"
        return None
    smin, smax = surge.get("min_age_min", 120), surge.get("max_age_min", 1440)
    if age > F["max_age_min"] and smin < age <= smax:
        if f["pc_m5"] < surge.get("min_price_change_m5", F["min_price_change_m5"]): return "surge_m5"
        if f["pc_m5"] > surge.get("max_price_change_m5", 25): return "surge_m5_hot"
        if bs < surge.get("min_buy_sell_ratio_m5", 2.0): return "surge_bs"
        if f["pc_h1"] > surge.get("max_price_change_h1", F["max_price_change_h1"]): return "surge_h1"
        if (f["liq"] or 0) < surge.get("min_liquidity_usd", 30000): return "surge_liq"
        return None
    return "too_old" if age > F["min_age_min"] else "too_young"

def market_filter(f):
    F = C()["filters"]
    surge = F.get("surge") or {}
    if f["age_min"] is None: return "no_age"
    if f["age_min"] < F["min_age_min"]: return "too_young"
    max_age = max(F.get("max_age_min", 120), surge.get("max_age_min", 0))
    if f["age_min"] > max_age: return "too_old"
    if f["quote"] not in F["allowed_quote_symbols"]: return "bad_quote"
    if f["dex"] in F.get("blocked_dexes", []): return "blocked_dex"
    if F.get("allowed_dexes") and f["dex"] not in F["allowed_dexes"]: return "dex_not_allowed"
    if not (F["min_mcap_usd"] <= f["mcap"] <= F["max_mcap_usd"]): return "mcap_range"
    curve = f["dex"] in ("pumpfun", "meteoradbc", "launchlab", "raydiumlaunchlab")
    if f["liq"] is None and not curve: return "no_liq_data"
    if f["liq"] is not None:
        if f["liq"] < F["min_liquidity_usd"]: return "low_liq"
        if f["liq"] / max(1, f["mcap"]) < F["min_liq_to_mcap"]: return "liq_mcap_ratio"
    if f["vol_m5"] < F["min_vol_m5_usd"]: return "low_vol_m5"
    if f["buys_m5"] + f["sells_m5"] < F["min_txns_m5"]: return "low_txns_m5"
    min_bs = min(F["min_buy_sell_ratio_m5"], surge.get("min_buy_sell_ratio_m5", F["min_buy_sell_ratio_m5"]))
    max_m5 = max(F["max_price_change_m5"], surge.get("max_price_change_m5", F["max_price_change_m5"]))
    if f["buys_m5"] / max(1, f["sells_m5"]) < min_bs: return "m5_sell_pressure"
    if f["pc_m5"] < min(F["min_price_change_m5"], surge.get("min_price_change_m5", F["min_price_change_m5"])): return "m5_not_rising"
    if f["pc_m5"] > max_m5: return "m5_parabolic"
    if f["pc_h1"] < F["min_price_change_h1"]: return "h1_down"
    if f["pc_h1"] > max(F["max_price_change_h1"], surge.get("max_price_change_h1", F["max_price_change_h1"])): return "h1_parabolic"
    if f["accel"] < F["min_accel"]: return "no_acceleration"
    return entry_window(f)

def classify_tier(s, mint):
    """Burned if the dominant pool's LP is locked, or the pump.fun AMM itself was burned on migration.
    Never uses max(lpLockedPct): a $0.03 side-pool at 100% must not hide an unlocked creator pool."""
    T = C().get("tiers") or {}
    floor = T.get("burned_min_lp_locked_pct", 90)
    if (s.get("lp_locked_pct") or 0) >= floor:
        return "burned"
    launch = s.get("launchpad")
    lname = (launch.get("name") if isinstance(launch, dict) else launch) or ""
    pump_origin = str(mint or "").endswith("pump") or "pump" in str(lname).lower()
    if pump_origin and (s.get("pump_amm_lp_locked_pct") or 0) >= floor:
        return "burned"
    return "creator_pool"

def rank(f):
    bs = min(3, f["buys_m5"] / max(1, f["sells_m5"]))
    mom = 1 - abs(f["pc_m5"] - 10) / 25           # sweet spot ~+10% in 5 min
    liq = min(1, (f["liq"] or 0) / max(1, f["mcap"]) / 0.15)
    return round(30 * (bs - 1) / 2 + 25 * max(0, mom) + 25 * min(1, f["accel"] / 3) + 20 * liq, 1)

def scan(c):
    S = C(); E = S["entry"]
    rejects = {}
    def rej(r): rejects[r] = rejects.get(r, 0) + 1
    mints, src, wadded, wl = discover(c)
    pairs = run.ds_tokens(mints)
    wdead = prune_watch(c, pairs)
    open_rows = c.execute("SELECT mint FROM positions WHERE status='open'").fetchall()
    open_mints = {r["mint"] for r in open_rows}
    open_syms = {(r["symbol"] or "").upper() for r in c.execute("SELECT symbol FROM positions WHERE status='open'")}
    cool = iso(now() - datetime.timedelta(minutes=S["reentry_cooldown_min"]))
    recent = {r["mint"] for r in c.execute("SELECT mint FROM positions WHERE strategy='scalp' AND opened_at>?", (cool,))}
    stage1 = []
    for m in mints:
        p = pairs.get(m)
        if not p: rej("no_pair_data"); continue
        if m in open_mints or m in recent: rej("open_or_cooldown"); continue
        if ((p.get("baseToken") or {}).get("symbol") or "").upper() in open_syms: rej("same_symbol_open(copycat/dup)"); continue
        f = feats(p); r = market_filter(f)
        if r: rej(r); continue
        f["rank"] = rank(f); stage1.append((m, f))
    stage1.sort(key=lambda x: -x[1]["rank"])
    seen_sym = set(); dedup = []
    for m, f in stage1:   # one token per ticker per scan (copycats share tickers)
        k = (f["symbol"] or "").upper()
        if k in seen_sym: rej("same_symbol_in_scan"); continue
        seen_sym.add(k); dedup.append((m, f))
    # Graduates (mint ends with "pump") are the burned-LP names. Check them before creator pools
    # so the per-scan RugCheck budget is not spent on a tier that is disabled.
    stage1 = sorted(dedup, key=lambda x: (not str(x[0]).endswith("pump"), -x[1]["rank"]))
    n_open = c.execute("SELECT COUNT(*) FROM positions WHERE status='open' AND strategy='scalp'").fetchone()[0]
    opened = 0; safe = 0; checks = 0
    for m, f in stage1:
        if opened >= S["max_new_per_scan"] or n_open >= S["max_concurrent"]: rej("slots_full"); continue
        if checks >= S["max_rugchecks_per_scan"]: rej("rugcheck_budget"); continue
        checks += 1
        rc = rugcheck_cached(c, m)
        if not rc: rej("rugcheck_unavailable"); continue
        s = run.safety_features(rc, m)
        r = run.safety_filter(s, S["safety"])
        if r:
            rej(r); log(f"  [scalp] reject {f['symbol']:<10} {r} (top10 {s['top10_ex_pools']}% top1 {s['top1_ex_pools']}% holders {s['holders']} insiders {s['graph_insiders']})"); continue
        if s["decimals"] is None: rej("no_decimals"); continue
        T = S.get("tiers") or {}
        tier = classify_tier(s, m)
        TT = T.get(tier, {})
        if TT.get("enabled") is False: rej(f"tier_disabled:{tier}"); continue
        n_tier = sum(1 for r in c.execute("SELECT features FROM positions WHERE status='open' AND strategy='scalp'")
                     if (json.loads(r["features"] or "{}").get("tier") or "creator_pool") == tier)
        if n_tier >= TT.get("max_concurrent", S["max_concurrent"]): rej(f"tier_slots_full:{tier}"); continue
        safe += 1
        cur_cash = run.cash(c)
        size = TT.get("position_size_usd", S["position_size_usd"]); fee = run.fee_usd()
        if cur_cash - size - fee < S["min_cash_reserve_usd"]: rej("no_cash"); continue
        jp = run.jup_prices([m]).get(m)
        if not jp: rej("no_jupiter_price"); continue
        div = 100 * (jp / f["price"] - 1)
        if abs(div) > E["max_mark_divergence_pct"]: rej("mark_divergence"); log(f"  [scalp] skip {f['symbol']} Jupiter vs DexScreener {div:+.1f}%"); continue
        lamports = int(size / run.sol_price() * 1e9)
        qb = run.jup_quote(SOL, m, lamports)
        if not qb: rej("no_buy_route"); continue
        impact = float(qb.get("priceImpactPct") or 0) * 100
        if impact > E["max_price_impact_pct"]: rej("price_impact"); log(f"  [scalp] skip {f['symbol']} buy impact {impact:.2f}%"); continue
        raw = int(qb["outAmount"])
        qs = run.jup_quote(m, SOL, raw)
        if not qs: rej("no_sell_route_honeypot?"); log(f"  [scalp] skip {f['symbol']} NO SELL ROUTE (possible honeypot)"); continue
        rt_loss = 100 * (1 - int(qs["outAmount"]) / lamports)
        if rt_loss > E["max_roundtrip_quote_loss_pct"]: rej("roundtrip_loss"); log(f"  [scalp] skip {f['symbol']} instant round-trip quote loss {rt_loss:.1f}%"); continue
        CO = run.CFG["costs"]
        tokens = raw / 10 ** s["decimals"] * (1 - CO["extra_slippage_pct_each_side"] / 100) * (1 - CO.get("wallet_swap_fee_pct", 0) / 100)
        eff = size / tokens
        entry_cost = 100 * (eff / jp - 1)
        if entry_cost > E["max_total_entry_cost_pct"]: rej("entry_cost_too_high"); log(f"  [scalp] skip {f['symbol']} entry cost {entry_cost:.1f}%"); continue
        feat = {**f, "price_ds": f["price"], "price": jp, "impact": impact, "roundtrip_quote_loss": round(rt_loss, 2), "entry_cost_pct": round(entry_cost, 2),
                **{k: s[k] for k in ["top10_ex_pools", "top1_ex_pools", "creator_pct", "holders", "graph_insiders", "lp_locked_pct", "pump_amm_lp_locked_pct", "rc_score_norm", "risks", "launchpad"]},
                "sources": src.get(m), "tier": tier}
        reasoning = (f"[scalp {tier}] rank {f['rank']} | age {f['age_min']:.0f}m dex {f['dex']} mcap ${f['mcap']:,.0f} liq ${(f['liq'] or 0):,.0f} | 5m: vol ${f['vol_m5']:,.0f} "
                     f"buys/sells {f['buys_m5']}/{f['sells_m5']} chg {f['pc_m5']}% accel x{f['accel']} | 1h chg {f['pc_h1']}% | holders {s['holders']} top10 {s['top10_ex_pools']}% "
                     f"top1 {s['top1_ex_pools']}% insiders {s['graph_insiders']} | impact {impact:.2f}% roundtrip-quote loss {rt_loss:.1f}% entry cost {entry_cost:.1f}% | src {src.get(m)}")
        run.set_cash(c, run.cash(c) - size - fee)   # re-read: intra-scan monitoring may have closed positions meanwhile
        cur = c.execute("""INSERT INTO positions(mint,symbol,name,pair,dex,opened_at,entry_mark,entry_eff,tokens,tokens_left,decimals,
            cost_usd,fees_usd,entry_liq,entry_mcap,score,features,reasoning,status,peak_mark,last_mark,last_checked,strategy)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?,'scalp')""",
            (m, f["symbol"], f["name"], f["pair"], f["dex"], iso(), jp, eff, tokens, tokens, s["decimals"], size, fee,
             f["liq"] or 0, f["mcap"], f["rank"], json.dumps(feat, default=str), reasoning, jp, jp, iso()))
        c.execute("INSERT INTO fills(pos_id,ts,side,tokens,usd,mark,eff_price,impact_pct,fee_usd,reason,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (cur.lastrowid, iso(), "BUY", tokens, size, jp, eff, impact, fee, "scalp_entry", "jupiter_quote"))
        c.commit()
        opened += 1; n_open += 1
        STATUS["last_open"] = {"id": cur.lastrowid, "symbol": f["symbol"], "tier": tier, "ts": iso()}
        log(f"  [scalp] OPEN #{cur.lastrowid} {f['symbol']} ${size:.2f} @ {jp:.8g} (eff {eff:.8g}, +{entry_cost:.1f}%) | {reasoning}")
    c.execute("INSERT INTO scalp_scans VALUES(?,?,?,?,?,?)", (iso(), len(mints), len(stage1), safe, opened, json.dumps(rejects))); c.commit()
    top = dict(sorted(rejects.items(), key=lambda x: -x[1])[:8])
    STATUS.update({"last_scan": iso(), "universe": len(mints), "watchlist": wl, "momentum_pass": len(stage1), "safety_pass": safe,
                   "opened_last_scan": opened, "top_rejects": top, "candidates": [{"symbol": f["symbol"], "age_min": round(f["age_min"] or 0, 1),
                   "pc_m5": f["pc_m5"], "bs_m5": round(f["buys_m5"] / max(1, f["sells_m5"]), 2), "mcap": f["mcap"]} for _, f in stage1[:5]]})
    log(f"[scalp] SCAN universe {len(mints)} (watchlist {wl}, +{wadded} new, -{wdead} dead) | momentum-pass {len(stage1)} | safety-pass {safe} | opened {opened} | open {n_open}/{S['max_concurrent']} | top rejects {top}")
    return opened

def update(c, force_close_reason=None):
    X = C()["exits"]
    rows = c.execute("SELECT * FROM positions WHERE status='open' AND strategy='scalp'").fetchall()
    if not rows: return {}
    mints = [r["mint"] for r in rows]
    jm = run.jup_prices(mints)
    pairs = run.ds_tokens(mints)
    marks = {}; ticks = []
    for p in rows:
        pr = pairs.get(p["mint"])
        mark = jm.get(p["mint"]) or (float(pr["priceUsd"]) if pr and pr.get("priceUsd") else None)
        if not mark:
            log(f"  [scalp] #{p['id']} {p['symbol']}: no price this tick - holding"); continue
        ref = p["last_mark"] or p["entry_mark"]
        glitch = bool(ref) and mark > ref * C()["exits"].get("glitch_jump_multiple", 5.0)
        if glitch: log(f"  [scalp] #{p['id']} {p['symbol']}: price jumped x{mark/ref:.1f} in one tick - treating as a liquidity pull, peak not updated")
        marks[p["mint"]] = mark
        peak = (p["peak_mark"] or mark) if glitch else max(p["peak_mark"] or mark, mark)
        c.execute("UPDATE positions SET last_mark=?, peak_mark=?, last_checked=? WHERE id=?", (mark, peak, iso(), p["id"]))
        p = c.execute("SELECT * FROM positions WHERE id=?", (p["id"],)).fetchone()
        g = 100 * (mark / p["entry_mark"] - 1); pk = 100 * (peak / p["entry_mark"] - 1)
        held = (now() - datetime.datetime.fromisoformat(p["opened_at"])).total_seconds() / 60
        liq = ((pr or {}).get("liquidity") or {}).get("usd")
        ticks.append(f"{p['symbol']} {g:+.1f}% (pk {pk:+.0f}%, {held:.0f}m)")
        reason = force_close_reason
        tier = (json.loads(p["features"] or "{}").get("tier") or "creator_pool")
        XT = {**X, **((C().get("exits_by_tier") or {}).get(tier) or {})}   # tier overrides on top of the shared exits
        if not reason and glitch:
            reason = "liquidity_pull_suspected"   # price jumped >x5 in one tick = pool drained, quote is meaningless
        if not reason and "tp1_gross_pct" in XT:   # ---- v2/v3/v4 exits ----
            liq_drop = liq is not None and p["entry_liq"] and liq < p["entry_liq"] * (1 - XT["exit_if_liquidity_drop_pct"] / 100)
            _m5 = ((pr or {}).get("txns") or {}).get("m5") or {}
            _sb = XT.get("exit_sells_to_buys_m5")
            sell_spike = bool(_sb) and (_m5.get("sells") or 0) >= XT.get("exit_sell_spike_min_sells", 30) and (_m5.get("sells") or 0) >= _sb * max(1, _m5.get("buys") or 0)
            if liq_drop: reason = "liquidity_drop"
            elif sell_spike: reason = "sell_spike"
            elif not p["tp1_done"]:
                if g <= XT["stop_loss_gross_pct"]: reason = "stop_loss"
                elif g >= XT["runner_take_profit_gross_pct"]: reason = "take_profit_full"
                elif g >= XT["tp1_gross_pct"]:
                    log(f"  [scalp] TP1 #{p['id']} {p['symbol']} ({tier}) gross {g:+.1f}% -> sell {XT['tp1_sell_fraction']*100:.0f}%, stop to +{XT['stop_after_tp1_gross_pct']}%")
                    run.close_part(c, p, XT["tp1_sell_fraction"], mark, "scalp_tp1")
                    c.execute("UPDATE positions SET tp1_done=1 WHERE id=?", (p["id"],))
                elif held >= XT["max_hold_min"]: reason = "max_hold"
                elif held >= XT["time_stop_min"] and g < XT["time_stop_min_gain_pct"]: reason = "time_stop"
            else:
                if g <= XT["stop_after_tp1_gross_pct"]: reason = "runner_breakeven_stop"
                elif g >= XT["runner_take_profit_gross_pct"]: reason = "runner_take_profit"
                elif mark <= peak * (1 - XT["runner_trail_drawdown_pct"] / 100): reason = "runner_trailing_stop"
                elif held >= XT["runner_max_min"]: reason = "runner_max_hold"
        elif not reason:
            if liq is not None and p["entry_liq"] and liq < p["entry_liq"] * (1 - X["exit_if_liquidity_drop_pct"] / 100): reason = "liquidity_drop"
            elif g <= X["stop_loss_gross_pct"]: reason = "stop_loss"
            elif pk >= X["lock_trigger_gross_pct"] and g <= X["lock_stop_gross_pct"]: reason = "profit_lock"
            elif pk >= X["trail_trigger_gross_pct"] and mark <= peak * (1 - X["trail_drawdown_pct"] / 100): reason = "trailing_stop"
            elif g >= X["take_profit_gross_pct"]: reason = "take_profit"
            elif held >= X["max_hold_min"]: reason = "max_hold"
            elif held >= X["time_stop_min"] and g < X["time_stop_min_gain_pct"]: reason = "time_stop"
        if reason:
            p = c.execute("SELECT * FROM positions WHERE id=?", (p["id"],)).fetchone()
            log(f"  [scalp] EXIT #{p['id']} {p['symbol']} {reason}: gross {g:+.1f}% (peak {pk:+.1f}%) held {held:.1f}m")
            if reason == "liquidity_pull_suspected":   # value at most at the last good mark minus a 50% haircut
                run.close_part(c, p, 1.0, ref, "scalp_" + reason, cap_mark=0.5 * ref)
            else:
                run.close_part(c, p, 1.0, mark, "scalp_" + reason)
        c.commit()
    if ticks: log("[scalp] tick: " + " | ".join(ticks))
    return marks

def lesson_line(p):
    f = json.loads(p["features"] or "{}")
    held = (datetime.datetime.fromisoformat(p["closed_at"]) - datetime.datetime.fromisoformat(p["opened_at"])).total_seconds() / 60
    pk = 100 * ((p["peak_mark"] or p["entry_mark"]) / p["entry_mark"] - 1)
    notes = []
    if f.get("pc_m5", 0) > 15: notes.append("entered after >15% 5m candle (late)")
    if f.get("accel", 0) >= 3: notes.append("strong volume acceleration")
    if f.get("buys_m5", 0) / max(1, f.get("sells_m5", 1)) >= 2: notes.append("5m buys >= 2x sells")
    if (f.get("age_min") or 0) < 30: notes.append(f"very fresh ({f.get('age_min',0):.0f}m)")
    if f.get("entry_cost_pct", 0) > 4: notes.append(f"high entry cost {f.get('entry_cost_pct')}%")
    if f.get("dex") == "pumpfun": notes.append("still on bonding curve")
    if pk >= 12 and p["pnl_usd"] <= 0: notes.append(f"was up {pk:.0f}% but gave it back")
    if pk < 2: notes.append("never went green (bad timing/entry at local top)")
    return (f"- {local(p['closed_at'])} | [SCALP] #{p['id']} {p['symbol']} | {'WIN' if p['pnl_usd'] > 0 else 'LOSS'} {p['pnl_pct']:+.1f}% (${p['pnl_usd']:+.2f}) | "
            f"exit {p['exit_reason']} after {held:.0f}m, peak {pk:+.0f}% | age {f.get('age_min',0):.0f}m mcap ${f.get('mcap',0):,.0f} 5m chg {f.get('pc_m5')}% "
            f"accel x{f.get('accel')} b/s {f.get('buys_m5')}/{f.get('sells_m5')} | {', '.join(notes) or 'none notable'}\n")

SF = ["rank", "age_min", "mcap", "pc_m5", "pc_h1", "accel", "bs_m5", "entry_cost_pct", "top10_ex_pools", "holders", "peak_pct"]
def _row(p):
    f = json.loads(p["features"] or "{}")
    return {"rank": p["score"], "age_min": f.get("age_min"), "mcap": f.get("mcap"), "pc_m5": f.get("pc_m5"), "pc_h1": f.get("pc_h1"),
            "accel": f.get("accel"), "bs_m5": f.get("buys_m5", 0) / max(1, f.get("sells_m5", 1)), "entry_cost_pct": f.get("entry_cost_pct"),
            "top10_ex_pools": f.get("top10_ex_pools"), "holders": f.get("holders"),
            "peak_pct": 100 * ((p["peak_mark"] or p["entry_mark"]) / p["entry_mark"] - 1)}

def aggregate_section(c):
    closed = c.execute("SELECT * FROM positions WHERE status='closed' AND strategy='scalp'").fetchall()
    out = ["\n## Aggregate SCALP\n"]
    if len(closed) < 5:
        out.append(f"\nOnly {len(closed)} closed scalps - need >=5 for comparisons.\n"); return "".join(out)
    W = [_row(p) for p in closed if p["pnl_usd"] > 0]; L = [_row(p) for p in closed if p["pnl_usd"] <= 0]
    def avg(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]; return sum(v) / len(v) if v else float("nan")
    out.append(f"\nClosed {len(closed)}: {len(W)} wins / {len(L)} losses, net ${sum(p['pnl_usd'] for p in closed):+.2f}\n\n| feature | avg winners | avg losers |\n|---|---|---|\n")
    for k in SF: out.append(f"| {k} | {avg(W,k):.3g} | {avg(L,k):.3g} |\n")
    reasons = {}
    for p in closed: reasons.setdefault(p["exit_reason"], []).append(p["pnl_usd"])
    out.append("\nExit reasons: " + ", ".join(f"{k}: n={len(v)} sum ${sum(v):+.2f}" for k, v in sorted(reasons.items())) + "\n")
    sugg = []
    for k in ["pc_m5", "entry_cost_pct", "top10_ex_pools"]:
        a, b = avg(W, k), avg(L, k)
        if not (math.isnan(a) or math.isnan(b)) and b > a * 1.3 and b > 0: sugg.append(f"losers had higher {k} ({b:.3g} vs {a:.3g}) -> lower its max")
    for k in ["accel", "bs_m5", "rank", "holders"]:
        a, b = avg(W, k), avg(L, k)
        if not (math.isnan(a) or math.isnan(b)) and a > b * 1.15: sugg.append(f"winners had higher {k} ({a:.3g} vs {b:.3g}) -> raise its min")
    never = sum(1 for r in L if r["peak_pct"] < 2)
    if L and never / len(L) > 0.5: sugg.append(f"{never}/{len(L)} losers never went green -> entries are late; require smaller pc_m5 or wait for pullback")
    gave = sum(1 for r in L if r["peak_pct"] >= 10)
    if gave >= 2: sugg.append(f"{gave} losers were up >=10% first -> lower lock/trail triggers")
    out.append("\nSuggested tuning:\n" + ("".join(f"- {s}\n" for s in sugg) or "- none yet\n"))
    return "".join(out)

if __name__ == "__main__":
    c = run.db(); cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "scan": scan(c)
    elif cmd == "update": update(c)
    else: run.report(c)
