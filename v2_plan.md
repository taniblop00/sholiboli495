# YONI TRADER – v2 plan (paper trading only)
Written 2026-11-02 08:50 (Asia/Jerusalem). **Paper only:** no real trades, swaps, transfers or signatures. Phantom MCP is not touched.

## 0. Final v1 numbers (from state.db)
- Equity went from $30.00 to **$21.72 (‑27.6%)**, with 23 closed trades, 48% WR, avg win +17.1% vs avg loss ‑34.2%.
- ANAKIN and PIBBLE were already closed on paper at 08:20 by an `update` run:
  - ANAKIN: +55.3% (+$1.85), max_hold
  - PIBBLE: ‑46.1% (‑$1.57), stop
  - Nobody was watching PIBBLE between 04:01 and 08:20, so most of its loss came from the engine being off.
- **Scalps:** 14 trades, 64% WR, ‑$1.11.
- **Swings:** 9 trades, 2 wins, ‑$7.17. Swings account for about 87% of the total loss.

## 1. Post‑mortem – what separated winners from losers
| group | trades | result |
|---|---|---|
| Scalp, **PumpSwap, age 5–14 min, 5m change +10–27%, b/s ≥1.5** | 6 | **6/6 wins**, +9 to +23% net (Anakin, AI×2, Google, VAMP, FAGENT) |
| Scalp, PumpSwap, age ≥20 min / weak 5m momentum (+2–9%) | 5 | 3 small wins (+2, +6, +19), 2 losses (‑3, ‑13). Mostly chop, liquidity‑drop exits at small gains |
| Scalp, **Meteora** (LISA, HEN, BHF) | 3 | **0/3**: ‑9%, ‑40%, ‑100%. This was −$5.25, more than the whole scalp loss |
| Swing (age 1–43 h, polled every 5 min) | 9 | 2/9 wins. GTA6 ‑100%, MIDTERMS ‑58%, PIBBLE ‑46% |

Without Meteora, the scalps were 11 trades, 82% WR, avg loss ‑7.7%, PF 8.6. That is a small sample, so it is a direction to follow, not proof.

### Why the losses were so much bigger than the ‑7% stop
1. **The box suspended while positions were open.** Two of the three ‑100% trades happened during these gaps:
   - **BHF** was at +17% at 22:02:16. The log then shows a 261 s wall‑clock jump. At 22:06:35 the liquidity was gone and the sell quote was 0.
   - **GTA 6 Coin** was a swing. A 333 s gap (00:59 to 01:05) ended with the price at ×0.008.
2. **Scans blocked monitoring.** The loop was single‑threaded, so a scan with many GT calls, 2.1 s sleeps and rugchecks froze position checks for 1–4 min. HEN went from +21% to ‑36% between two ticks about 50 s apart, so the stop filled at ‑36%.
3. **Swings were polled every 300 s.** MIDTERMS fell to ‑54% between two polls.
4. **Costs are about 7–8% per round trip.** I measured this as the gap between the gross exit and net PnL on every scalp. A ‑7% gross stop therefore realises about ‑12 to ‑13%, and a +25% TP realises about +16 to +18%. MOVEMBER entered with a 7.5% instant round‑trip quote loss: ‑12.6% after 6 s.
5. **Meteora‑DBC / "LP unlocked" pools let the creator pull liquidity (BHF).** PumpSwap graduates had the same rugcheck "LP unlocked" flag but none of them rugged. The DEX is the separating feature; the rugcheck LP flag is not.

### Why only 4 scalps overnight
The hourly self‑review kept re‑using the same 3 Meteora losers every hour. Each time it read them as "losers are younger and smaller" and raised min_age 20→30 and min_mcap 40k→70k, even though the real cause (Meteora) was already blocked. That pushed the filters past the profile of **every winner** (age 5–14 min, mcap 15–90k). There was no rule against re‑using the same evidence and no trade‑rate floor.

