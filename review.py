#!/usr/bin/env python3
"""Hourly self-review for the PAPER trading loop (simulation only - never trades).
Analyses closed trades, appends dated lessons to lessons.md and makes SMALL, BOUNDED, LOGGED tweaks to
config.json scalp entry/exit parameters. It NEVER loosens anti-rug safety checks (it never writes any
'safety' key) and never moves the scalp market filters below the session floors below. config.strict.json
remains the hard floor for safety settings (verified by safety_floor_ok)."""
import json, os, time, datetime, statistics, math
import run

# Session floors: the self-review may tighten above these but never go below them.
FLOORS = {"min_age_min": 20, "min_mcap_usd": 40000, "min_liquidity_usd": 15000}
# Upper bounds (do not tighten past these - otherwise nothing ever trades).
CAPS = {"min_age_min": 60, "min_mcap_usd": 150000, "min_liquidity_usd": 40000, "min_buy_sell_ratio_m5": 2.0,
        "min_accel": 1.6, "min_price_change_m5": 4.0, "min_vol_m5_usd": 6000}
# Loosening limits (momentum only).
LOOSE_FLOOR = {"min_price_change_m5": 0.0, "min_accel": 0.8, "min_vol_m5_usd": 1000, "min_buy_sell_ratio_m5": 1.1}
EXIT_BOUNDS = {"lock_trigger_gross_pct": (8.0, 15.0), "stop_loss_gross_pct": (-7.0, -5.0)}

def _meta(c, k, default=None):
    r = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default
def _set_meta(c, k, v):
    c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, str(v))); c.commit()

def _feat(p):
    f = json.loads(p["features"] or "{}")
    pk = 100 * ((p["peak_mark"] or p["entry_mark"]) / p["entry_mark"] - 1) if p["entry_mark"] else 0
    return {"age_min": f.get("age_min"), "mcap": f.get("mcap"), "liq": f.get("liq"), "dex": f.get("dex"),
            "pc_m5": f.get("pc_m5"), "accel": f.get("accel"), "bs_m5": (f.get("buys_m5") or 0) / max(1, f.get("sells_m5") or 1),
            "holders": f.get("holders"), "top10": f.get("top10_ex_pools"), "insiders": f.get("graph_insiders"),
            "entry_cost": f.get("entry_cost_pct"), "peak": pk, "pnl_pct": p["pnl_pct"], "reason": p["exit_reason"]}

def _med(rows, k):
    v = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
    return statistics.median(v) if v else float("nan")

def safety_floor_ok(cfg):
    """True if swing safety is at least as strict as config.strict.json on the numeric anti-rug keys we can compare
    (except min_lp_locked_pct / LP-unlocked which the user explicitly allowed)."""
    try: strict = json.load(open(os.path.join(run.BASE, "config.strict.json")))["safety"]
    except Exception: return True, []
    s = cfg["safety"]; bad = []
    for k in ("require_mint_revoked", "require_freeze_revoked", "block_transfer_fee"):
        if strict.get(k) and not s.get(k): bad.append(k)
    for k in ("max_single_holder_pct_ex_pools", "max_creator_pct", "max_insiders_detected"):
        if s.get(k) is not None and strict.get(k) is not None and s[k] > strict[k]: bad.append(k)
    return not bad, bad

def _write_cfg(cfg):
    tmp = run.CFG_PATH + ".tmp"
    json.dump(cfg, open(tmp, "w"), indent=2, ensure_ascii=False); os.replace(tmp, run.CFG_PATH); run.CFG = cfg

def _append_lessons(text):
    txt = open(run.LESSONS).read() if os.path.exists(run.LESSONS) else "<!-- AGGREGATE -->\n"
    head, mark, tail = txt.partition("<!-- AGGREGATE -->")
    if not mark: head, tail = txt, ""
    open(run.LESSONS, "w").write(head.rstrip("\n") + "\n" + text.rstrip("\n") + "\n\n<!-- AGGREGATE -->" + tail)

