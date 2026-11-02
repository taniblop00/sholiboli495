"""v8 exits are the Jupiter sell quote. A higher pool mark cannot take profit.
No second slippage haircut is applied. Runs on a temp copy of state.db.
    python tests/test_v8_quote_exit.py
"""
import os, sys, json, shutil, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="mt_v8_")
for f in ("config.json", "config.strict.json", "state.db"):
    if os.path.exists(os.path.join(ROOT, f)):
        shutil.copy(os.path.join(ROOT, f), TMP)
os.environ["MT_HOME"] = TMP
os.environ["MT_NO_STDOUT"] = "1"
sys.path.insert(0, ROOT)
import run, liquid

# --- pure signal and decision (the POSSUM bug was a mark trigger) ---
highs = [10, 10, 10, 10, 10, 10, 9.5]
lows = [9, 9, 8, 9, 9, 9, 7.9]
closes = [9.5, 9.5, 9.2, 9.4, 9.6, 9.5, 8.5]
assert liquid.orb_fade_signal(highs, lows, closes, 6) is True
assert liquid.orb_fade_signal(highs, [9, 9, 8, 9, 9, 9, 8.2], closes, 6) is False  # no wick of the prior low
assert liquid.orb_fade_signal(highs, lows, closes[:-1] + [7.5], 6) is False  # close stays under the range
assert liquid.exit_decision(1.0, 1.011, 60, 0.01, 0.004, 1800) == "quote_take_profit"
assert liquid.exit_decision(1.0, 0.995, 60, 0.01, 0.004, 1800) == "quote_stop"
assert liquid.exit_decision(1.0, 0.997, 60, 0.01, 0.004, 1800) is None
assert liquid.exit_decision(1.0, 0.997, 1800, 0.01, 0.004, 1800) == "quote_time_stop"
assert liquid.exit_decision(1.0, None, 60, 0.01, 0.004, 1800) is None
# mark +10% with a sell quote under the fill is not a take-profit
mark = 1.10
sell = 0.99
assert sell < mark and liquid.exit_decision(1.0, sell, 10, 0.01, 0.004, 1800) == "quote_stop"

# --- booked fill equals the quote minus one priority fee ---
FART = "9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"
liquid.priority_fee_usd = lambda: 0.01
liquid.quote_sell = lambda token, tokens: (2.90, 0.00290, 0.1, "jupiter_quote")
c = run.db()
# buy 1000 tokens at $0.003 = $3. A mark of $0.0033 would be +10%, the quote is -3.3%.
c.execute("""INSERT INTO positions(mint,symbol,name,pair,dex,opened_at,entry_mark,entry_eff,tokens,tokens_left,decimals,
    cost_usd,fees_usd,entry_liq,entry_mcap,score,features,reasoning,status,peak_mark,last_mark,last_checked,strategy)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?,?)""",
    (FART, "FARTCOIN", "FARTCOIN", "pool", "jupiter", run.iso(), 0.0033, 0.003, 1000, 1000, 6,
     3.0, 0.01, 6e6, None, None, json.dumps({"tier": "liquid", "strategy_label": "orb fade 30m"}), "test",
     0.0033, 0.0033, run.iso(), liquid.STRATEGY))
c.commit()
cash_before = run.cash(c)
liquid.update(c)
row = c.execute("SELECT status, exit_reason, pnl_usd, pnl_pct FROM positions WHERE symbol='FARTCOIN' ORDER BY id DESC").fetchone()
fill = c.execute("SELECT usd, eff_price, fee_usd, source FROM fills WHERE side='SELL' ORDER BY id DESC").fetchone()
assert row["status"] == "closed", row
assert row["exit_reason"] == "quote_stop", row
assert row["pnl_usd"] < 0, row
assert abs(fill["usd"] - (2.90 - 0.01)) < 1e-9, fill  # quote minus one fee, no 1.5% haircut
assert fill["source"] == "jupiter_quote"
assert abs((run.cash(c) - cash_before) - (2.90 - 0.01)) < 1e-9

# take-profit only when the quote itself is +1% over the fill
liquid.quote_sell = lambda token, tokens: (3.04, 0.00304, 0.0, "jupiter_quote")
c.execute("""INSERT INTO positions(mint,symbol,name,pair,dex,opened_at,entry_mark,entry_eff,tokens,tokens_left,decimals,
    cost_usd,fees_usd,entry_liq,entry_mcap,score,features,reasoning,status,peak_mark,last_mark,last_checked,strategy)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open',?,?,?,?)""",
    (FART, "FARTCOIN", "FARTCOIN", "pool", "jupiter", run.iso(), 0.003, 0.003, 1000, 1000, 6,
     3.0, 0.01, 6e6, None, None, "{}", "test", 0.003, 0.003, run.iso(), liquid.STRATEGY))
c.commit()
liquid.update(c)
row = c.execute("SELECT status, exit_reason, pnl_usd FROM positions WHERE symbol='FARTCOIN' ORDER BY id DESC").fetchone()
assert row["status"] == "closed" and row["exit_reason"] == "quote_take_profit", row
# proceeds 3.03 vs invested 3.01
assert abs(row["pnl_usd"] - ((3.04 - 0.01) - 3.01)) < 1e-9, row
print("OK v8 quote exits", TMP)
