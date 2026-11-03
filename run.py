#!/usr/bin/env python3
"""
Meme-coin PAPER TRADING engine (Solana). Simulation only.
This script NEVER signs, sends or builds real transactions. It only reads public market data:
  - DexScreener public API (discovery + prices)
  - GeckoTerminal public API (discovery: trending pools)
  - RugCheck public API (token safety report)
  - Jupiter lite-api (SOL price + swap QUOTES used only to estimate realistic fill/price impact)
Usage:
  python3 run.py scan     # find candidates, open simulated positions
  python3 run.py update   # mark open positions, apply TP/SL/time exits
  python3 run.py report   # performance stats
  python3 run.py cycle    # update + scan + lessons + short summary (for cron, every 30-60 min)
  python3 run.py lessons  # rebuild aggregate lessons section
"""
import json, os, sys, time, math, sqlite3, datetime, traceback, urllib.request, urllib.error, socket
HTTP_HARD_TIMEOUT_S = 10          # hard cap on connect + each socket read for EVERY request
HTTP_MAX_WALL_PER_CALL_S = 30     # total wall budget for one get() incl. retries
socket.setdefaulttimeout(HTTP_HARD_TIMEOUT_S)

# All paths are relative to the repo root (the folder this file lives in) - no machine-specific paths.
# MT_HOME can override the root (e.g. for tests).
BASE = os.environ.get("MT_HOME") or os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "config.json")
DB_PATH = os.path.join(BASE, "state.db")
LESSONS = os.path.join(BASE, "lessons.md")
LOG_DIR = os.path.join(BASE, "logs"); os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, "cycle.log")
LOG_MAX_BYTES = 3_000_000   # rotate so the repo does not grow without bound
SOL = "So11111111111111111111111111111111111111112"
EXCLUDE = {SOL, "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
           "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"}

def now(): return datetime.datetime.now(datetime.timezone.utc)
def iso(dt=None): return (dt or now()).isoformat(timespec="seconds")
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo(os.environ.get("MT_TZ", "Asia/Jerusalem"))   # GitHub runners are UTC; reports stay in the user's zone
except Exception:
    LOCAL_TZ = None
def local_now(): return datetime.datetime.now(LOCAL_TZ) if LOCAL_TZ else datetime.datetime.now()
def local(ts):
    try:
        return datetime.datetime.fromisoformat(ts).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception: return ts

CFG = json.load(open(CFG_PATH))

def log(msg):
    line = f"[{local_now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if os.environ.get("MT_NO_STDOUT") != "1": print(line)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > LOG_MAX_BYTES: os.replace(LOG, LOG + ".1")
        with open(LOG, "a") as f: f.write(line + "\n")
    except Exception: pass

TICK_HOOK = None          # v2: callable run between HTTP calls so open scalps are re-priced even during long scans
_HOOK_BUSY = False
def _maybe_tick():
    global _HOOK_BUSY
    if TICK_HOOK is None or _HOOK_BUSY: return
    _HOOK_BUSY = True
    try: TICK_HOOK()
    except Exception as e: log(f"WARN intra-scan tick failed: {e}")
    finally: _HOOK_BUSY = False

def get(url, timeout=None, retries=2):
    """Public read-only GET. Hard timeout (connect+read) <= HTTP_HARD_TIMEOUT_S per attempt and a total
    wall-clock budget per call, so a stalled server can never block the loop for long."""
    timeout = min(float(timeout or CFG["http"].get("timeout", HTTP_HARD_TIMEOUT_S)), HTTP_HARD_TIMEOUT_S)
    _maybe_tick()
    t0 = time.time(); last = None
    for i in range(retries + 1):
        if time.time() - t0 > HTTP_MAX_WALL_PER_CALL_S: last = (last or "") + " (wall budget exhausted)"; break
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 memetrader-paper/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = b""; 
                while True:   # read in chunks so a trickling response is still bounded by the wall budget
                    chunk = r.read(65536)
                    if not chunk: break
                    body += chunk
                    if time.time() - t0 > HTTP_MAX_WALL_PER_CALL_S + 5: raise TimeoutError("response read exceeded wall budget")
                return json.loads(body.decode())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 429: time.sleep(min(3 + 3 * i, 6)); continue
            if e.code in (400, 404): break
            time.sleep(1.5)
        except Exception as e:
            last = str(e); time.sleep(1.5)
    raise RuntimeError(f"GET failed {url[:90]}: {last}")

