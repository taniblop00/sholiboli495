"""v8 paper book: 5-minute opening-range fade on deep Solana pairs.

Simulation only. Reads GeckoTerminal candles and Jupiter quotes. Never signs,
builds, or sends a swap. A position is opened and closed at the quote. Exit
triggers use that sell quote, and the quote is the fill — no second slippage
or wallet haircut is stacked on top. Priority/network fee is added once per side.
"""
import datetime, json, time
import run

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
STRATEGY = "orb_fade_30m"
_IN_UPDATE = False

STATUS = {"last_scan": None, "universe": 0, "watchlist": 0, "momentum_pass": 0, "safety_pass": 0,
          "opened_last_scan": 0, "top_rejects": {}, "candidates": []}


def book():
    return run.CFG["scalp"]["liquid"]


def priority_fee_usd():
    """Chain fee that is NOT inside the Jupiter quote. Counted once per fill."""
    px = run.sol_price()
    prio = float(book().get("priority_fee_sol_per_tx", 0.00005))
    base = float(run.CFG["costs"].get("network_base_fee_sol_per_tx", 5e-6))
    return (prio + base) * px


def orb_fade_signal(highs, lows, closes, lookback):
    """True when the last bar wicks the prior `lookback` low and closes back inside that range.
    The caller must pass only closed bars. The last bar is the signal bar."""
    if lookback < 2 or len(closes) < lookback + 1:
        return False
    rh = max(highs[-(lookback + 1):-1])
    rl = min(lows[-(lookback + 1):-1])
    if not (rh > rl > 0):
        return False
    return lows[-1] <= rl and closes[-1] > rl and closes[-1] < rh


def exit_decision(entry_eff, sell_eff, held_s, tp, sl, hold_s):
    """Decide from the sell-quote return versus the buy-quote fill. The pool mark is not an input.
    Returns a reason, or None to keep the position. A missing quote never triggers."""
    if not entry_eff or not sell_eff or entry_eff <= 0 or sell_eff <= 0:
        return None
    ret = sell_eff / entry_eff - 1.0
    if ret >= tp:
        return "quote_take_profit"
    if ret <= -abs(sl):
        return "quote_stop"
    if held_s >= hold_s:
        return "quote_time_stop"
    return None


def closed_bars(rows, bar_seconds, now_s=None):
    """Drop the candle that is still forming. Rows are [ts, o, h, l, c, v], any order."""
    now_s = time.time() if now_s is None else now_s
    rows = sorted(rows, key=lambda r: r[0])
    if rows and now_s - float(rows[-1][0]) < bar_seconds:
        rows = rows[:-1]
    return rows


def _impact(q):
    try:
        return float(q.get("priceImpactPct") or 0) * 100
    except (TypeError, ValueError):
        return None


def quote_buy(token, usd):
    """Tokens out for `usd` of the quote asset. No haircut on top of the quote.
    Returns (tokens, eff_price, impact_pct, source) or None."""
    if token["quote"] == "USDC":
        raw = int(round(usd * 1_000_000))
        q = run.jup_quote(USDC, token["mint"], raw, slippage_bps=50)
    else:
        raw = int(round(usd / run.sol_price() * 1e9))
        q = run.jup_quote(run.SOL, token["mint"], raw, slippage_bps=50)
    if not q or not q.get("outAmount"):
        return None
    tokens = int(q["outAmount"]) / 10 ** int(token["decimals"])
    if tokens <= 0:
        return None
    return tokens, usd / tokens, _impact(q), "jupiter_quote"


def quote_sell(token, tokens):
    """USD out for selling `tokens`. No haircut on top of the quote.
    Returns (usd, eff_price, impact_pct, source) or None."""
    raw = int(round(float(tokens) * 10 ** int(token["decimals"])))
    if raw < 1:
        return None
    if token["quote"] == "USDC":
        q = run.jup_quote(token["mint"], USDC, raw, slippage_bps=50)
        if not q or not q.get("outAmount"):
            return None
        usd = int(q["outAmount"]) / 1_000_000
    else:
        q = run.jup_quote(token["mint"], run.SOL, raw, slippage_bps=50)
        if not q or not q.get("outAmount"):
            return None
        usd = int(q["outAmount"]) / 1e9 * run.sol_price()
    if usd <= 0 or tokens <= 0:
        return None
    return usd, usd / float(tokens), _impact(q), "jupiter_quote"


def _token_by_mint(mint):
    for t in book()["tokens"]:
        if t["mint"] == mint:
            return t
    return None