def review(c, loop_started_ts=None):
    """Entry point used by the loop. NEVER raises: any error is logged and the config is left untouched.
    Bug fixed 2026-11-02: v3 configs fell through to the legacy v1 review, which read exits['lock_trigger_gross_pct']
    (a v1-only key) and crashed with KeyError on every run -> no self-learning happened during the v3 session.
    Now every config with partial-TP exits (v2/v3/v4...) uses review_v2, and the legacy path only runs for real v1 configs."""
    try:
        cfg = json.load(open(run.CFG_PATH))
        X = (cfg.get("scalp") or {}).get("exits") or {}
        if "tp1_gross_pct" in X or str(cfg["scalp"].get("version", "")).lower() not in ("", "v1"):
            return review_v2(c, cfg, loop_started_ts)
        return review_v1(c, cfg, loop_started_ts)
    except Exception as e:
        import traceback
        try: c.rollback()
        except Exception: pass
        run.log("[review] self-review failed safely (config untouched): " + traceback.format_exc().replace("\n", " | ")[-800:])
        return []

def review_v1(c, cfg, loop_started_ts=None):
    S = cfg["scalp"]; F = S["filters"]; X = S["exits"]
    stamp = run.local_now().strftime("%Y-%m-%d %H:%M")
    rows = c.execute("SELECT * FROM positions WHERE status='closed' AND strategy='scalp' ORDER BY closed_at").fetchall()
    allc = c.execute("SELECT * FROM positions WHERE status='closed'").fetchall()
    sig = [r for r in rows if r["exit_reason"] != "scalp_session_end"]   # session-end closes are not strategy signals
    T = [_feat(r) for r in sig]; W = [t for t in T if (t["pnl_pct"] or 0) > 0]; L = [t for t in T if (t["pnl_pct"] or 0) <= 0]
    gw = sum(r["pnl_usd"] for r in allc if r["pnl_usd"] > 0); gl = -sum(r["pnl_usd"] for r in allc if r["pnl_usd"] <= 0)
    pf = gw / gl if gl else float("inf")
    aw = statistics.mean([t["pnl_pct"] for t in W]) if W else 0.0
    al = statistics.mean([t["pnl_pct"] for t in L]) if L else 0.0
    wr = 100 * len(W) / len(T) if T else 0
    since2h = run.iso(run.now() - datetime.timedelta(hours=2))
    entries_2h = c.execute("SELECT COUNT(*) FROM positions WHERE strategy='scalp' AND opened_at>?", (since2h,)).fetchone()[0]
    eq = c.execute("SELECT equity FROM equity ORDER BY ts DESC LIMIT 1").fetchone()
    lines = [f"### Self-review {stamp} Asia/Jerusalem (auto, hourly)",
             f"- All closed: {len(allc)} | profit factor {pf:.2f} | equity ${(eq[0] if eq else 0):.2f}",
             f"- Scalp (excl. session-end): {len(T)} trades, win rate {wr:.0f}%, avg win {aw:+.1f}%, avg loss {al:+.1f}%, scalp entries last 2h: {entries_2h}"]
    if W and L:
        feats = ["age_min", "mcap", "liq", "pc_m5", "accel", "bs_m5", "holders", "top10", "entry_cost", "peak"]
        lines.append("- Median winners vs losers: " + ", ".join(f"{k} {_med(W,k):.3g}/{_med(L,k):.3g}" for k in feats))
        dl = {}
        for t in T: dl.setdefault(t["dex"], [0, 0])[0 if (t["pnl_pct"] or 0) > 0 else 1] += 1
        lines.append("- By dex (wins/losses): " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in dl.items()))
    changes = []
    def tighten(k, step, why):
        old = F[k]; new = min(CAPS[k], round(old + step, 3))
        new = max(new, FLOORS.get(k, new))
        if new != old: F[k] = new; changes.append(f"scalp.filters.{k}: {old} -> {new} ({why})")
    last_tighten = float(_meta(c, "review_last_tighten_ts", 0) or 0)
    n_new_since = c.execute("SELECT COUNT(*) FROM positions WHERE strategy='scalp' AND status='closed' AND closed_at>?",
                            (run.iso(datetime.datetime.fromtimestamp(last_tighten, datetime.timezone.utc)),)).fetchone()[0] if last_tighten else len(sig)
    if len(T) >= 5 and L and W and n_new_since >= 2:
        # 1) losers cluster at low liquidity / young age / low mcap -> raise that minimum one small step
        for k, fk, step in (("liq", "min_liquidity_usd", 2500), ("age_min", "min_age_min", 5), ("mcap", "min_mcap_usd", 10000)):
            ml, mw = _med(L, k), _med(W, k)
            if not (math.isnan(ml) or math.isnan(mw)) and len(L) >= 2 and ml < 0.8 * mw and ml < F[fk] * 1.5:
                tighten(fk, step, f"losers' median {k} {ml:.3g} < 0.8x winners' {mw:.3g}")
        # 2) avg loss > 2x avg win -> tighten entry quality (buy pressure) + stop
        if aw > 0 and abs(al) > 2 * aw:
            tighten("min_buy_sell_ratio_m5", 0.1, f"avg loss {al:.1f}% > 2x avg win {aw:.1f}%")
            lo, hi = EXIT_BOUNDS["stop_loss_gross_pct"]; old = X["stop_loss_gross_pct"]; new = min(hi, max(lo, old + 0.5))
            if new != old: X["stop_loss_gross_pct"] = new; changes.append(f"scalp.exits.stop_loss_gross_pct: {old} -> {new} (avg loss > 2x avg win)")
        # 3) several losers were up >= 10% first -> lock profits earlier
        gave_back = [t for t in L if t["peak"] >= 10]
        if len(gave_back) >= 2:
            lo, hi = EXIT_BOUNDS["lock_trigger_gross_pct"]; old = X["lock_trigger_gross_pct"]; new = max(lo, old - 1)
            if new != old: X["lock_trigger_gross_pct"] = new; changes.append(f"scalp.exits.lock_trigger_gross_pct: {old} -> {new} ({len(gave_back)} losers were up >=10% first)")
        # 4) a dex with >=3 losses and 0 wins -> block it for scalps (tightening only; never block the best dex)
        dexstat = {}
        for t in T: dexstat.setdefault(t["dex"], [0, 0])[0 if (t["pnl_pct"] or 0) > 0 else 1] += 1
        best = max(dexstat, key=lambda d: dexstat[d][0]) if dexstat else None
        for d, (w, l) in dexstat.items():
            if d and w == 0 and l >= 3 and d != best and d not in F.setdefault("blocked_dexes", []):
                F["blocked_dexes"].append(d); changes.append(f"scalp.filters.blocked_dexes += {d} ({l} losses, 0 wins on this dex)")
        if changes: _set_meta(c, "review_last_tighten_ts", time.time())
    # 4) zero entries for 2h (and loop has been running 2h) -> loosen ONE momentum knob a little; never safety/liq/age/mcap
    last_loosen = float(_meta(c, "review_last_loosen_ts", 0) or 0)
    running_2h = loop_started_ts is not None and time.time() - loop_started_ts >= 7200
    if entries_2h == 0 and running_2h and time.time() - last_loosen >= 7200 and not changes:
        for k, step in (("min_accel", -0.1), ("min_price_change_m5", -0.5), ("min_vol_m5_usd", -250), ("min_buy_sell_ratio_m5", -0.05)):
            old = F[k]; new = max(LOOSE_FLOOR[k], round(old + step, 3))
            if new != old:
                F[k] = new; changes.append(f"scalp.filters.{k}: {old} -> {new} (0 scalp entries in last 2h; momentum-only loosening, safety untouched)")
                _set_meta(c, "review_last_loosen_ts", time.time()); break
    ok, bad = safety_floor_ok(cfg)
    if not ok: lines.append(f"- WARNING: swing safety looser than config.strict.json on {bad} - not auto-changed, needs manual review")
    if changes:
        cfg["scalp"]["filters"] = F; cfg["scalp"]["exits"] = X; _write_cfg(cfg)
        lines.append("- Config changes (bounded): " + "; ".join(changes))
    else:
        lines.append("- Config changes: none (" + ("not enough new closed trades since last change" if len(T) >= 5 and n_new_since < 2 else "no rule triggered / sample too small") + ")")
    _set_meta(c, "review_last_run_ts", time.time())
    _append_lessons("\n".join(lines))
    run.log("[review] " + " | ".join(l.lstrip("- #") for l in lines[1:]))
    return changes



