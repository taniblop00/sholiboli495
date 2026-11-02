#!/usr/bin/env python3
"""Exports the PAPER engine state to docs/data/state.json for the dashboard (GitHub Pages / raw URL).
Read-only on the DB. Written atomically (tmp file + rename). Simulation only - no real trades exist."""
import json, os, time, datetime, statistics
import run

OUT_DIR = os.path.join(run.BASE, "docs", "data")
OUT = os.path.join(OUT_DIR, "state.json")
MAX_EQ_POINTS = 1500

def _ts(s):
    try: return datetime.datetime.fromisoformat(s).timestamp()
    except Exception: return None

def _stats(rows, hours=None):
    W = [r for r in rows if (r["pnl_usd"] or 0) > 0]; L = [r for r in rows if (r["pnl_usd"] or 0) <= 0]
    gw = sum(r["pnl_usd"] for r in W); gl = -sum(r["pnl_usd"] for r in L)
    out = {"trades": len(rows), "wins": len(W), "losses": len(L),
           "win_rate_pct": round(100 * len(W) / len(rows), 1) if rows else None,
           "profit_factor": (round(gw / gl, 2) if gl > 0 else (None if not W else "inf")),
           "avg_win_pct": round(statistics.mean([r["pnl_pct"] for r in W]), 2) if W else None,
           "avg_loss_pct": round(statistics.mean([r["pnl_pct"] for r in L]), 2) if L else None,
           "net_usd": round(gw - gl, 4),
           "liquidity_pulls": sum(1 for r in rows if "liquidity" in (r["exit_reason"] or "") and (r["pnl_pct"] or 0) < -30)}
    if hours: out["trades_per_hour"] = round(len(rows) / max(hours, 1e-6), 2)
    return out