def _ohlcv(pool, limit=40):
    url = (f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}"
           f"/ohlcv/minute?aggregate=5&limit={limit}&currency=usd")
    data = run.get(url, retries=2)
    return (data.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []


def _book_close(c, p, sell_usd, sell_eff, impact, src, reason):
    fee = priority_fee_usd()
    net = max(0.0, sell_usd - fee)
    run.set_cash(c, run.cash(c) + net)
    proceeds = (p["proceeds_usd"] or 0) + net
    c.execute("""INSERT INTO fills(pos_id,ts,side,tokens,usd,mark,eff_price,impact_pct,fee_usd,reason,source)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (p["id"], run.iso(), "SELL", p["tokens_left"], net, sell_eff, sell_eff, impact, fee, reason, src))
    invested = (p["cost_usd"] or 0) + (p["fees_usd"] or 0)
    pnl = proceeds - invested
    c.execute("""UPDATE positions SET tokens_left=0, proceeds_usd=?, status='closed', closed_at=?, exit_reason=?,
                 pnl_usd=?, pnl_pct=?, last_mark=?, last_checked=? WHERE id=?""",
              (proceeds, run.iso(), reason, pnl, (100 * pnl / invested) if invested else 0, sell_eff, run.iso(), p["id"]))
    run.log(f"  CLOSE #{p['id']} {p['symbol']} {reason} quote ${sell_usd:.4f} fee ${fee:.4f} net ${net:.4f} PnL ${pnl:+.4f} ({100*pnl/invested if invested else 0:+.2f}%)")
    return pnl


def update(c, force_close_reason=None):
    """Re-quote every open v8 position and exit only on that sell quote.
    Re-entry is ignored: a quote HTTP call ticks the loop, and a second update
    would book the same sell twice."""
    global _IN_UPDATE
    if _IN_UPDATE:
        return
    _IN_UPDATE = True
    try:
        _update_open(c, force_close_reason)
    finally:
        _IN_UPDATE = False


def _update_open(c, force_close_reason=None):
    L = book()
    tp = float(L["tp_pct"]) / 100.0
    sl = float(L["sl_pct"]) / 100.0
    hold_s = float(L["max_hold_min"]) * 60
    rows = c.execute("SELECT * FROM positions WHERE status='open' AND strategy=?", (STRATEGY,)).fetchall()
    if not rows and not force_close_reason:
        return
    run.log(f"LIQUID UPDATE {len(rows)} open")
    for p in rows:
        token = _token_by_mint(p["mint"])
        if token is None:
            token = {"mint": p["mint"], "symbol": p["symbol"], "decimals": p["decimals"], "quote": "SOL"}
        opened = datetime.datetime.fromisoformat(p["opened_at"])
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=datetime.timezone.utc)
        held_s = (run.now() - opened).total_seconds()
        q = quote_sell(token, p["tokens_left"])
        if not q:
            run.log(f"  #{p['id']} {p['symbol']}: no sell quote — holding (exits are not marked to a price)")
            continue
        sell_usd, sell_eff, impact, src = q
        peak = max(p["peak_mark"] or sell_eff, sell_eff)
        c.execute("UPDATE positions SET last_mark=?, peak_mark=?, last_checked=? WHERE id=?",
                  (sell_eff, peak, run.iso(), p["id"]))
        ret = sell_eff / p["entry_eff"] - 1.0 if p["entry_eff"] else 0
        reason = force_close_reason or exit_decision(p["entry_eff"], sell_eff, held_s, tp, sl, hold_s)
        run.log(f"  #{p['id']} {p['symbol']} quote {100*ret:+.2f}% vs fill, held {held_s/60:.1f}m"
                + (f" -> {reason}" if reason else ""))
        if reason:
            _book_close(c, p, sell_usd, sell_eff, impact, src, reason)
    c.commit()


def scan(c):
    """One signal check per token on the latest closed 5m bar. Enter at the buy quote."""
    L = book()
    lookback = max(2, int(round(float(L["lookback_min"]) / 5)))
    bar_s = 300
    size = float(L["position_size_usd"])
    reserve = float(L.get("min_cash_reserve_usd", 2))
    max_n = int(L.get("max_concurrent", 4))
    max_rt = float(L.get("max_entry_roundtrip_loss_pct", 0.45)) / 100.0
    rejects = {}

    def rej(k):
        rejects[k] = rejects.get(k, 0) + 1

    open_rows = c.execute("SELECT mint FROM positions WHERE status='open'").fetchall()
    open_mints = {r["mint"] for r in open_rows}
    n_open = c.execute("SELECT COUNT(*) FROM positions WHERE status='open' AND strategy=?", (STRATEGY,)).fetchone()[0]
    signals = []
    for token in L["tokens"]:
        try:
            raw = _ohlcv(token["pool"])
        except Exception as e:
            rej("no_ohlcv")
            run.log(f"  {token['symbol']}: ohlcv failed {e}")
            continue
        bars = closed_bars(raw, bar_s)
        if len(bars) < lookback + 1:
            rej("short_history")
            continue
        highs = [float(b[2]) for b in bars]
        lows = [float(b[3]) for b in bars]
        closes = [float(b[4]) for b in bars]
        sig_ts = int(bars[-1][0])
        if not orb_fade_signal(highs, lows, closes, lookback):
            rej("no_signal")
            continue
        if token["mint"] in open_mints:
            rej("already_open")
            continue
        used = c.execute("SELECT v FROM meta WHERE k=?", (f"v8_bar_{token['mint']}",)).fetchone()
        if used and used[0] == str(sig_ts):
            rej("same_bar")
            continue
        signals.append((token, sig_ts, closes[-1], lows[-1]))
    opened = 0
    passed_quote = 0
    cands = []
    for token, sig_ts, close, low in signals:
        if n_open >= max_n:
            rej("slots_full")
            continue
        fee = priority_fee_usd()
        if run.cash(c) - size - fee < reserve:
            rej("no_cash")
            continue
        bought = quote_buy(token, size)
        if not bought:
            rej("no_buy_quote")
            continue
        tokens, eff, impact, src = bought
        sold = quote_sell(token, tokens)
        if not sold:
            rej("no_sell_quote")
            continue
        sell_usd, sell_eff, simpact, ssrc = sold
        rt = sell_usd / size - 1.0
        if rt < -max_rt:
            rej("roundtrip_loss")
            run.log(f"  skip {token['symbol']} quote round-trip {100*rt:.2f}% (limit -{100*max_rt:.2f}%)")
            c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (f"v8_bar_{token['mint']}", str(sig_ts)))
            continue
        passed_quote += 1
        cands.append({"symbol": token["symbol"], "strategy": L.get("label") or STRATEGY,
                      "rt_pct": round(100 * rt, 3)})
        reasoning = (f"{L.get('label') or STRATEGY} 5m fade of the prior {L['lookback_min']}m low. "
                     f"signal bar {sig_ts} close {close:.8g} low {low:.8g}. "
                     f"buy quote eff {eff:.8g} impact {impact}. immediate sell quote {100*rt:.3f}% vs cost. "
                     f"Exits are this sell quote, TP +{L['tp_pct']}% SL -{L['sl_pct']}% hold {L['max_hold_min']}m.")
        feats = {"strategy_label": L.get("label") or STRATEGY, "pool": token["pool"], "quote": token["quote"],
                 "signal_ts": sig_ts, "liq": token.get("liq_usd"), "tier": "liquid",
                 "signal_close": close, "signal_low": low, "entry_rt_pct": round(100 * rt, 3)}
        run.set_cash(c, run.cash(c) - size - fee)
        cur = c.execute("""INSERT INTO positions(mint,symbol,name,pair,dex,opened_at,entry_mark,entry_eff,tokens,tokens_left,decimals,
            cost_usd,fees_usd,entry_liq,entry_mcap,score,features,reasoning,status,peak_mark,last_mark,last_checked,strategy)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?,?)""",
            (token["mint"], token["symbol"], token["symbol"], token["pool"], "jupiter", run.iso(),
             eff, eff, tokens, tokens, int(token["decimals"]), size, fee, token.get("liq_usd"), None, None,
             json.dumps(feats), reasoning, max(eff, sell_eff), sell_eff, run.iso(), STRATEGY))
        c.execute("""INSERT INTO fills(pos_id,ts,side,tokens,usd,mark,eff_price,impact_pct,fee_usd,reason,source)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                  (cur.lastrowid, run.iso(), "BUY", tokens, size, eff, eff, impact, fee, "entry", src))
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (f"v8_bar_{token['mint']}", str(sig_ts)))
        opened += 1
        n_open += 1
        open_mints.add(token["mint"])
        run.log(f"  OPEN #{cur.lastrowid} {token['symbol']} ${size:.2f} quote eff {eff:.8g} rt {100*rt:.3f}% via {src}")
    c.execute("INSERT INTO scalp_scans(ts,universe,market_pass,safety_pass,opened,rejects) VALUES(?,?,?,?,?,?)",
              (run.iso(), len(L["tokens"]), len(signals), passed_quote, opened, json.dumps(rejects)))
    c.commit()
    STATUS.update(last_scan=run.iso(), universe=len(L["tokens"]), watchlist=len(L["tokens"]),
                  momentum_pass=len(signals), safety_pass=passed_quote, opened_last_scan=opened,
                  top_rejects=dict(sorted(rejects.items(), key=lambda kv: -kv[1])[:8]), candidates=cands)
    run.log(f"LIQUID SCAN tokens {len(L['tokens'])} signals {len(signals)} quoted {passed_quote} opened {opened} rejects {rejects}")
    return opened