## 2. Replay / backtest
**A. Exit replay on the 14 real scalp price paths** (cycle.log ticks, gapped fills as observed, 7.5% cost):
| exits | WR | avg win | avg loss | PF |
|---|---|---|---|---|
| v1 actual | 64% | +14.7% | ‑32.8% | 0.81 |
| 50% at +12, BE, runner to +25 | 64% | +10.0% | ‑15.8% | 1.14 |
| all‑out TP+15 / SL‑5 | 79% | +9.7% | ‑8.9% | 3.99 |

**B. Candle backtest:** 145 PumpSwap pools created in the last ~30 h, GeckoTerminal 1‑min OHLCV, entry at the next candle's open.
- Stops are assumed hit before TP within a candle; gaps fill at the open minus 2%; cost is 6%.

| entry window | exits | n | WR | avg win | avg loss | exp/trade |
|---|---|---|---|---|---|---|
| **fresh 3–20 min, 5m +8–30%** | **v2: 50% at +15, stop→+3, runner TP40 / trail 10, SL ‑5** | 75 | 83% | +17.7% | ‑11.7% | **+12.6%** |
| fresh 3–20 min | TP20 / SL‑5 | 75 | 83% | +12.8% | ‑13.9% | +6.7% |
| 30–180 min | v2 | 68 | 44% | +9.8% | ‑12.6% | **‑2.7%** |
| 3–12 h | v2 | 27 | 33% | +4.8% | ‑10.4% | **‑5.4%** |

- **Pessimistic stress test** (stops slip 10%, TP only counts if the wick goes 5% past it): fresh + v2 still gives 80% WR, avg win +17.1% vs avg loss ‑17.2%, exp +10.3%. The 30–180 min window drops to ‑5.5%.
- **Time split:** the first half gave exp +14.0%, the second half +11.2%.
- **Signal rate:** about 2.7 trades/h on only 145 pools. The live universe is larger.

**Honest caveats:**
- The pool list was "most active by 24h tx", which carries selection bias. 53% of these pools are already down more than 80% from their peak, so rugs are well represented.
- 1‑min candles can't show buy/sell ratio, holders or liquidity pulls.
- Treat the absolute numbers as optimistic. The **direction** is consistent across live and backtest data: fresh graduates are positive, late entries are negative.