def _bounded_ok(before, after):
    """Hard guard for any automatic config write: safety and tier blocks identical; only allowed knobs may change,
    each within the review_v2 bounds; the buy/sell floor may never go below loose_floor."""
    try:
        b, a = before["scalp"], after["scalp"]; R = b.get("review_v2", {})
        if json.dumps(b.get("safety"), sort_keys=True) != json.dumps(a.get("safety"), sort_keys=True): return False, "safety changed"
        if json.dumps(b.get("tiers"), sort_keys=True) != json.dumps(a.get("tiers"), sort_keys=True): return False, "tiers changed"
        if json.dumps(before.get("safety"), sort_keys=True) != json.dumps(after.get("safety"), sort_keys=True): return False, "swing safety changed"
        allowed_f = {"min_price_change_m5", "min_buy_sell_ratio_m5", "min_vol_m5_usd", "min_txns_m5"}
        for k in set(b["filters"]) | set(a["filters"]):
            if b["filters"].get(k) != a["filters"].get(k):
                if k not in allowed_f: return False, f"filters.{k} not allowed"
                lo, hi = R["loose_floor"][k], R["tight_cap"][k]
                if not (lo <= a["filters"][k] <= hi): return False, f"filters.{k} out of bounds"
        for k in set(b["exits"]) | set(a["exits"]):
            if b["exits"].get(k) != a["exits"].get(k):
                if k != "tp1_gross_pct": return False, f"exits.{k} not allowed"
                lo, hi = R["tp1_bounds"]
                if not (lo <= a["exits"][k] <= hi): return False, "tp1 out of bounds"
        return True, ""
    except Exception as e:
        return False, f"guard error {e}"