# ---------------- DB ----------------
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS positions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT, symbol TEXT, name TEXT, pair TEXT, dex TEXT,
      opened_at TEXT, entry_mark REAL, entry_eff REAL, tokens REAL, tokens_left REAL, decimals INTEGER,
      cost_usd REAL, fees_usd REAL, entry_liq REAL, entry_mcap REAL, score REAL, features TEXT, reasoning TEXT,
      status TEXT, peak_mark REAL, last_mark REAL, last_checked TEXT, tp1_done INTEGER DEFAULT 0, tp2_done INTEGER DEFAULT 0,
      proceeds_usd REAL DEFAULT 0, closed_at TEXT, exit_reason TEXT, pnl_usd REAL, pnl_pct REAL, lesson_done INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS fills(id INTEGER PRIMARY KEY AUTOINCREMENT, pos_id INTEGER, ts TEXT, side TEXT,
      tokens REAL, usd REAL, mark REAL, eff_price REAL, impact_pct REAL, fee_usd REAL, reason TEXT, source TEXT);
    CREATE TABLE IF NOT EXISTS equity(ts TEXT, cash REAL, open_value REAL, equity REAL);
    CREATE TABLE IF NOT EXISTS scans(ts TEXT, universe INTEGER, market_pass INTEGER, safety_pass INTEGER, opened INTEGER, rejects TEXT);
    CREATE TABLE IF NOT EXISTS shadow(id INTEGER PRIMARY KEY AUTOINCREMENT, mint TEXT, symbol TEXT, ts TEXT, mark REAL,
      stage TEXT, reason TEXT, score REAL, mark_6h REAL, mult_6h REAL, checked INTEGER DEFAULT 0);
    """)
    cols = [r[1] for r in c.execute("PRAGMA table_info(positions)")]
    if "strategy" not in cols:
        c.execute("ALTER TABLE positions ADD COLUMN strategy TEXT DEFAULT 'swing'")
        c.execute("UPDATE positions SET strategy='swing' WHERE strategy IS NULL"); c.commit()
    c.execute("CREATE TABLE IF NOT EXISTS rc_cache(mint TEXT PRIMARY KEY, ts REAL, data TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS scalp_scans(ts TEXT, universe INTEGER, market_pass INTEGER, safety_pass INTEGER, opened INTEGER, rejects TEXT)")
    if c.execute("SELECT v FROM meta WHERE k='cash'").fetchone() is None:
        c.execute("INSERT INTO meta VALUES('cash',?)", (str(CFG["bankroll_start_usd"]),))
        c.execute("INSERT INTO meta VALUES('started',?)", (iso(),))
        c.commit()
    return c

def cash(c): return float(c.execute("SELECT v FROM meta WHERE k='cash'").fetchone()[0])
def set_cash(c, v): c.execute("UPDATE meta SET v=? WHERE k='cash'", (str(v),))

# ---------------- market data ----------------
_SOLPX = None
def sol_price():
    global _SOLPX
    if _SOLPX: return _SOLPX
    try:
        d = get(f"https://lite-api.jup.ag/price/v3?ids={SOL}")
        _SOLPX = float(d[SOL]["usdPrice"])
    except Exception:
        d = get(f"https://api.dexscreener.com/tokens/v1/solana/{SOL}")
        _SOLPX = float(d[0]["priceUsd"])
    return _SOLPX

def jup_prices(mints):
    """Jupiter lite price v3 (<=50 ids per call). Returns {mint: usdPrice}. Fresher than DexScreener."""
    out = {}
    mints = list(dict.fromkeys(mints))
    for i in range(0, len(mints), 50):
        try:
            d = get("https://lite-api.jup.ag/price/v3?ids=" + ",".join(mints[i:i + 50]))
            for k, v in (d or {}).items():
                if v and v.get("usdPrice"): out[k] = float(v["usdPrice"])
        except Exception as e: log(f"WARN jupiter price: {e}")
    return out

def ds_tokens(mints):
    """DexScreener batch (chunks of 10: endpoint caps output at 30 pairs). Returns {mint: best_pair_by_liquidity}"""
    out = {}
    mints = list(dict.fromkeys(mints))
    for i in range(0, len(mints), 10):
        chunk = mints[i:i + 10]
        try:
            pairs = get("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(chunk))
        except Exception as e:
            log(f"WARN dexscreener batch failed: {e}"); continue
        for p in pairs or []:
            m = p.get("baseToken", {}).get("address")
            if m not in chunk: continue
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if m not in out or liq > ((out[m].get("liquidity") or {}).get("usd") or 0):
                out[m] = p
        time.sleep(0.3)
    return out

def discover():
    mints, src = [], {}
    def add(m, s):
        if m and m not in EXCLUDE:
            if m not in src: mints.append(m); src[m] = []
            src[m].append(s)
    for path, tag in [("token-profiles/latest/v1", "ds_profile"), ("token-boosts/latest/v1", "ds_boost"),
                      ("token-boosts/top/v1", "ds_boost_top"), ("community-takeovers/latest/v1", "ds_cto")]:
        try:
            for t in get("https://api.dexscreener.com/" + path) or []:
                if t.get("chainId") == "solana": add(t.get("tokenAddress"), tag)
        except Exception as e: log(f"WARN discovery {tag}: {e}")
    for dur in ["1h", "6h"]:
        for page in [1, 2]:
            try:
                d = get(f"https://api.geckoterminal.com/api/v2/networks/solana/trending_pools?duration={dur}&page={page}")
                for p in d.get("data", []):
                    bid = p["relationships"]["base_token"]["data"]["id"]
                    add(bid.split("_", 1)[1], f"gt_trending_{dur}")
            except Exception as e: log(f"WARN geckoterminal trending {dur} p{page}: {e}")
            time.sleep(2.2)
    # graduated pump.fun tokens (PumpSwap) ranked by activity
    for dex in CFG.get("gt_dexes", ["pumpswap"]):
        for sort in ["h24_tx_count_desc", "h24_volume_usd_desc"]:
            for page in [1, 2]:
                try:
                    d = get(f"https://api.geckoterminal.com/api/v2/networks/solana/dexes/{dex}/pools?sort={sort}&page={page}")
                    for p in d.get("data", []):
                        bid = p["relationships"]["base_token"]["data"]["id"]
                        add(bid.split("_", 1)[1], f"gt_{dex}_{sort.split('_')[1]}")
                except Exception as e: log(f"WARN geckoterminal {dex} {sort} p{page}: {e}")
                time.sleep(2.2)
    return mints, src

def rugcheck(mint):
    try:
        r = get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report", timeout=10)
        time.sleep(CFG["http"]["rugcheck_sleep_s"])
        return r
    except Exception as e:
        log(f"WARN rugcheck {mint[:6]}: {e}"); return None

def jup_quote(inp, out, amount_raw, slippage_bps=300):
    try:
        q = get(f"https://lite-api.jup.ag/swap/v1/quote?inputMint={inp}&outputMint={out}&amount={int(amount_raw)}&slippageBps={slippage_bps}&restrictIntermediateTokens=true", retries=1)
        time.sleep(CFG["http"]["jupiter_sleep_s"])
        if "outAmount" in q: return q
    except Exception as e:
        log(f"WARN jupiter quote: {e}")
    return None

# ---------------- analysis ----------------
def market_features(p):
    tx = p.get("txns") or {}; vol = p.get("volume") or {}; pc = p.get("priceChange") or {}
    h1 = tx.get("h1") or {}; info = p.get("info") or {}
    created = p.get("pairCreatedAt")
    age_h = (time.time() * 1000 - created) / 3.6e6 if created else None
    socials = {s.get("type") for s in info.get("socials") or []}
    return {
        "price": float(p.get("priceUsd") or 0), "mcap": p.get("marketCap") or p.get("fdv") or 0,
        "liq": (p.get("liquidity") or {}).get("usd") or 0, "age_h": age_h,
        "vol_h1": vol.get("h1") or 0, "vol_h6": vol.get("h6") or 0, "vol_h24": vol.get("h24") or 0,
        "buys_h1": h1.get("buys") or 0, "sells_h1": h1.get("sells") or 0,
        "pc_m5": pc.get("m5") or 0, "pc_h1": pc.get("h1") or 0, "pc_h6": pc.get("h6") or 0, "pc_h24": pc.get("h24") or 0,
        "dex": p.get("dexId"), "quote": (p.get("quoteToken") or {}).get("symbol"), "pair": p.get("pairAddress"),
        "symbol": (p.get("baseToken") or {}).get("symbol"), "name": (p.get("baseToken") or {}).get("name"),
        "has_twitter": "twitter" in socials, "has_telegram": "telegram" in socials,
        "has_website": bool(info.get("websites")), "boosts": (p.get("boosts") or {}).get("active", 0),
    }

def market_filter(f):
    F = CFG["filters"]
    if f["age_h"] is None: return "no_age"
    if f["age_h"] < F["min_age_hours"]: return "too_young"
    if f["age_h"] > F["max_age_hours"]: return "too_old"
    if f["quote"] not in F["allowed_quote_symbols"]: return "bad_quote"
    if not (F["min_mcap_usd"] <= f["mcap"] <= F["max_mcap_usd"]): return "mcap_range"
    if f["liq"] < F["min_liquidity_usd"]: return "low_liq"
    if f["mcap"] and f["liq"] / f["mcap"] < F["min_liq_to_mcap"]: return "liq_mcap_ratio"
    if f["vol_h1"] < F["min_vol_h1_usd"]: return "low_vol_h1"
    if f["buys_h1"] + f["sells_h1"] < F["min_txns_h1"]: return "low_txns_h1"
    if f["buys_h1"] / max(1, f["sells_h1"]) < F["min_buy_sell_ratio_h1"]: return "sell_pressure"
    if f["pc_h1"] < F["min_price_change_h1"]: return "h1_down"
    if f["pc_h1"] > F["max_price_change_h1"]: return "h1_parabolic"
    if f["pc_h6"] < F["min_price_change_h6"]: return "h6_dump"
    if f["pc_m5"] > F["max_price_change_m5"]: return "m5_spike"
    if f["pc_m5"] < F["min_price_change_m5"]: return "m5_dumping"
    return None

def _lp_value(m):
    """Rank a RugCheck market by the dollars in it, counting unlocked LP too.
    A dust side-pool that is 100% locked must not outrank the real pool."""
    lp = m.get("lp") or {}
    locked = float(lp.get("lpLocked") or 0)
    unlocked = float(lp.get("lpUnlocked") or 0)
    locked_usd = float(lp.get("lpLockedUSD") or 0)
    if locked > 0 and locked_usd > 0:
        return locked_usd * (locked + unlocked) / locked
    if unlocked > 0:
        return unlocked   # unpriced unlocked pool: still larger than a $0.03 lock
    return locked_usd

def lp_locked_pct(markets, prefer_types=None):
    """LP lock of the dominant market, not the max across every side-pool.
    RugCheck often reports a dust Meteora market at 100% next to a creator PumpSwap
    pool at ~0%. max(lpLockedPct) would call that burned. The pool we would trade is
    the one with the money in it. prefer_types (e.g. pump_fun_amm) wins when present."""
    pool = list(markets or [])
    if prefer_types:
        pref = [m for m in pool if (m.get("marketType") or "") in prefer_types]
        if pref:
            pool = pref
    if not pool:
        return 0.0
    best = max(pool, key=_lp_value)
    return float((best.get("lp") or {}).get("lpLockedPct") or 0)

def safety_features(rc, mint):
    known = rc.get("knownAccounts") or {}
    pool_owners = set(known.keys())
    pool_accts = set()
    for m in rc.get("markets") or []:
        for k in ("liquidityA", "liquidityB", "pubkey"):
            if m.get(k): pool_accts.add(m[k])
        for k in ("liquidityAAccount", "liquidityBAccount"):
            if (m.get(k) or {}).get("owner"): pool_owners.add(m[k]["owner"])
    holders = [h for h in (rc.get("topHolders") or [])
               if h.get("owner") not in pool_owners and h.get("address") not in pool_accts]
    top10 = sum(h.get("pct", 0) for h in holders[:10])
    top1 = holders[0]["pct"] if holders else 0
    insiders_top = sum(1 for h in holders[:20] if h.get("insider"))
    supply = ((rc.get("token") or {}).get("supply") or 0)
    creator_pct = 100.0 * (rc.get("creatorBalance") or 0) / supply if supply else 0
    markets = rc.get("markets") or []
    lp_locked = lp_locked_pct(markets)
    pump_amm = lp_locked_pct(markets, prefer_types=("pump_fun_amm", "pump_amm", "pumpswap"))
    tf = rc.get("transferFee") or {}
    return {
        "mint_auth": (rc.get("token") or {}).get("mintAuthority") if rc.get("token") else rc.get("mintAuthority"),
        "freeze_auth": (rc.get("token") or {}).get("freezeAuthority") if rc.get("token") else rc.get("freezeAuthority"),
        "top10_ex_pools": round(top10, 2), "top1_ex_pools": round(top1, 2), "insiders_in_top": insiders_top,
        "graph_insiders": rc.get("graphInsidersDetected") or 0, "creator_pct": round(creator_pct, 3),
        "lp_locked_pct": round(lp_locked, 1), "pump_amm_lp_locked_pct": round(pump_amm, 1),
        "rc_score_norm": rc.get("score_normalised"),
        "holders": rc.get("totalHolders") or 0, "rugged": bool(rc.get("rugged")),
        "risks": [f"{r.get('name')}({r.get('level')})" for r in rc.get("risks") or []],
        "risk_names": [r.get("name") for r in rc.get("risks") or []],
        "danger_risks": [r.get("name") for r in rc.get("risks") or [] if r.get("level") == "danger"],
        "token_program": rc.get("tokenProgram"), "transfer_fee_pct": tf.get("pct") or 0,
        "decimals": (rc.get("token") or {}).get("decimals"), "launchpad": rc.get("launchpad"),
        "deploy_platform": rc.get("deployPlatform"),
        "creator": rc.get("creator") or ((rc.get("token") or {}).get("creator")),
    }

def safety_filter(s, S=None):
    S = S or CFG["safety"]
    if s["rugged"]: return "rugcheck_rugged"
    if S["require_mint_revoked"] and s["mint_auth"]: return "mint_authority_active"
    if S["require_freeze_revoked"] and s["freeze_auth"]: return "freeze_authority_active"
    if s["token_program"] not in S["allowed_token_programs"]: return "odd_token_program"
    if S["block_transfer_fee"] and s["transfer_fee_pct"]: return "transfer_fee"
    dr = [r for r in s["danger_risks"] if r not in S.get("ignore_danger_risks", [])]
    if dr: return "rugcheck_danger:" + dr[0]
    blocked = [r for r in s["risk_names"] if r in S["danger_risk_names_block"]]
    if blocked: return "rugcheck_risk:" + blocked[0]
    if s["top10_ex_pools"] > S["max_top10_pct_ex_pools"]: return "top10_concentrated"
    if s["top1_ex_pools"] > S["max_single_holder_pct_ex_pools"]: return "whale_holder"
    if s["creator_pct"] > S["max_creator_pct"]: return "creator_holds"
    if s["lp_locked_pct"] < S["min_lp_locked_pct"]: return "lp_not_locked"
    if S.get("max_rugcheck_score_normalised") is not None and s["rc_score_norm"] is not None and s["rc_score_norm"] > S["max_rugcheck_score_normalised"]: return "rugcheck_score_high"
    if s["graph_insiders"] > S["max_insiders_detected"]: return "insider_network"
    if s["holders"] < S["min_total_holders"]: return "few_holders"
    return None

def lin(x, lo, hi):
    if hi == lo: return 0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))

def score(f, s):
    W = CFG["scoring"]["weights"]
    comp = {}
    comp["liq_ratio"] = lin(f["liq"] / max(1, f["mcap"]), 0.07, 0.25)
    comp["volume_turnover"] = lin(f["vol_h1"] / max(1, f["liq"]), 0.2, 1.5)
    comp["buy_pressure"] = lin(f["buys_h1"] / max(1, f["sells_h1"]), 1.0, 1.8)
    h1 = f["pc_h1"]
    mom = 1.0 if 10 <= h1 <= 60 else (0.4 + 0.06 * h1 if h1 < 10 else max(0.2, 1 - (h1 - 60) / 90))
    if f["pc_m5"] > 0: mom = min(1.0, mom + 0.1)
    if f["pc_h6"] < 0: mom *= 0.7
    comp["momentum"] = mom
    comp["holders"] = lin(math.log10(max(1, s["holders"])), math.log10(300), math.log10(5000))
    comp["distribution"] = lin(35 - s["top10_ex_pools"], 0, 20)
    comp["socials"] = (f["has_twitter"] + f["has_telegram"] + f["has_website"]) / 3
    total = sum(comp[k] * W[k] for k in W) / sum(W.values()) * 100
    return round(total, 1), {k: round(v, 2) for k, v in comp.items()}

# ---------------- simulated execution ----------------
def fee_usd():
    C = CFG["costs"]
    return (C["priority_fee_sol_per_tx"] + C["network_base_fee_sol_per_tx"]) * sol_price()

def sim_buy(mint, usd, mark, decimals):
    """Returns (tokens, eff_price, impact_pct, source). Uses a real Jupiter QUOTE only (never a swap)."""
    C = CFG["costs"]
    if C["use_jupiter_quote"] and decimals is not None:
        lamports = usd / sol_price() * 1e9
        q = jup_quote(SOL, mint, lamports)
        if q:
            tokens = int(q["outAmount"]) / 10 ** decimals * (1 - C["extra_slippage_pct_each_side"] / 100) * (1 - C.get("wallet_swap_fee_pct", 0) / 100)
            return tokens, usd / tokens, float(q.get("priceImpactPct") or 0) * 100, "jupiter_quote"
    tokens = usd / (mark * (1 + C["fallback_slippage_pct_each_side"] / 100)) * (1 - C.get("wallet_swap_fee_pct", 0) / 100)
    return tokens, usd / tokens, None, "dexscreener_mark+fallback_slippage"

def sim_sell(mint, tokens, mark, decimals):
    C = CFG["costs"]
    if C["use_jupiter_quote"] and decimals is not None and tokens > 0:
        q = jup_quote(mint, SOL, tokens * 10 ** decimals)
        if q:
            usd = int(q["outAmount"]) / 1e9 * sol_price() * (1 - C["extra_slippage_pct_each_side"] / 100) * (1 - C.get("wallet_swap_fee_pct", 0) / 100)
            return usd, float(q.get("priceImpactPct") or 0) * 100, "jupiter_quote"
    if mark and mark > 0:
        return tokens * mark * (1 - C["fallback_slippage_pct_each_side"] / 100) * (1 - C.get("wallet_swap_fee_pct", 0) / 100), None, "dexscreener_mark+fallback_slippage"
    return 0.0, None, "no_route_no_price"

# ---------------- commands ----------------
def open_value(c, marks=None):
    v = 0
    for p in c.execute("SELECT * FROM positions WHERE status='open'"):
        m = (marks or {}).get(p["mint"]) or p["last_mark"] or p["entry_mark"]
        v += p["tokens_left"] * m
    return v

def scan(c):
    log("SCAN start")
    rejects = {}
    def rej(r): rejects[r] = rejects.get(r, 0) + 1
    mints, src = discover()
    log(f"universe: {len(mints)} solana tokens from DexScreener profiles/boosts/CTO + GeckoTerminal trending")
    pairs = ds_tokens(mints)
    open_mints = {r["mint"] for r in c.execute("SELECT mint FROM positions WHERE status='open'")}
    cooldown = now() - datetime.timedelta(hours=CFG["reentry_cooldown_hours"])
    recent = {r["mint"] for r in c.execute("SELECT mint FROM positions WHERE opened_at>? AND strategy='swing'", (iso(cooldown),))}
    stage1 = []
    for m in mints:
        p = pairs.get(m)
        if not p: rej("no_pair_data"); continue
        if m in open_mints or m in recent: rej("already_traded"); continue
        f = market_features(p)
        r = market_filter(f)
        if r: rej(r); continue
        stage1.append((m, f))
    log(f"market filter pass: {len(stage1)}")
    cands = []
    recent_rej = {r["mint"]: r["reason"] for r in c.execute("SELECT mint, reason FROM shadow WHERE stage='safety' AND ts>?", (iso(now() - datetime.timedelta(hours=3)),))}
    for m, f in stage1[:25]:
        if m in recent_rej and not any(k in recent_rej[m] for k in ('LP Unlocked','lp_not_locked')):
            rej("recent_safety_reject"); log(f"  skip {f['symbol']:<10} (safety-rejected <3h ago: {recent_rej[m]})"); continue
        rc = rugcheck(m)
        if not rc: rej("rugcheck_unavailable"); continue
        s = safety_features(rc, m)
        r = safety_filter(s)
        sc, comp = score(f, s) if not r else (None, None)
        if r:
            rej(r); c.execute("INSERT INTO shadow(mint,symbol,ts,mark,stage,reason,score) VALUES(?,?,?,?,?,?,?)",
                              (m, f["symbol"], iso(), f["price"], "safety", r, None))
            log(f"  reject {f['symbol']:<10} {r}  (top10={s['top10_ex_pools']} holders={s['holders']} rc={s['rc_score_norm']} lp={s['lp_locked_pct']})")
            continue
        if sc < CFG["scoring"]["min_score_to_enter"]:
            rej("score_low"); c.execute("INSERT INTO shadow(mint,symbol,ts,mark,stage,reason,score) VALUES(?,?,?,?,?,?,?)",
                                        (m, f["symbol"], iso(), f["price"], "score", "score_low", sc))
            log(f"  reject {f['symbol']:<10} score {sc} {comp}")
            continue
        cands.append((sc, m, f, s, comp))
    cands.sort(key=lambda x: -x[0])
    opened = 0
    n_open = c.execute("SELECT COUNT(*) FROM positions WHERE status='open' AND strategy='swing'").fetchone()[0]
    for sc, m, f, s, comp in cands:
        if opened >= CFG["max_new_positions_per_cycle"] or n_open >= CFG["max_concurrent_positions"]:
            rej("slots_full"); c.execute("INSERT INTO shadow(mint,symbol,ts,mark,stage,reason,score) VALUES(?,?,?,?,?,?,?)",
                                         (m, f["symbol"], iso(), f["price"], "slots", "slots_full", sc)); continue
        cur_cash = cash(c)
        equity = cur_cash + open_value(c)
        # size = smaller of fixed $ size and a % of current equity (shrinks after losses)
        size = min(CFG["position_size_usd"], equity * CFG["position_size_pct_of_equity"])
        fee = fee_usd()
        if cur_cash - size - fee < CFG["min_cash_reserve_usd"]:
            rej("no_cash"); continue
        jp = jup_prices([m]).get(m)
        if jp:
            div = 100 * (jp / f["price"] - 1)
            if abs(div) > CFG["costs"].get("max_mark_divergence_pct", 10):
                rej("stale_or_fast_moving_price"); log(f"  skip {f['symbol']} Jupiter vs DexScreener price diverge {div:+.1f}% (stale data / fast move)"); continue
            f["price_ds"] = f["price"]; f["price"] = jp
        tokens, eff, impact, srcq = sim_buy(m, size, f["price"], s["decimals"])
        if impact is not None and impact > CFG["costs"]["max_entry_price_impact_pct"]:
            rej("price_impact"); log(f"  skip {f['symbol']} impact {impact:.2f}%"); continue
        if 100 * (eff / f["price"] - 1) > CFG["costs"].get("max_total_entry_cost_pct", 7):
            rej("entry_cost_too_high"); log(f"  skip {f['symbol']} effective entry {100*(eff/f['price']-1):.1f}% above mark"); continue
        reasoning = (f"score {sc} | age {f['age_h']:.1f}h mcap ${f['mcap']:,.0f} liq ${f['liq']:,.0f} (liq/mc {f['liq']/max(1,f['mcap']):.2f}) "
                     f"vol1h ${f['vol_h1']:,.0f} buys/sells1h {f['buys_h1']}/{f['sells_h1']} chg m5 {f['pc_m5']}% h1 {f['pc_h1']}% h6 {f['pc_h6']}% | "
                     f"holders {s['holders']} top10(ex-pools) {s['top10_ex_pools']}% top1 {s['top1_ex_pools']}% creator {s['creator_pct']}% "
                     f"LP locked {s['lp_locked_pct']}% rugcheck {s['rc_score_norm']} risks {s['risks']} | sources {src.get(m)}")
        feats = {**f, **{k: v for k, v in s.items() if k not in ('risk_names',)}, "components": comp, "sources": src.get(m)}
        set_cash(c, cur_cash - size - fee)
        cur = c.execute("""INSERT INTO positions(mint,symbol,name,pair,dex,opened_at,entry_mark,entry_eff,tokens,tokens_left,decimals,
            cost_usd,fees_usd,entry_liq,entry_mcap,score,features,reasoning,status,peak_mark,last_mark,last_checked)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?)""",
            (m, f["symbol"], f["name"], f["pair"], f["dex"], iso(), f["price"], eff, tokens, tokens, s["decimals"],
             size, fee, f["liq"], f["mcap"], sc, json.dumps(feats, default=str), reasoning, f["price"], f["price"], iso()))
        c.execute("INSERT INTO fills(pos_id,ts,side,tokens,usd,mark,eff_price,impact_pct,fee_usd,reason,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (cur.lastrowid, iso(), "BUY", tokens, size, f["price"], eff, impact, fee, "entry", srcq))
        opened += 1; n_open += 1
        log(f"  OPEN #{cur.lastrowid} {f['symbol']} ${size:.2f} @mark {f['price']:.8g} eff {eff:.8g} (slip vs mark {100*(eff/f['price']-1):.2f}%, impact {impact}) via {srcq}")
        log(f"       {reasoning}")
    c.execute("INSERT INTO scans VALUES(?,?,?,?,?,?)", (iso(), len(mints), len(stage1), len(cands), opened, json.dumps(rejects)))
    c.commit()
    log(f"SCAN done: universe {len(mints)}, market-pass {len(stage1)}, safety+score pass {len(cands)}, opened {opened}. rejects: {dict(sorted(rejects.items(), key=lambda x:-x[1]))}")
    return opened

def close_part(c, p, frac, mark, reason, cap_mark=None, fill=None):
    """Simulated sell (Jupiter QUOTE only, never a swap).
    fill={usd, impact, source} is the quote for the whole remaining size. It is scaled
    for a partial sell and is not haircut again. cap_mark only blocks a fake profit."""
    tokens = p["tokens_left"] * frac if frac < 0.999 else p["tokens_left"]
    if fill is not None:
        full = p["tokens_left"] or tokens
        usd = float(fill.get("usd") or 0) * ((tokens / full) if full else 0)
        impact = fill.get("impact")
        srcq = fill.get("source") or "jupiter_quote"
    else:
        tier = (json.loads(p["features"] or "{}").get("tier") if p["features"] else None)
        if tier == "bonding_curve" and mark:
            # Same 0.75% sell haircut as the buy. A curve quote is not a Jupiter swap.
            slip = 0.0075
            usd, impact, srcq = tokens * mark * (1 - slip), slip * 100, "curve_mark+1.5pct_roundtrip"
        else:
            usd, impact, srcq = sim_sell(p["mint"], tokens, mark, p["decimals"])
    if cap_mark is not None and usd > tokens * cap_mark:
        usd = tokens * cap_mark; srcq += "+capped_at_last_good_mark"
    fee = fee_usd()
    net = max(0.0, usd - fee)
    set_cash(c, cash(c) + net)
    left = p["tokens_left"] - tokens
    proceeds = (p["proceeds_usd"] or 0) + net
    c.execute("INSERT INTO fills(pos_id,ts,side,tokens,usd,mark,eff_price,impact_pct,fee_usd,reason,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (p["id"], iso(), "SELL", tokens, net, mark, (usd / tokens if tokens else 0), impact, fee, reason, srcq))
    c.execute("UPDATE positions SET tokens_left=?, proceeds_usd=? WHERE id=?", (left, proceeds, p["id"]))
    log(f"  SELL #{p['id']} {p['symbol']} {frac*100:.0f}% reason={reason} net ${net:.2f} (mark {mark:.8g}, x{mark/p['entry_mark']:.2f}) via {srcq}")
    if frac >= 0.999 or left <= 1e-12:
        invested = p["cost_usd"] + p["fees_usd"]
        pnl = proceeds - invested
        c.execute("UPDATE positions SET status='closed', closed_at=?, exit_reason=?, pnl_usd=?, pnl_pct=?, tokens_left=0 WHERE id=?",
                  (iso(), reason, pnl, 100 * pnl / invested, p["id"]))
        log(f"  CLOSED #{p['id']} {p['symbol']} PnL ${pnl:+.2f} ({100*pnl/invested:+.1f}%) reason={reason}")

def update(c):
    E = CFG["exits"]
    rows = c.execute("SELECT * FROM positions WHERE status='open' AND strategy='swing'").fetchall()
    log(f"UPDATE {len(rows)} open swing positions")
    if not rows: return
    pairs = ds_tokens([r["mint"] for r in rows])
    jmarks = jup_prices([r["mint"] for r in rows])
    marks = {}
    for p in rows:
        pr = pairs.get(p["mint"])
        if not pr:
            log(f"  #{p['id']} {p['symbol']}: no DexScreener data this cycle (API issue or pair delisted) - holding"); continue
        f = market_features(pr)
        mark = jmarks.get(p["mint"]) or f["price"]; marks[p["mint"]] = mark
        peak = max(p["peak_mark"] or mark, mark)
        c.execute("UPDATE positions SET last_mark=?, peak_mark=?, last_checked=? WHERE id=?", (mark, peak, iso(), p["id"]))
        p = c.execute("SELECT * FROM positions WHERE id=?", (p["id"],)).fetchone()
        mult = mark / p["entry_mark"]; peak_mult = peak / p["entry_mark"]
        held_h = (now() - datetime.datetime.fromisoformat(p["opened_at"])).total_seconds() / 3600
        log(f"  #{p['id']} {p['symbol']:<10} x{mult:.3f} (peak x{peak_mult:.2f}) held {held_h:.1f}h liq ${f['liq']:,.0f} (entry ${p['entry_liq']:,.0f})")
        sl = 1 + E["stop_loss_pct"] / 100
        if p["tp1_done"] and E["breakeven_after_tp1"]: sl = max(sl, 1.0)
        reason = None
        if f["liq"] < p["entry_liq"] * (1 - E["exit_if_liquidity_drop_pct"] / 100): reason = "liquidity_drop"
        elif mult <= sl: reason = "breakeven_stop" if p["tp1_done"] and sl >= 1.0 else "stop_loss"
        elif peak_mult >= E["trailing_activate_multiple"] and mult <= peak_mult * (1 - E["trailing_drawdown_pct"] / 100): reason = "trailing_stop"
        elif held_h >= E["max_hold_hours"]: reason = "max_hold_time"
        elif held_h >= E["time_stop_hours_if_flat"] and abs(mult - 1) * 100 < E["flat_band_pct"] and not p["tp1_done"]: reason = "time_stop_flat"
        if reason:
            close_part(c, p, 1.0, mark, reason); continue
        if not p["tp1_done"] and mult >= E["tp1_multiple"]:
            close_part(c, p, E["tp1_sell_fraction"], mark, "take_profit_1")
            c.execute("UPDATE positions SET tp1_done=1 WHERE id=?", (p["id"],))
            p = c.execute("SELECT * FROM positions WHERE id=?", (p["id"],)).fetchone()
        if p["tp1_done"] and not p["tp2_done"] and mult >= E["tp2_multiple"]:
            close_part(c, p, E["tp2_sell_fraction"], mark, "take_profit_2")
            c.execute("UPDATE positions SET tp2_done=1 WHERE id=?", (p["id"],))
    c.commit()
    return marks

def check_shadows(c):
    """Learning aid: how did tokens we REJECTED do 6h+ later? (detects over-strict filters)"""
    cutoff = iso(now() - datetime.timedelta(hours=6))
    rows = c.execute("SELECT * FROM shadow WHERE checked=0 AND ts<? LIMIT 60", (cutoff,)).fetchall()
    if not rows: return
    pairs = ds_tokens(list({r["mint"] for r in rows}))
    for r in rows:
        p = pairs.get(r["mint"])
        mk = float(p.get("priceUsd") or 0) if p else 0.0
        c.execute("UPDATE shadow SET checked=1, mark_6h=?, mult_6h=? WHERE id=?", (mk, (mk / r["mark"]) if r["mark"] else None, r["id"]))
    c.commit()

def record_equity(c, marks=None):
    ov = open_value(c, marks); ca = cash(c)
    c.execute("INSERT INTO equity VALUES(?,?,?,?)", (iso(), ca, ov, ca + ov)); c.commit()
    return ca, ov

def lesson_for(p):
    if (p["strategy"] or "swing") == "scalp":
        import scalp; return scalp.lesson_line(p)
    f = json.loads(p["features"] or "{}")
    win = p["pnl_usd"] > 0
    notes = []
    if f.get("pc_h1", 0) > 80: notes.append("entered after a >80% 1h pump (chasing)")
    if f.get("pc_m5", 0) > 10: notes.append("entered on a 5m spike")
    if f.get("top10_ex_pools", 0) > 25: notes.append(f"top10 concentration {f.get('top10_ex_pools')}%")
    if f.get("liq", 0) / max(1, f.get("mcap", 1)) < 0.1: notes.append("thin liquidity vs mcap")
    if f.get("age_h", 0) and f["age_h"] < 3: notes.append(f"very young token ({f['age_h']:.1f}h)")
    if f.get("holders", 0) < 600: notes.append(f"few holders ({f.get('holders')})")
    if f.get("buys_h1", 0) / max(1, f.get("sells_h1", 1)) > 1.5: notes.append("strong 1h buy pressure")
    if not f.get("has_twitter"): notes.append("no X account")
    if "ds_boost" in str(f.get("sources")) or "ds_boost_top" in str(f.get("sources")): notes.append("paid DexScreener boost")
    verdict = "WIN" if win else "LOSS"
    return (f"- {local(p['closed_at'])} | #{p['id']} {p['symbol']} | {verdict} {p['pnl_pct']:+.1f}% (${p['pnl_usd']:+.2f}) | exit: {p['exit_reason']} | "
            f"score {p['score']} | age {f.get('age_h',0):.1f}h mcap ${f.get('mcap',0):,.0f} h1 {f.get('pc_h1')}% | signals: {', '.join(notes) or 'none notable'}\n")

FEATS = ["score", "age_h", "mcap", "liq_mcap", "pc_h1", "pc_m5", "pc_h6", "bs_ratio", "holders", "top10_ex_pools", "rc_score_norm"]
def feat_row(p):
    f = json.loads(p["features"] or "{}")
    return {"score": p["score"], "age_h": f.get("age_h"), "mcap": f.get("mcap"), "liq_mcap": f.get("liq", 0) / max(1, f.get("mcap", 1)),
            "pc_h1": f.get("pc_h1"), "pc_m5": f.get("pc_m5"), "pc_h6": f.get("pc_h6"),
            "bs_ratio": f.get("buys_h1", 0) / max(1, f.get("sells_h1", 1)), "holders": f.get("holders"),
            "top10_ex_pools": f.get("top10_ex_pools"), "rc_score_norm": f.get("rc_score_norm")}

def lessons(c):
    if not os.path.exists(LESSONS):
        open(LESSONS, "w").write("# Paper-trading lessons (auto + manual)\n\nPer-trade notes are appended automatically after each closed trade. "
                                 "The aggregate section is regenerated every cycle. Use it to tune config.json.\n\n## Manual lessons / decisions\n\n"
                                 "## Per-trade log\n\n<!-- AGGREGATE -->\n")
    txt = open(LESSONS).read()
    new = c.execute("SELECT * FROM positions WHERE status='closed' AND lesson_done=0 ORDER BY closed_at").fetchall()
    add = "".join(lesson_for(p) for p in new)
    head, _, _ = txt.partition("<!-- AGGREGATE -->")
    head = head.rstrip("\n") + "\n" + add if add else head.rstrip("\n") + "\n"
    for p in new: c.execute("UPDATE positions SET lesson_done=1 WHERE id=?", (p["id"],))
    closed = c.execute("SELECT * FROM positions WHERE status='closed' AND strategy='swing'").fetchall()
    agg = ["\n<!-- AGGREGATE -->\n## Aggregate SWING (auto-regenerated " + local_now().strftime("%Y-%m-%d %H:%M") + " Asia/Jerusalem)\n"]
    if len(closed) < 5:
        agg.append(f"\nOnly {len(closed)} closed trades - too few for statistical lessons (need >=5, ideally 30+).\n")
    else:
        W = [feat_row(p) for p in closed if p["pnl_usd"] > 0]; L = [feat_row(p) for p in closed if p["pnl_usd"] <= 0]
        agg.append(f"\nClosed {len(closed)}: {len(W)} wins / {len(L)} losses.\n\n| feature | avg winners | avg losers |\n|---|---|---|\n")
        def avg(rows, k):
            v = [r[k] for r in rows if r.get(k) is not None]
            return sum(v) / len(v) if v else float("nan")
        for k in FEATS: agg.append(f"| {k} | {avg(W,k):.3g} | {avg(L,k):.3g} |\n")
        reasons = {}
        for p in closed: reasons.setdefault(p["exit_reason"], []).append(p["pnl_usd"])
        agg.append("\nExit reasons: " + ", ".join(f"{k}: n={len(v)} sum ${sum(v):+.2f}" for k, v in reasons.items()) + "\n")
        sugg = []
        for k in ["pc_h1", "pc_m5", "top10_ex_pools", "age_h"]:
            a, b = avg(W, k), avg(L, k)
            if not (math.isnan(a) or math.isnan(b)) and b > a * 1.3 and b > 0: sugg.append(f"losers had higher {k} ({b:.3g} vs {a:.3g}) -> consider tightening its max filter")
        for k in ["score", "liq_mcap", "holders", "bs_ratio"]:
            a, b = avg(W, k), avg(L, k)
            if not (math.isnan(a) or math.isnan(b)) and a > b * 1.15: sugg.append(f"winners had higher {k} ({a:.3g} vs {b:.3g}) -> consider raising its minimum")
        sl = reasons.get("stop_loss", [])
        if len(sl) >= 3 and len(sl) / len(closed) > 0.5: sugg.append("majority of exits are stop-losses -> entries are late/chasing or SL too tight for 30-60 min polling")
        agg.append("\nSuggested tuning (review manually before changing config.json):\n" + ("".join(f"- {s}\n" for s in sugg) or "- none yet\n"))
    sh = c.execute("SELECT stage, reason, COUNT(*) n, AVG(mult_6h) m, SUM(CASE WHEN mult_6h>=1.5 THEN 1 ELSE 0 END) big, SUM(CASE WHEN mult_6h<0.5 THEN 1 ELSE 0 END) dead FROM shadow WHERE checked=1 GROUP BY stage, reason ORDER BY n DESC").fetchall()
    if sh:
        agg.append("\nRejected-token follow-up (price ~6h+ after rejection):\n\n| stage | reason | n | avg multiple | >=1.5x | <0.5x |\n|---|---|---|---|---|---|\n")
        for r in sh: agg.append(f"| {r['stage']} | {r['reason']} | {r['n']} | {(r['m'] or 0):.2f} | {r['big']} | {r['dead']} |\n")
    try:
        import scalp; agg.append(scalp.aggregate_section(c))
    except Exception as e: agg.append(f"\n(scalp aggregate failed: {e})\n")
    open(LESSONS, "w").write(head + "".join(agg))
    c.commit()

def strat_stats(c, strat, since=None):
    q = "SELECT * FROM positions WHERE status='closed' AND strategy=?" + (" AND closed_at>=?" if since else "") + " ORDER BY closed_at"
    closed = c.execute(q, (strat, since) if since else (strat,)).fetchall()
    wins = [p for p in closed if p["pnl_usd"] > 0]; losses = [p for p in closed if p["pnl_usd"] <= 0]
    gp = sum(p["pnl_usd"] for p in wins); gl = -sum(p["pnl_usd"] for p in losses)
    hold = [ (datetime.datetime.fromisoformat(p["closed_at"]) - datetime.datetime.fromisoformat(p["opened_at"])).total_seconds()/60 for p in closed]
    return (f"{strat.upper()}: closed {len(closed)} | wins {len(wins)} | losses {len(losses)} | win rate {(100*len(wins)/len(closed)) if closed else 0:.0f}% | "
            f"avg win {(sum(p['pnl_pct'] for p in wins)/len(wins)) if wins else 0:+.1f}% | avg loss {(sum(p['pnl_pct'] for p in losses)/len(losses)) if losses else 0:+.1f}% | "
            f"net PnL ${gp-gl:+.2f} | profit factor {(gp/gl) if gl else float('inf'):.2f} | avg hold {(sum(hold)/len(hold)) if hold else 0:.0f} min")

def report(c, short=False):
    closed = c.execute("SELECT * FROM positions WHERE status='closed' ORDER BY closed_at").fetchall()
    openp = c.execute("SELECT * FROM positions WHERE status='open'").fetchall()
    ca = cash(c); ov = open_value(c); eq = ca + ov; start = CFG["bankroll_start_usd"]
    wins = [p for p in closed if p["pnl_usd"] > 0]; losses = [p for p in closed if p["pnl_usd"] <= 0]
    realized = sum(p["pnl_usd"] for p in closed)
    lines = [f"PAPER TRADING REPORT ({local_now().strftime('%Y-%m-%d %H:%M')} Asia/Jerusalem) - simulation only, no real trades",
             f"Bankroll start ${start:.2f} | cash ${ca:.2f} | open positions value (mark) ${ov:.2f} | equity ${eq:.2f} ({100*(eq/start-1):+.1f}%)",
             f"ALL: closed trades {len(closed)} | wins {len(wins)} | losses {len(losses)} | win rate {(100*len(wins)/len(closed)) if closed else 0:.0f}% | realized PnL ${realized:+.2f}",
             strat_stats(c, "swing"), strat_stats(c, "scalp")]
    ns = c.execute("SELECT COUNT(*) FROM positions WHERE strategy='scalp' AND opened_at>=?", (iso(now() - datetime.timedelta(hours=1)),)).fetchone()[0]
    lines.append(f"Scalp entries in last 60 min: {ns}")
    if closed:
        aw = sum(p["pnl_pct"] for p in wins) / len(wins) if wins else 0
        al = sum(p["pnl_pct"] for p in losses) / len(losses) if losses else 0
        best = max(closed, key=lambda p: p["pnl_pct"]); worst = min(closed, key=lambda p: p["pnl_pct"])
        gp = sum(p["pnl_usd"] for p in wins); gl = -sum(p["pnl_usd"] for p in losses)
        lines.append(f"avg win {aw:+.1f}% | avg loss {al:+.1f}% | profit factor {(gp/gl) if gl else float('inf'):.2f} | best {best['symbol']} {best['pnl_pct']:+.1f}% | worst {worst['symbol']} {worst['pnl_pct']:+.1f}%")
    if openp:
        lines.append("Open:")
        for p in openp:
            m = p["last_mark"] or p["entry_mark"]
            val = p["tokens_left"] * m + (p["proceeds_usd"] or 0)
            lines.append(f"  [{p['strategy']}] #{p['id']} {p['symbol']:<10} opened {local(p['opened_at'])} cost ${p['cost_usd']:.2f} | x{m/p['entry_mark']:.2f} vs entry mark | est value ${val:.2f} | score {p['score']}")
    if not short:
        if closed:
            lines.append("Closed:")
            for p in closed:
                lines.append(f"  [{p['strategy']}] #{p['id']} {p['symbol']:<10} {local(p['opened_at'])} -> {local(p['closed_at'])} {p['exit_reason']:<15} ${p['pnl_usd']:+.2f} ({p['pnl_pct']:+.1f}%)")
        eqs = c.execute("SELECT ts, equity FROM equity ORDER BY ts").fetchall()
        if eqs:
            step = max(1, len(eqs) // 20)
            lines.append("Equity curve: " + " -> ".join(f"{local(e['ts'])[5:]} ${e['equity']:.2f}" for e in eqs[::step]))
        sc = c.execute("SELECT COUNT(*), SUM(universe), SUM(market_pass), SUM(safety_pass), SUM(opened) FROM scans").fetchone()
        lines.append(f"Swing scans {sc[0]} | tokens screened {sc[1]} | passed market filter {sc[2]} | passed safety+score {sc[3]} | opened {sc[4]}")
        sc = c.execute("SELECT COUNT(*), SUM(universe), SUM(market_pass), SUM(safety_pass), SUM(opened) FROM scalp_scans").fetchone()
        lines.append(f"Scalp scans {sc[0]} | tokens screened {sc[1]} | passed momentum filter {sc[2]} | passed safety+sell-check {sc[3]} | opened {sc[4]}")
    out = "\n".join(lines); print(out); return out

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cycle"
    if cmd != "report":
        import fcntl
        lockf = open(os.path.join(BASE, ".lock"), "w")
        try: fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: print("another run is in progress - exiting"); return
    c = db()
    try:
        if cmd == "scan": scan(c); record_equity(c)
        elif cmd == "update": m = update(c); record_equity(c, m); lessons(c)
        elif cmd == "report": report(c)
        elif cmd == "lessons": lessons(c)
        elif cmd == "cycle":
            log("=== CYCLE start ===")
            m = update(c); check_shadows(c); scan(c); record_equity(c, m); lessons(c)
            print("\n" + "-" * 60); report(c, short=True)
            log("=== CYCLE end ===")
        else: print(__doc__)
    except Exception:
        log("ERROR " + traceback.format_exc()); raise

if __name__ == "__main__":
    main()