I tried an unbiased sample (last night's watch list), but most of its "PumpSwap" pools were dead copycat pools with about $0 reserve. That supports the copycat/rug filters but adds no replay data.

## 3. v2 rule set (applied 08:44, config.v2.json = config.json; backup config.json.bak_pre_v2_0843)
- **Scalp only.** `swing_enabled: false`.
- **Universe:**
  - **PumpSwap only** (canonical pump.fun graduates), SOL quote.
  - Pool age **3–20 min**, mcap 15k–400k, liquidity ≥20k, liquidity/mcap ≥0.10.
  - 5m volume ≥8k, ≥60 txns, buy/sell ≥1.4, 5m change **+6% to +30%**, 1h change ≥‑10%.
- **Anti‑rug:**
  - Mint and freeze authority revoked; Token/Token‑2022 program only; no transfer fee.
  - Top10 ≤35%, single holder ≤8%, creator ≤5%, insider network ≤3, holders ≥200.
  - Copycat/duplicate tickers blocked.
  - Jupiter vs DexScreener divergence ≤8%, impact ≤2%, **instant round‑trip quote loss ≤3.5%** (this would have blocked MOVEMBER), entry cost ≤5%.
  - Sell route must exist (honeypot check).
- **Exits (built so wins are larger than losses):**
  - Hard stop ‑5% gross.
  - **Sell 50% at +15%**, then move the stop on the rest to **+3%** (about breakeven after costs).
  - Runner: TP +40% or a 10% trail from the peak, max 30 min.
  - Time stop: 12 min if the gain is still below +4% and TP1 hasn't hit.
  - Liquidity drop ≥20% → exit.
- **Monitoring:**
  - Update every **5 s**.
  - **Positions are re‑priced during scans** via an HTTP‑level hook every ~8 s, which fixes the single‑threaded blind spot.
  - Scan every 90 s.
- **Sizing:** $3.50 per trade (about 16% of equity), max 4 open, 2 new per scan, 30 min re‑entry cooldown.
- **Self‑learning v2** (`review.review_v2`, every 30 min):
  - Only v2 trades count. A change needs ≥8 **new** trades, and only one knob changes per review.
  - Only momentum and TP1 knobs can change, within caps. It never touches safety, the age window, the DEX or the liquidity floor.
  - **Trade‑rate floor:** below 2 entries/h after 45 min, it loosens one momentum knob instead of tightening.
- **Costs are still simulated conservatively** (~7% round trip, including Phantom's 0.85%/side).
  - For real money: swapping via Jupiter directly (no wallet fee), plus a lower priority fee and slightly larger size, would bring costs to about 4–4.5%.
  - That alone lifts expectancy by about 3% per trade in the backtest.

**Code changes:**
- scalp.py: allowed_dexes, v2 exits with partial TP, cash re‑read.
- run.py: TICK_HOOK in get().
- loop.py: swing gate, intra‑scan tick.
- review.py: review_v2.
- Backups are `*.bak_pre_v2`.

## 4. Running without burning weekly usage
**Facts:**
- The box suspends about 4–5 min after the last agent activity, even with the engine process running. Cycle.log shows 8 jumps of 165–377 s overnight despite the 5‑min routine.
- Process activity does not keep the box awake. I found no process‑level knob, so on the box a keep‑alive still needs agent wakes.
- Last night's 5‑min health‑check routine cost about 7.7% of weekly usage per 4 h, which is about 0.16% per wake.

| option | agent wakes | est. weekly‑usage cost | effort for user | verdict |
|---|---|---|---|---|
| Box + 5‑min health‑check routine (last night) | ~12/h | ~1.9%/h, ~15% per 8 h night | none | too expensive |
| Box + minimal keep‑alive routine every 4 min (no checks, no messages; 1 report at the end) | ~15/h, very short turns | ~0.6–1.2%/h (est.) | none | OK for **short** sessions like today's to 10:00 (~1–1.5%); still ~5–10% per night |
| **GitHub Actions (public repo)**: one job runs the engine up to 6 h (2 chained jobs for 8 h); state/results committed to the repo; live dashboard on GitHub Pages (static HTML reading data.json, refreshes itself) | 1–2 per night (start + morning summary) | **~0.3% per night** | connect GitHub once (1 click) and accept a public repo (no secrets needed, only public APIs) | **recommended** |
| User's desktop (HSN27548) running `python loop.py` overnight | 0–1 | ~0% | PC must stay on and not sleep, Python installed; it is offline now | good fallback |
| Oracle Cloud Always Free VM (2 OCPU / 12 GB Arm) | 0–1 | ~0% | signup with credit card, capacity issues, SSH setup | best uptime, most setup |
| Colab / Render free / Railway / Cloudflare Workers | – | – | Colab needs an open browser; Render free sleeps; Railway has no free tier; CF Workers have 10 ms CPU and need a JS rewrite | not suitable |

**GitHub Actions tradeoffs:**
- Hard 6 h job cap.
- Cron can be delayed, so start runs by `workflow_dispatch` or at off‑minutes.
- Shared runner IPs can hit GeckoTerminal's ~30 req/min limit, so keep the 2.1 s pacing.
- The strategy and paper results would be public.
- Scheduled workflows auto‑disable after 60 days of no activity.

**Recommendation:**
- Short daytime sessions: run on the box with a minimal 4‑min keep‑alive.
- Overnight: move to GitHub Actions plus a GitHub Pages dashboard, with one morning summary turn.
- Needed from the user: approve connecting GitHub, and OK a public repo.