def build(c, run_info=None, status=None):
    run_info = run_info or {}; status = status or {}
    now = time.time()
    cash = run.cash(c)
    openp = c.execute("SELECT * FROM positions WHERE status='open' ORDER BY opened_at").fetchall()
    open_list = []; open_val = 0.0
    for p in openp:
        mark = p["last_mark"] or p["entry_mark"]; f = json.loads(p["features"] or "{}")
        val = (p["tokens_left"] or 0) * mark
        invested = (p["cost_usd"] or 0) + (p["fees_usd"] or 0)
        est = val + (p["proceeds_usd"] or 0)
        open_val += val
        o = _ts(p["opened_at"]) or now
        open_list.append({"id": p["id"], "symbol": p["symbol"], "name": p["name"], "mint": p["mint"], "pair": p["pair"], "dex": p["dex"],
            "tier": f.get("tier", "creator_pool"), "opened_at": p["opened_at"], "held_min": round((now - o) / 60, 1),
            "entry_price": p["entry_mark"], "last_price": mark, "peak_price": p["peak_mark"], "last_checked": p["last_checked"],
            "gross_pct": round(100 * (mark / p["entry_mark"] - 1), 2) if p["entry_mark"] else None,
            "peak_pct": round(100 * ((p["peak_mark"] or mark) / p["entry_mark"] - 1), 2) if p["entry_mark"] else None,
            "invested_usd": round(invested, 4), "est_value_usd": round(est, 4),
            "live_pnl_usd": round(est - invested, 4), "live_pnl_pct": round(100 * (est / invested - 1), 2) if invested else None,
            "tp1_done": bool(p["tp1_done"]), "dexscreener": f"https://dexscreener.com/solana/{p['pair']}" if p["pair"] else None})
    closed = c.execute("SELECT * FROM positions WHERE status='closed' ORDER BY closed_at DESC").fetchall()
    try: sessions = json.loads((c.execute("SELECT v FROM meta WHERE k='sessions'").fetchone() or ["[]"])[0])
    except Exception: sessions = []
    def sess_of(o):
        name = None
        for sv in sessions:
            if o >= sv["start"]: name = sv["name"]
        return name
    closed_list = []
    for p in closed:
        f = json.loads(p["features"] or "{}"); o, cl = _ts(p["opened_at"]), _ts(p["closed_at"])
        closed_list.append({"id": p["id"], "strategy": p["strategy"], "symbol": p["symbol"], "mint": p["mint"], "dex": p["dex"],
            "tier": f.get("tier"), "session": sess_of(p["opened_at"]), "opened_at": p["opened_at"], "closed_at": p["closed_at"],
            "hold_min": round((cl - o) / 60, 1) if o and cl else None, "invested_usd": round((p["cost_usd"] or 0) + (p["fees_usd"] or 0), 4),
            "pnl_usd": round(p["pnl_usd"] or 0, 4), "pnl_pct": round(p["pnl_pct"] or 0, 2), "exit_reason": (p["exit_reason"] or "").replace("scalp_", ""),
            "entry_price": p["entry_mark"], "exit_price": p["last_mark"],
            "entry": {k: f.get(k) for k in ("age_min", "mcap", "liq", "pc_m5", "pc_h1", "buys_m5", "sells_m5", "holders", "top10_ex_pools", "lp_locked_pct")}})
    eq = c.execute("SELECT ts, equity FROM equity ORDER BY ts").fetchall()
    step = max(1, len(eq) // MAX_EQ_POINTS)
    eq_hist = [{"t": r["ts"], "equity": round(r["equity"], 4)} for r in eq[::step]]
    equity = cash + open_val
    if not eq_hist or eq_hist[-1]["t"] != run.iso(): eq_hist.append({"t": run.iso(), "equity": round(equity, 4)})
    scalp_closed = [p for p in closed if p["strategy"] == "scalp"]
    rs = run_info.get("started_ts")
    this_run = [p for p in scalp_closed if rs and (_ts(p["opened_at"]) or 0) >= rs]
    v = run.CFG["scalp"].get("version"); vs = c.execute("SELECT v FROM meta WHERE k=?", (f"{v}_started",)).fetchone()
    ver_rows = [p for p in scalp_closed if vs and p["opened_at"] >= vs[0]]
    ver_hours = (now - (_ts(vs[0]) or now)) / 3600 if vs else None
    hb = None
    try: hb = open(os.path.join(run.BASE, "heartbeat.txt")).read().strip()
    except Exception: pass
    S = run.CFG["scalp"]
    return {
        "schema": 1, "mode": "PAPER (simulation only - no real trades, no wallet)", "engine_version": v,
        "generated_at": run.iso(), "generated_at_local": run.local_now().strftime("%Y-%m-%d %H:%M:%S"), "timezone": "Asia/Jerusalem",
        "heartbeat": {"ts": run.iso(), "raw": hb},
        "status": {"state": status.get("state", "running"), "phase": status.get("phase"), "message": status.get("message"),
                   "run_started_at": run_info.get("started_at"), "run_ends_at": run_info.get("ends_at"), "runner": run_info.get("runner"),
                   "scanner": {k: v for k, v in (status.get("scanner") or {}).items()}},
        "portfolio": {"equity_usd": round(equity, 4), "cash_usd": round(cash, 4), "open_value_usd": round(open_val, 4),
                      "bankroll_start_usd": run.CFG.get("bankroll_start_usd", 30.0),
                      "pnl_vs_start_pct": round(100 * (equity / run.CFG.get("bankroll_start_usd", 30.0) - 1), 2),
                      "run_start_equity_usd": run_info.get("start_equity")},
        "stats": {"all_time_scalp": _stats(scalp_closed), "all_time_all": _stats(closed),
                  "current_version": {**_stats(ver_rows, ver_hours), "since": vs[0] if vs else None},
                  "this_run": _stats(this_run, (now - rs) / 3600 if rs else None)},
        "sessions": sessions, "open_positions": open_list, "closed_trades": closed_list, "equity_history": eq_hist,
        "rules": {"entry": {k: S["filters"].get(k) for k in ("min_age_min", "max_age_min", "min_buy_sell_ratio_m5", "min_price_change_m5", "max_price_change_m5", "max_price_change_h1", "min_liquidity_usd", "min_mcap_usd", "max_mcap_usd")},
                  "exits": {k: S["exits"].get(k) for k in ("stop_loss_gross_pct", "tp1_gross_pct", "tp1_sell_fraction", "stop_after_tp1_gross_pct", "runner_take_profit_gross_pct", "max_hold_min", "time_stop_min", "runner_max_min")},
                  "exits_by_tier": S.get("exits_by_tier") or {},
                  "tiers": S.get("tiers")},
    }

def export(c, run_info=None, status=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    d = build(c, run_info, status)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f: json.dump(d, f, ensure_ascii=False, separators=(",", ":"), default=str)
    os.replace(tmp, OUT)
    return d

if __name__ == "__main__":
    c = run.db(); d = export(c, status={"state": "idle", "message": "manual export"})
    print(f"wrote {OUT}: equity ${d['portfolio']['equity_usd']:.2f}, {len(d['closed_trades'])} closed, {len(d['open_positions'])} open")