def review_v2(c, cfg, loop_started_ts=None):
    """v2 self-review. Lessons from v1: the old review re-used the SAME 3 Meteora losses every hour and kept tightening
    age/mcap (confounded with the DEX) until almost nothing traded. v2 rules:
      * only v2 trades count (opened after meta v2_started); evidence is never re-used: a change needs >= N NEW trades
      * ONE knob per review, momentum/exit knobs only; never safety, never age window / DEX / liquidity floor
      * trade-rate floor: if entries/h in the last hour < floor -> loosen one momentum knob (within loose_floor)
      * tighten only when the sample says losers differ from winners on that knob AND rate is above floor."""
    S = cfg["scalp"]; F = S["filters"]; X = S["exits"]; R = S["review_v2"]
    stamp = run.local_now().strftime("%Y-%m-%d %H:%M")
    ver = str(S.get("version", "v2")); mk = f"{ver}_started"
    v2s = _meta(c, mk)
    if not v2s: v2s = run.iso(); _set_meta(c, mk, v2s)   # only trades made under the CURRENT rule version count
    rows = c.execute("SELECT * FROM positions WHERE status='closed' AND strategy='scalp' AND opened_at>=? AND exit_reason!='scalp_session_end' ORDER BY closed_at", (v2s,)).fetchall()
    T = [_feat(r) for r in rows]; W = [t for t in T if (t["pnl_pct"] or 0) > 0]; L = [t for t in T if (t["pnl_pct"] or 0) <= 0]
    aw = statistics.mean([t["pnl_pct"] for t in W]) if W else 0.0; al = statistics.mean([t["pnl_pct"] for t in L]) if L else 0.0
    since1h = run.iso(run.now() - datetime.timedelta(hours=1))
    rate = c.execute("SELECT COUNT(*) FROM positions WHERE strategy='scalp' AND opened_at>? AND opened_at>=?", (since1h, v2s)).fetchone()[0]
    ran = (time.time() - loop_started_ts) / 60 if loop_started_ts else 0
    eq = c.execute("SELECT equity FROM equity ORDER BY ts DESC LIMIT 1").fetchone()
    lines = [f"### Self-review {ver} {stamp} Asia/Jerusalem (auto)",
             f"- {ver} trades {len(T)}: WR {100*len(W)/len(T) if T else 0:.0f}%, avg win {aw:+.1f}%, avg loss {al:+.1f}%, entries last 60 min {rate} (floor {R['min_entries_per_hour_floor']}/h), equity ${(eq[0] if eq else 0):.2f}"]
    if W and L:
        lines.append("- Median winners vs losers: " + ", ".join(f"{k} {_med(W,k):.3g}/{_med(L,k):.3g}" for k in ["age_min","mcap","liq","pc_m5","bs_m5","holders","top10","entry_cost","peak"]))
    changes = []
    last_change = float(_meta(c, "v2_last_change_ts", 0) or 0)
    n_new = sum(1 for r in rows if datetime.datetime.fromisoformat(r["closed_at"]).timestamp() > last_change)
    if ran >= 45 and rate < R["min_entries_per_hour_floor"] and time.time() - last_change > 1800:
        for k, step in (("min_price_change_m5", -1.0), ("min_buy_sell_ratio_m5", -0.1), ("min_vol_m5_usd", -1000), ("min_txns_m5", -10)):
            old = F[k]; new = max(R["loose_floor"][k], round(old + step, 3))
            if new != old: F[k] = new; changes.append(f"{k}: {old} -> {new} (only {rate} entries in last hour < floor; momentum-only loosening)"); break
    elif n_new >= R["min_new_trades_for_change"] and W and L:
        recent = T[-n_new:]; rw = [t for t in recent if (t["pnl_pct"] or 0) > 0]; rl = [t for t in recent if (t["pnl_pct"] or 0) <= 0]
        near_tp1 = [t for t in rl if t["peak"] >= 0.7 * X["tp1_gross_pct"]]
        if len(near_tp1) >= 2:
            lo, hi = R["tp1_bounds"]; old = X["tp1_gross_pct"]; new = max(lo, old - 1)
            if new != old: X["tp1_gross_pct"] = new; changes.append(f"tp1_gross_pct: {old} -> {new} ({len(near_tp1)} recent losers peaked >= 70% of TP1)")
        elif rl and len(rl) / len(recent) > 0.4 and rate >= 2 * R["min_entries_per_hour_floor"]:
            for k, fk, step in (("bs_m5", "min_buy_sell_ratio_m5", 0.1), ("pc_m5", "min_price_change_m5", 1.0)):
                ml, mw = _med(rl, k), _med(rw, k) if rw else float("nan")
                if not (math.isnan(ml) or math.isnan(mw)) and ml < 0.85 * mw:
                    old = F[fk]; new = min(R["tight_cap"][fk], round(old + step, 3))
                    if new != old: F[fk] = new; changes.append(f"{fk}: {old} -> {new} (recent losers' median {k} {ml:.3g} < 0.85x winners' {mw:.3g})"); break
    if changes:
        before = json.load(open(run.CFG_PATH))
        ok, why = _bounded_ok(before, cfg)
        if not ok:
            lines.append(f"- Config change REJECTED by guard ({why}) - nothing written"); changes = []
    if changes:
        _set_meta(c, "v2_last_change_ts", time.time())
        cfg["scalp"]["filters"] = F; cfg["scalp"]["exits"] = X; _write_cfg(cfg)
        lines.append("- Config change (one knob): " + "; ".join(changes))
    else:
        lines.append(f"- Config changes: none ({n_new} new trades since last change; need {R['min_new_trades_for_change']}, or rate below floor after 45 min)")
    _set_meta(c, "review_last_run_ts", time.time())
    _append_lessons("\n".join(lines))
    run.log(f"[review {ver}] " + " | ".join(l.lstrip("- #") for l in lines[1:]))
    return changes


if __name__ == "__main__":
    c = run.db(); print(review(c, loop_started_ts=None))
