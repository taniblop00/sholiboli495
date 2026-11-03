# Paper-trading lessons (auto + manual)

Per-trade notes are appended automatically after each closed trade. The aggregate section is regenerated every cycle. Use it to tune config.json.

## Manual lessons / decisions

- 2026-11-01 20:41 | Engine bug, trade #2 AAPLCAT voided: DexScreener price was stale during a fast move (+15% in 5m), so the simulated fill was 18.8% above the 'mark'. Fix: marks now come from Jupiter price v3; entry is skipped if Jupiter vs DexScreener differ >10% or the effective fill is >7% above mark. Lesson: never trust a single cached price feed on a fast-moving memecoin; always compare the executable quote to the mark.

## Per-trade log
- 2026-11-01 21:39 | [SCALP] #4 LISA | LOSS -8.7% ($-0.31) | exit scalp_profit_lock after 4m, peak +14% | age 9m mcap $16,666 5m chg 21.04% accel x1.01 b/s 771/554 | entered after >15% 5m candle (late), very fresh (9m), was up 14% but gave it back
- 2026-11-01 21:43 | [SCALP] #3 Anakin | WIN +9.2% ($+0.32) | exit scalp_trailing_stop after 16m, peak +24% | age 12m mcap $15,488 5m chg 26.66% accel x1.11 b/s 460/231 | entered after >15% 5m candle (late), very fresh (12m)
- 2026-11-01 21:48 | [SCALP] #5 AI | WIN +15.9% ($+0.56) | exit scalp_take_profit after 8m, peak +26% | age 10m mcap $74,076 5m chg 10.58% accel x1.05 b/s 551/302 | very fresh (10m)
- 2026-11-01 21:59 | [SCALP] #7 Google🔥 | WIN +17.1% ($+0.60) | exit scalp_take_profit after 10m, peak +27% | age 7m mcap $30,103 5m chg 10.08% accel x1.02 b/s 553/362 | very fresh (7m)
- 2026-11-01 22:00 | [SCALP] #8 VAMP🧛 | WIN +23.2% ($+0.82) | exit scalp_take_profit after 8m, peak +32% | age 5m mcap $18,400 5m chg 27.11% accel x1.01 b/s 470/104 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (5m)
- 2026-11-01 22:00 | [SCALP] #9 HEN | LOSS -39.9% ($-1.41) | exit scalp_stop_loss after 3m, peak +21% | age 9m mcap $18,250 5m chg 29.01% accel x1.06 b/s 734/369 | entered after >15% 5m candle (late), very fresh (9m), was up 21% but gave it back
- 2026-11-01 22:01 | [SCALP] #6 AI | WIN +17.3% ($+0.61) | exit scalp_take_profit after 20m, peak +25% | age 14m mcap $88,811 5m chg 10.89% accel x1.05 b/s 598/333 | very fresh (14m)
- 2026-11-01 22:06 | [SCALP] #10 BHF | LOSS -100.0% ($-3.53) | exit scalp_liquidity_drop after 6m, peak +17% | age 9m mcap $17,863 5m chg 21.4% accel x1.03 b/s 678/408 | entered after >15% 5m candle (late), very fresh (9m), was up 17% but gave it back
- 2026-11-01 22:10 | [SCALP] #11 FAGENT | WIN +22.8% ($+0.80) | exit scalp_take_profit after 4m, peak +29% | age 10m mcap $32,708 5m chg 21.15% accel x1.01 b/s 375/56 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (10m)
- 2026-11-01 23:03 | #1 Leverhedge | LOSS -10.6% ($-0.48) | exit: time_stop_flat | score 67.4 | age 42.9h mcap $745,980 h1 42.18% | signals: strong 1h buy pressure
- 2026-11-02 00:09 | [SCALP] #13 Anakin | LOSS -2.7% ($-0.10) | exit scalp_session_end after 64m, peak +5% | age 25m mcap $101,789 5m chg 1.93% accel x1.22 b/s 709/433 | very fresh (25m)
- 2026-11-02 00:20 | ENGINE RELIABILITY FIX after two freezes (22:11-23:03 and 23:09-00:08). Root cause: the box VM itself was suspended while no agent turn was active (uptime counter is ~2h10m short of wall time; the platform's own 64s monitor logged single gaps of 3089s and 3587s; agent-store FUSE re-armed exactly at 23:03 and 00:08, the moments the box was woken). The Python process was frozen with everything else, mid-HTTP call, and resumed when the box woke. Fixes: hard 10s HTTP timeout + 30s wall budget per call, 110s SIGALRM watchdog per step with rollback, catch-all per pass, heartbeat.txt, external supervisor.sh (restarts loop if dead or heartbeat >180s stale, with resume grace), healthcheck.sh, hourly self-review (review.py) with bounded config changes. Lesson: an in-box supervisor cannot run while the box is suspended - something outside the box (a scheduled agent check) must wake it regularly.
- 2026-11-02 00:20 | Overnight session to 08:00 Asia/Jerusalem. Kept tightened scalp filters (age>=20m, mcap>=40k, liq>=15k, holders>=150) as hard floors for the self-review.
- 2026-11-02 00:35 | #12 RAM | LOSS -4.8% ($-0.19) | exit: time_stop_flat | score 68.2 | age 41.1h mcap $147,247 h1 141% | signals: entered after a >80% 1h pump (chasing)
### Self-review 2026-11-02 00:36 Asia/Jerusalem (auto, hourly)
- All closed: 12 | profit factor 0.62 | equity $27.56
- Scalp (excl. session-end): 9 trades, win rate 67%, avg win +17.6%, avg loss -49.5%, scalp entries last 2h: 1
- Median winners vs losers: age_min 10.2/8.88, mcap 3.14e+04/1.79e+04, liq 4.12e+04/2.41e+04, pc_m5 16/21.4, accel 1.04/1.03, bs_m5 1.91/1.66, holders 614/652, top10 17.6/9.28, entry_cost 2.2/1.56, peak 26.7/17.3
- By dex (wins/losses): meteora 0/3, pumpswap 6/0
- Config changes (bounded): scalp.filters.min_mcap_usd: 40000 -> 50000 (losers' median mcap 1.79e+04 < 0.8x winners' 3.14e+04); scalp.filters.min_buy_sell_ratio_m5: 1.15 -> 1.25 (avg loss -49.5% > 2x avg win 17.6%); scalp.exits.stop_loss_gross_pct: -7.0 -> -6.5 (avg loss > 2x avg win); scalp.exits.lock_trigger_gross_pct: 12.0 -> 11.0 (3 losers were up >=10% first); scalp.filters.blocked_dexes += meteora (3 losses, 0 wins on this dex)
- 2026-11-02 00:55 | #14 VETOTRUMP | LOSS -17.5% ($-0.69) | exit: trailing_stop | score 88.9 | age 1.1h mcap $133,720 h1 58.12% | signals: very young token (1.1h), strong 1h buy pressure
- 2026-11-02 00:56 | [SCALP] #15 uni | WIN +2.2% ($+0.08) | exit scalp_liquidity_drop after 13m, peak +16% | age 21m mcap $97,052 5m chg 9.21% accel x1.06 b/s 630/395 | very fresh (21m)
- 2026-11-02 01:05 | #16 GTA 6 Coin | LOSS -100.0% ($-3.85) | exit: liquidity_drop | score 67.2 | age 1.2h mcap $192,967 h1 4.69% | signals: very young token (1.2h), strong 1h buy pressure, no X account
- 2026-11-02 01:12 | [SCALP] #17 VETOTRUMP | WIN +18.7% ($+0.66) | exit scalp_take_profit after 4m, peak +27% | age 101m mcap $133,509 5m chg 1.74% accel x1.01 b/s 205/119 | none notable
### Self-review 2026-11-02 01:36 Asia/Jerusalem (auto, hourly)
- All closed: 16 | profit factor 0.42 | equity $23.92
- Scalp (excl. session-end): 11 trades, win rate 73%, avg win +15.8%, avg loss -49.5%, scalp entries last 2h: 2
- Median winners vs losers: age_min 11.5/8.88, mcap 5.34e+04/1.79e+04, liq 4.12e+04/2.41e+04, pc_m5 10.7/21.4, accel 1.04/1.03, bs_m5 1.81/1.66, holders 782/652, top10 17.6/9.28, entry_cost 2.2/1.56, peak 26.7/17.3
- By dex (wins/losses): meteora 0/3, pumpswap 8/0
- Config changes (bounded): scalp.filters.min_age_min: 20 -> 25 (losers' median age_min 8.88 < 0.8x winners' 11.5); scalp.filters.min_mcap_usd: 50000 -> 60000 (losers' median mcap 1.79e+04 < 0.8x winners' 5.34e+04); scalp.filters.min_buy_sell_ratio_m5: 1.25 -> 1.35 (avg loss -49.5% > 2x avg win 15.8%); scalp.exits.stop_loss_gross_pct: -6.5 -> -6.0 (avg loss > 2x avg win); scalp.exits.lock_trigger_gross_pct: 11.0 -> 10.0 (3 losers were up >=10% first)
- 2026-11-02 02:19 | #21 MIDTERMS | LOSS -58.2% ($-1.94) | exit: stop_loss | score 77.8 | age 0.7h mcap $38,593 h1 11.33% | signals: very young token (0.7h)
- 2026-11-02 02:24 | [SCALP] #22 MOVEMBER | LOSS -12.6% ($-0.45) | exit scalp_stop_loss after 0m, peak +0% | age 226m mcap $78,129 5m chg 19.94% accel x2.46 b/s 98/59 | entered after >15% 5m candle (late), never went green (bad timing/entry at local top)
### Self-review 2026-11-02 02:37 Asia/Jerusalem (auto, hourly)
- All closed: 18 | profit factor 0.35 | equity $21.54
- Scalp (excl. session-end): 12 trades, win rate 67%, avg win +15.8%, avg loss -40.3%, scalp entries last 2h: 4
- Median winners vs losers: age_min 11.5/8.95, mcap 5.34e+04/1.81e+04, liq 4.12e+04/2.39e+04, pc_m5 10.7/21.2, accel 1.04/1.04, bs_m5 1.81/1.66, holders 782/688, top10 17.6/11.7, entry_cost 2.2/2.04, peak 26.7/15.8
- By dex (wins/losses): meteora 0/3, pumpswap 8/1
- Config changes: none (not enough new closed trades since last change)
- 2026-11-02 02:54 | [SCALP] #23 Learjet | WIN +6.1% ($+0.21) | exit scalp_liquidity_drop after 28m, peak +18% | age 25m mcap $94,969 5m chg 2.11% accel x1.12 b/s 637/417 | very fresh (25m)
### Self-review 2026-11-02 03:37 Asia/Jerusalem (auto, hourly)
- All closed: 21 | profit factor 0.35 | equity $24.10
- Scalp (excl. session-end): 13 trades, win rate 69%, avg win +14.7%, avg loss -40.3%, scalp entries last 2h: 2
- Median winners vs losers: age_min 12.5/8.95, mcap 7.41e+04/1.81e+04, liq 4.97e+04/2.39e+04, pc_m5 10.6/21.2, accel 1.05/1.04, bs_m5 1.8/1.66, holders 823/688, top10 18/11.7, entry_cost 2.12/2.04, peak 26.3/15.8
- By dex (wins/losses): meteora 0/3, pumpswap 9/1
- Config changes (bounded): scalp.filters.min_age_min: 25 -> 30 (losers' median age_min 8.95 < 0.8x winners' 12.5); scalp.filters.min_mcap_usd: 60000 -> 70000 (losers' median mcap 1.81e+04 < 0.8x winners' 7.41e+04); scalp.filters.min_buy_sell_ratio_m5: 1.35 -> 1.45 (avg loss -40.3% > 2x avg win 14.7%); scalp.exits.stop_loss_gross_pct: -6.0 -> -5.5 (avg loss > 2x avg win); scalp.exits.lock_trigger_gross_pct: 10.0 -> 9.0 (3 losers were up >=10% first)
- 2026-11-02 03:36 | #18 Anakinius | WIN +0.4% ($+0.01) | exit: time_stop_flat | score 92.4 | age 1.2h mcap $262,466 h1 12.86% | signals: very young token (1.2h), strong 1h buy pressure
- 2026-11-02 03:36 | #19 ANAKINCORE | LOSS -9.7% ($-0.33) | exit: time_stop_flat | score 89.8 | age 2.5h mcap $358,767 h1 24.56% | signals: very young token (2.5h), strong 1h buy pressure
### Self-review 2026-11-02 04:01 Asia/Jerusalem (auto, hourly)
- All closed: 21 | profit factor 0.35 | equity $23.34
- Scalp (excl. session-end): 13 trades, win rate 69%, avg win +14.7%, avg loss -40.3%, scalp entries last 2h: 2
- Median winners vs losers: age_min 12.5/8.95, mcap 7.41e+04/1.81e+04, liq 4.97e+04/2.39e+04, pc_m5 10.6/21.2, accel 1.05/1.04, bs_m5 1.8/1.66, holders 823/688, top10 18/11.7, entry_cost 2.12/2.04, peak 26.3/15.8
- By dex (wins/losses): meteora 0/3, pumpswap 9/1
- Config changes: none (not enough new closed trades since last change)
- 2026-11-02 08:20 | #20 ANAKIN | WIN +55.3% ($+1.85) | exit: max_hold_time | score 81.7 | age 1.7h mcap $2,056,935 h1 27.54% | signals: thin liquidity vs mcap, very young token (1.7h), strong 1h buy pressure, paid DexScreener boost
- 2026-11-02 08:20 | #24 PIBBLE | LOSS -46.1% ($-1.57) | exit: stop_loss | score 62.0 | age 2.3h mcap $35,746 h1 31.52% | signals: entered on a 5m spike, very young token (2.3h), few holders (577), strong 1h buy pressure, no X account
### Self-review v2 2026-11-02 08:45 Asia/Jerusalem (auto)
- v2 trades 0: WR 0%, avg win +0.0%, avg loss +0.0%, entries last 60 min 0 (floor 2/h), equity $21.72
- Config changes: none (0 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 08:49 | [SCALP] #25 OKCAT | LOSS -19.6% ($-0.69) | exit scalp_stop_loss after 1m, peak +10% | age 9m mcap $18,836 5m chg 28.57% accel x1.04 b/s 631/439 | entered after >15% 5m candle (late), very fresh (9m)
### Self-review v2 2026-11-02 09:15 Asia/Jerusalem (auto)
- v2 trades 1: WR 0%, avg win +0.0%, avg loss -19.6%, entries last 60 min 4 (floor 2/h), equity $21.84
- Config changes: none (1 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 09:17 | [SCALP] #26 0agent | LOSS -46.2% ($-1.63) | exit scalp_liquidity_drop after 16m, peak +24% | age 16m mcap $82,773 5m chg 7.28% accel x1.06 b/s 517/300 | very fresh (16m), was up 24% but gave it back
- 2026-11-02 09:18 | [SCALP] #27 Musk | WIN +19.2% ($+0.68) | exit scalp_runner_take_profit after 9m, peak +40% | age 4m mcap $23,936 5m chg 25.44% accel x1.0 b/s 396/66 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 09:24 | [SCALP] #28 FAGENT | WIN +12.4% ($+0.44) | exit scalp_runner_trailing_stop after 14m, peak +39% | age 4m mcap $22,283 5m chg 9.56% accel x1.0 b/s 211/36 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 09:28 | [SCALP] #29 PEACE | WIN +5.2% ($+0.18) | exit scalp_runner_trailing_stop after 7m, peak +28% | age 4m mcap $17,829 5m chg 18.75% accel x1.0 b/s 267/55 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 09:31 | [SCALP] #30 Capybara | WIN +17.1% ($+0.60) | exit scalp_runner_take_profit after 8m, peak +40% | age 4m mcap $24,133 5m chg 24.29% accel x1.0 b/s 213/58 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m), high entry cost 4.41%
- 2026-11-02 09:38 | [SCALP] #31 我靠 | WIN +20.0% ($+0.71) | exit scalp_runner_take_profit after 14m, peak +42% | age 6m mcap $75,411 5m chg 22.1% accel x1.03 b/s 404/213 | entered after >15% 5m candle (late), very fresh (6m)
### Self-review v2 2026-11-02 09:46 Asia/Jerusalem (auto)
- v2 trades 7: WR 71%, avg win +14.8%, avg loss -32.9%, entries last 60 min 10 (floor 2/h), equity $22.39
- Median winners vs losers: age_min 3.86/12.4, mcap 2.39e+04/5.08e+04, liq 4.27e+04/7.4e+04, pc_m5 22.1/17.9, bs_m5 4.85/1.58, holders 263/668, top10 4.66/17.6, entry_cost 2.55/2.92, peak 40.2/16.8
- Config changes: none (7 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 09:49 | [SCALP] #32 LILY | WIN +3.9% ($+0.14) | exit scalp_runner_trailing_stop after 13m, peak +17% | age 3m mcap $24,914 5m chg 23.4% accel x1.0 b/s 295/44 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (3m)
### Self-review v2 2026-11-02 10:00 Asia/Jerusalem (auto)
- v2 trades 8: WR 75%, avg win +13.0%, avg loss -32.9%, entries last 60 min 10 (floor 2/h), equity $23.14
- Median winners vs losers: age_min 3.82/12.4, mcap 2.4e+04/5.08e+04, liq 4.3e+04/7.4e+04, pc_m5 22.8/17.9, bs_m5 5.36/1.58, holders 273/668, top10 6.65/17.6, entry_cost 2.45/2.92, peak 39.8/16.8
- Config changes: none (8 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 10:00 | [SCALP] #33 Musk | WIN +8.4% ($+0.30) | exit scalp_session_end after 14m, peak +18% | age 5m mcap $20,711 5m chg 8.82% accel x1.0 b/s 452/80 | 5m buys >= 2x sells, very fresh (5m)
- 2026-11-02 10:00 | [SCALP] #34 CATO | WIN +18.4% ($+0.65) | exit scalp_session_end after 14m, peak +34% | age 13m mcap $30,300 5m chg 17.37% accel x1.0 b/s 478/313 | entered after >15% 5m candle (late), very fresh (13m)
- 2026-11-02 10:00 | [SCALP] #35 火龙果 | LOSS -8.1% ($-0.28) | exit scalp_session_end after 2m, peak +0% | age 3m mcap $18,774 5m chg 17.74% accel x1.0 b/s 239/48 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (3m), never went green (bad timing/entry at local top)
- 2026-11-02 10:44 | [SCALP] #36 PEACE | WIN +20.1% ($+0.71) | exit scalp_runner_take_profit after 16m, peak +40% | age 4m mcap $21,119 5m chg 8.76% accel x1.0 b/s 339/71 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 10:46 | [SCALP] #37 Trump | LOSS -45.2% ($-1.60) | exit scalp_liquidity_drop after 19m, peak +1508019% | age 4m mcap $20,916 5m chg 11.95% accel x1.0 b/s 385/63 | 5m buys >= 2x sells, very fresh (4m), was up 1508019% but gave it back
- 2026-11-02 10:57 | [SCALP] #38 OAK | LOSS -9.0% ($-0.32) | exit scalp_time_stop after 12m, peak +4% | age 4m mcap $19,755 5m chg 24.41% accel x1.0 b/s 280/77 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 11:04 | [SCALP] #41 NEAR | WIN +20.1% ($+0.71) | exit scalp_runner_take_profit after 6m, peak +43% | age 3m mcap $19,055 5m chg 19.16% accel x1.0 b/s 224/48 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (3m)
- 2026-11-02 11:05 | [SCALP] #40 Warcoin | WIN +6.3% ($+0.22) | exit scalp_runner_trailing_stop after 14m, peak +29% | age 4m mcap $24,186 5m chg 19.23% accel x1.0 b/s 400/50 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 11:15 | [SCALP] #42 PEACE | WIN +20.6% ($+0.73) | exit scalp_runner_take_profit after 16m, peak +42% | age 4m mcap $21,659 5m chg 10.89% accel x1.0 b/s 172/56 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 11:18 | [SCALP] #44 OAK | LOSS -100.0% ($-3.53) | exit scalp_liquidity_drop after 2m, peak +921% | age 4m mcap $18,410 5m chg 15.58% accel x1.0 b/s 179/64 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m), was up 921% but gave it back
- 2026-11-02 11:20 | [SCALP] #39 Trump | WIN +18.7% ($+0.66) | exit scalp_runner_take_profit after 28m, peak +41% | age 4m mcap $21,256 5m chg 13.19% accel x1.0 b/s 410/66 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 11:25 | [SCALP] #43 Dino | WIN +25.2% ($+0.89) | exit scalp_runner_take_profit after 14m, peak +52% | age 4m mcap $18,194 5m chg 13.54% accel x1.0 b/s 204/71 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 11:47 | [SCALP] #46 Musk | LOSS -47.0% ($-1.66) | exit scalp_liquidity_drop after 6m, peak +40% | age 4m mcap $20,804 5m chg 9.25% accel x1.0 b/s 341/62 | 5m buys >= 2x sells, very fresh (4m), was up 40% but gave it back
- 2026-11-02 11:49 | [SCALP] #47 PEAK | LOSS -11.8% ($-0.42) | exit scalp_stop_loss after 1m, peak +0% | age 5m mcap $24,177 5m chg 25.5% accel x1.0 b/s 368/79 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (5m), never went green (bad timing/entry at local top)
- 2026-11-02 11:49 | [SCALP] #45 Tesla | WIN +20.5% ($+0.72) | exit scalp_runner_take_profit after 13m, peak +42% | age 4m mcap $19,902 5m chg 6.34% accel x1.0 b/s 394/63 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 11:57 | [SCALP] #48 Warcoin | WIN +3.1% ($+0.11) | exit scalp_runner_trailing_stop after 8m, peak +21% | age 4m mcap $23,465 5m chg 16.22% accel x1.0 b/s 391/59 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 12:01 | [SCALP] #49 Musk | WIN +19.2% ($+0.68) | exit scalp_runner_take_profit after 10m, peak +42% | age 4m mcap $24,004 5m chg 25.86% accel x1.0 b/s 377/64 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 12:10 | [SCALP] #51 OAK | WIN +4.1% ($+0.14) | exit scalp_runner_trailing_stop after 15m, peak +19% | age 4m mcap $17,476 5m chg 10.11% accel x1.0 b/s 181/65 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 12:17 | [SCALP] #50 PEACE | WIN +19.1% ($+0.67) | exit scalp_runner_take_profit after 23m, peak +33% | age 4m mcap $21,248 5m chg 9.25% accel x1.0 b/s 236/79 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 12:33 | [SCALP] #52 Musk | WIN +11.4% ($+0.40) | exit scalp_runner_trailing_stop after 13m, peak +37% | age 3m mcap $22,228 5m chg 16.99% accel x1.0 b/s 296/53 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (3m)
- 2026-11-02 12:37 | [SCALP] #53 Claude AI | LOSS -45.9% ($-1.62) | exit scalp_liquidity_drop after 8m, peak +17% | age 3m mcap $19,257 5m chg 19.39% accel x1.0 b/s 237/54 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (3m), was up 17% but gave it back
- 2026-11-02 13:00 | [SCALP] #54 Capybara | WIN +12.2% ($+0.43) | exit scalp_session_end after 4m, peak +25% | age 4m mcap $23,379 5m chg 18.96% accel x1.0 b/s 233/64 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
### Self-review v4 2026-11-02 15:31 Asia/Jerusalem (auto)
- v4 trades 0: WR 0%, avg win +0.0%, avg loss +0.0%, entries last 60 min 1 (floor 2/h), equity $20.64
- Config changes: none (0 new trades since last change; need 8, or rate below floor after 45 min)
### Self-review v4 2026-11-02 16:01 Asia/Jerusalem (auto)
- v4 trades 5: WR 80%, avg win +8.3%, avg loss -100.0%, entries last 60 min 5 (floor 2/h), equity $18.74
- Median winners vs losers: age_min 4.35/4.55, mcap 2.31e+04/2.37e+04, liq 4.38e+04/4.42e+04, pc_m5 12.1/14.8, bs_m5 5.34/5.99, holders 292/463, top10 3.27/3.05, entry_cost 3.02/2.52, peak 25.7/7.33
- Config changes: none (5 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 15:35 | [SCALP] #55 FOREVER | WIN +8.9% ($+0.27) | exit scalp_runner_take_profit after 4m, peak +26% | age 4m mcap $22,666 5m chg 9.61% accel x1.0 b/s 385/64 | 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 15:37 | [SCALP] #56 PREDICT | WIN +6.7% ($+0.20) | exit scalp_runner_breakeven_stop after 4m, peak +20% | age 4m mcap $22,161 5m chg 15.65% accel x1.0 b/s 189/35 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (4m)
- 2026-11-02 15:43 | [SCALP] #58 FOREVER | LOSS -100.0% ($-3.03) | exit scalp_liquidity_pull_suspected after 3m, peak +7% | age 5m mcap $23,739 5m chg 14.83% accel x1.0 b/s 437/73 | 5m buys >= 2x sells, very fresh (5m)
- 2026-11-02 15:45 | [SCALP] #57 PEACE | WIN +8.6% ($+0.26) | exit scalp_runner_take_profit after 5m, peak +26% | age 5m mcap $27,470 5m chg 11.56% accel x0.94 b/s 257/71 | 5m buys >= 2x sells, very fresh (5m)
- 2026-11-02 15:55 | [SCALP] #59 FOREVER | WIN +9.2% ($+0.28) | exit scalp_runner_take_profit after 9m, peak +25% | age 3m mcap $23,518 5m chg 12.57% accel x1.0 b/s 306/58 | 5m buys >= 2x sells, very fresh (3m)
### Self-review v4 2026-11-02 16:32 Asia/Jerusalem (auto)
- v4 trades 5: WR 80%, avg win +8.3%, avg loss -100.0%, entries last 60 min 4 (floor 2/h), equity $18.74
- Median winners vs losers: age_min 4.35/4.55, mcap 2.31e+04/2.37e+04, liq 4.38e+04/4.42e+04, pc_m5 12.1/14.8, bs_m5 5.34/5.99, holders 292/463, top10 3.27/3.05, entry_cost 3.02/2.52, peak 25.7/7.33
- Config changes: none (5 new trades since last change; need 8, or rate below floor after 45 min)
### Self-review v4 2026-11-02 17:00 Asia/Jerusalem (auto)
- v4 trades 6: WR 83%, avg win +7.6%, avg loss -100.0%, entries last 60 min 1 (floor 2/h), equity $19.01
- Median winners vs losers: age_min 4.31/4.55, mcap 2.35e+04/2.37e+04, liq 4.41e+04/4.42e+04, pc_m5 12.6/14.8, bs_m5 5.28/5.99, holders 316/463, top10 3.24/3.05, entry_cost 2.99/2.52, peak 25.5/7.33
- Config change (one knob): min_price_change_m5: 6.0 -> 5.0 (only 1 entries in last hour < floor; momentum-only loosening)
- 2026-11-02 17:00 | [SCALP] #60 Virus🦠 | WIN +4.8% ($+0.15) | exit scalp_run_end after 2m, peak +12% | age 3m mcap $23,603 5m chg 14.38% accel x1.0 b/s 247/56 | 5m buys >= 2x sells, very fresh (3m)
### Self-review v5 2026-11-02 17:31 Asia/Jerusalem (auto)
- v5 trades 0: WR 0%, avg win +0.0%, avg loss +0.0%, entries last 60 min 0 (floor 2/h), equity $18.89
- Config changes: none (0 new trades since last change; need 8, or rate below floor after 45 min)
### Self-review v5 2026-11-02 18:02 Asia/Jerusalem (auto)
- v5 trades 0: WR 0%, avg win +0.0%, avg loss +0.0%, entries last 60 min 0 (floor 2/h), equity $18.89
- Config change (one knob): min_price_change_m5: 6.0 -> 5.0 (only 0 entries in last hour < floor; momentum-only loosening)
### Self-review v5 2026-11-02 18:33 Asia/Jerusalem (auto)
- v5 trades 1: WR 100%, avg win +0.7%, avg loss +0.0%, entries last 60 min 1 (floor 2/h), equity $18.91
- Config change (one knob): min_price_change_m5: 5.0 -> 4.0 (only 1 entries in last hour < floor; momentum-only loosening)
- 2026-11-02 18:24 | [SCALP] #61 Marutaro | WIN +0.7% ($+0.03) | exit scalp_runner_trailing_stop after 17m, peak +23% | age 83m mcap $256,938 5m chg 9.55% accel x1.95 b/s 985/340 | 5m buys >= 2x sells, high entry cost 4.58%
### Self-review v5 2026-11-02 19:04 Asia/Jerusalem (auto)
- v5 trades 2: WR 50%, avg win +0.7%, avg loss -20.9%, entries last 60 min 2 (floor 2/h), equity $18.18
- Median winners vs losers: age_min 83.4/72.3, mcap 2.57e+05/1.89e+05, liq 4.13e+04/3.51e+04, pc_m5 9.55/15.8, bs_m5 2.9/4.56, holders 6.72e+03/4.52e+03, top10 1.84/1.3, entry_cost 4.58/4.68, peak 23.1/5.99
- Config changes: none (1 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 18:47 | [SCALP] #62 KOROSUKE | LOSS -20.9% ($-0.74) | exit scalp_stop_loss after 1m, peak +6% | age 72m mcap $189,475 5m chg 15.83% accel x0.51 b/s 1194/262 | entered after >15% 5m candle (late), 5m buys >= 2x sells, high entry cost 4.68%
### Self-review v5 2026-11-02 19:35 Asia/Jerusalem (auto)
- v5 trades 2: WR 50%, avg win +0.7%, avg loss -20.9%, entries last 60 min 1 (floor 2/h), equity $18.18
- Median winners vs losers: age_min 83.4/72.3, mcap 2.57e+05/1.89e+05, liq 4.13e+04/3.51e+04, pc_m5 9.55/15.8, bs_m5 2.9/4.56, holders 6.72e+03/4.52e+03, top10 1.84/1.3, entry_cost 4.58/4.68, peak 23.1/5.99
- Config change (one knob): min_buy_sell_ratio_m5: 1.5 -> 1.4 (only 1 entries in last hour < floor; momentum-only loosening)
### Self-review v5 2026-11-02 19:52 Asia/Jerusalem (auto)
- v5 trades 2: WR 50%, avg win +0.7%, avg loss -20.9%, entries last 60 min 0 (floor 2/h), equity $18.18
- Median winners vs losers: age_min 83.4/72.3, mcap 2.57e+05/1.89e+05, liq 4.13e+04/3.51e+04, pc_m5 9.55/15.8, bs_m5 2.9/4.56, holders 6.72e+03/4.52e+03, top10 1.84/1.3, entry_cost 4.58/4.68, peak 23.1/5.99
- Config changes: none (0 new trades since last change; need 8, or rate below floor after 45 min)
### Self-review v6 2026-11-02 20:23 Asia/Jerusalem (auto)
- v6 trades 4: WR 0%, avg win +0.0%, avg loss -32.9%, entries last 60 min 4 (floor 3/h), equity $14.19
- Config changes: none (4 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 20:11 | [SCALP] #63 SLINGOOR | LOSS -27.4% ($-0.83) | exit scalp_stop_loss after 0m, peak +0% | age 15m mcap $143,187 5m chg 28.97% accel x0.77 b/s 1632/334 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (15m), never went green (bad timing/entry at local top)
- 2026-11-02 20:14 | [SCALP] #64 NULL | LOSS -12.8% ($-0.39) | exit scalp_stop_loss after 1m, peak +0% | age 27m mcap $71,419 5m chg 8.43% accel x0.45 b/s 168/103 | very fresh (27m), never went green (bad timing/entry at local top)
- 2026-11-02 20:16 | [SCALP] #65 Horse | LOSS -15.6% ($-0.47) | exit scalp_stop_loss after 0m, peak +0% | age 5m mcap $121,375 5m chg 23.57% accel x1.01 b/s 1440/419 | entered after >15% 5m candle (late), 5m buys >= 2x sells, very fresh (5m), never went green (bad timing/entry at local top)
- 2026-11-02 20:22 | [SCALP] #66 Robinhood | LOSS -75.9% ($-2.30) | exit scalp_stop_loss after 1m, peak +3% | age 21m mcap $205,876 5m chg 10.36% accel x0.41 b/s 2161/959 | 5m buys >= 2x sells, very fresh (21m)
### Self-review v6 2026-11-02 20:33 Asia/Jerusalem (auto)
- v6 trades 5: WR 0%, avg win +0.0%, avg loss -27.0%, entries last 60 min 5 (floor 3/h), equity $14.08
- Config changes: none (5 new trades since last change; need 8, or rate below floor after 45 min)
- 2026-11-02 20:27 | [SCALP] #67 POSSUM | LOSS -3.5% ($-0.11) | exit scalp_take_profit_full after 0m, peak +11% | age 10m mcap $72,210 5m chg 25.72% accel x1.39 b/s 1304/1057 | entered after >15% 5m candle (late), very fresh (10m)
- 2026-11-02 22:28 | #68 PENGU | LOSS -0.0% ($-0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-02 23:05 | #69 SOL | WIN +0.1% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-02 23:08 | #70 TRUMP | WIN +0.7% ($+0.02) | exit: quote_take_profit | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-02 23:15 | #71 JUP | LOSS -0.3% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-02 23:21 | #72 FARTCOIN | WIN +0.2% ($+0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 00:32 | #73 FARTCOIN | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 01:00 | #76 FARTCOIN | LOSS -0.7% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 01:05 | #74 SOL | LOSS -0.3% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 01:10 | #75 TRUMP | LOSS -0.1% ($-0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 01:21 | #77 TRUMP | LOSS -0.7% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 02:06 | #78 JUP | LOSS -0.2% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 02:07 | #79 TRUMP | LOSS -0.3% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 02:11 | #80 SOL | LOSS -0.3% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 02:39 | #81 PENGU | WIN +0.0% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 02:40 | #82 FARTCOIN | WIN +0.1% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 02:44 | #84 TRUMP | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 02:46 | #83 SOL | LOSS -0.0% ($-0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 03:25 | #86 PENGU | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 03:29 | #85 TRUMP | WIN +0.7% ($+0.02) | exit: quote_take_profit | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 03:38 | #87 FARTCOIN | LOSS -0.3% ($-0.01) | exit: run_end | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 04:10 | #88 JUP | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 04:19 | #90 TRUMP | LOSS -0.7% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 04:31 | #89 PENGU | LOSS -0.4% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 04:41 | #91 SOL | LOSS -0.1% ($-0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 05:00 | #92 PENGU | LOSS -0.7% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 05:27 | #94 TRUMP | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 05:28 | #95 FARTCOIN | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 05:31 | #93 PENGU | LOSS -0.3% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 05:59 | #96 FARTCOIN | WIN +0.2% ($+0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 06:26 | #97 SOL | LOSS -0.2% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 06:40 | #98 TRUMP | LOSS -0.2% ($-0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 06:53 | #99 FARTCOIN | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 07:32 | #100 SOL | LOSS -0.7% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 08:11 | #101 JUP | LOSS -0.6% ($-0.02) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 08:12 | #102 SOL | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 08:22 | #103 TRUMP | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 08:43 | #106 FARTCOIN | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 08:50 | #104 TRUMP | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 08:56 | #105 SOL | LOSS -0.4% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 09:18 | #107 SOL | WIN +0.1% ($+0.00) | exit: run_end | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 09:49 | #108 PENGU | LOSS -0.1% ($-0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 09:49 | #109 TRUMP | WIN +0.1% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 09:50 | #110 FARTCOIN | WIN +0.0% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 10:26 | #112 TRUMP | LOSS -0.9% ($-0.03) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 10:40 | #111 SOL | LOSS -0.6% ($-0.02) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 10:59 | #113 TRUMP | WIN +0.8% ($+0.02) | exit: quote_take_profit | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 11:21 | #114 SOL | WIN +0.2% ($+0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 13:26 | #115 SOL | LOSS -0.1% ($-0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 13:32 | #116 TRUMP | LOSS -0.3% ($-0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 14:16 | #117 SOL | WIN +0.1% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 14:26 | #118 TRUMP | WIN +0.7% ($+0.02) | exit: quote_take_profit | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 15:22 | #120 FARTCOIN | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 15:24 | #119 SOL | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 15:29 | #122 PENGU | WIN +0.7% ($+0.02) | exit: quote_take_profit | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 15:31 | #121 SOL | WIN +0.8% ($+0.02) | exit: quote_take_profit | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 15:36 | #123 TRUMP | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 15:36 | #125 FARTCOIN | LOSS -0.8% ($-0.03) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 15:53 | #124 SOL | LOSS -0.7% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 16:07 | #126 TRUMP | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 16:45 | #127 SOL | WIN +0.2% ($+0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 16:45 | #128 TRUMP | WIN +0.5% ($+0.01) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 16:50 | #129 PENGU | WIN +0.1% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 17:18 | #131 TRUMP | LOSS -0.7% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 17:22 | #132 FARTCOIN | LOSS -0.8% ($-0.02) | exit: quote_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 17:45 | #130 SOL | WIN +0.1% ($+0.00) | exit: quote_time_stop | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account
- 2026-11-03 17:46 | #133 FARTCOIN | WIN +0.3% ($+0.01) | exit: run_end | score None | age 0.0h mcap $0 h1 None% | signals: few holders (None), no X account

<!-- AGGREGATE -->
## Aggregate SWING (auto-regenerated 2026-11-03 17:46 Asia/Jerusalem)

Closed 9: 2 wins / 7 losses.

| feature | avg winners | avg losers |
|---|---|---|
| score | 87.1 | 74.5 |
| age_h | 1.44 | 13.1 |
| mcap | 1.16e+06 | 2.36e+05 |
| liq_mcap | 0.109 | 0.242 |
| pc_h1 | 20.2 | 44.8 |
| pc_m5 | -6.1 | 2.65 |
| pc_h6 | 2.23e+03 | 195 |
| bs_ratio | 3.16 | 1.73 |
| holders | 5.94e+03 | 3.11e+03 |
| top10_ex_pools | 1.77 | 13.8 |
| rc_score_norm | 1 | 1 |

Exit reasons: time_stop_flat: n=4 sum $-0.98, trailing_stop: n=1 sum $-0.69, liquidity_drop: n=1 sum $-3.85, max_hold_time: n=1 sum $+1.85, stop_loss: n=2 sum $-3.50

Suggested tuning (review manually before changing config.json):
- losers had higher pc_h1 (44.8 vs 20.2) -> consider tightening its max filter
- losers had higher pc_m5 (2.65 vs -6.1) -> consider tightening its max filter
- losers had higher top10_ex_pools (13.8 vs 1.77) -> consider tightening its max filter
- losers had higher age_h (13.1 vs 1.44) -> consider tightening its max filter
- winners had higher score (87.1 vs 74.5) -> consider raising its minimum
- winners had higher holders (5.94e+03 vs 3.11e+03) -> consider raising its minimum
- winners had higher bs_ratio (3.16 vs 1.73) -> consider raising its minimum

Rejected-token follow-up (price ~6h+ after rejection):

| stage | reason | n | avg multiple | >=1.5x | <0.5x |
|---|---|---|---|---|---|
| safety | insider_network | 6 | 1.46 | 1 | 1 |
| safety | rugcheck_danger:Large Amount of LP Unlocked | 3 | 12.68 | 3 | 0 |
| safety | rugcheck_risk:Single holder ownership | 1 | 11.43 | 1 | 0 |

## Aggregate SCALP

Closed 57: 36 wins / 21 losses, net $-8.75

| feature | avg winners | avg losers |
|---|---|---|
| rank | 72.5 | 65.5 |
| age_min | 11.2 | 23 |
| mcap | 4.11e+04 | 6.21e+04 |
| pc_m5 | 14.8 | 18.1 |
| pc_h1 | 40.7 | 91.4 |
| accel | 1.04 | 1.02 |
| bs_m5 | 4.18 | 3.22 |
| entry_cost_pct | 2.35 | 2.51 |
| top10_ex_pools | 9.15 | 10.1 |
| holders | 712 | 1.13e+03 |
| peak_pct | 30.1 | 7.19e+04 |

Exit reasons: scalp_liquidity_drop: n=8 sum $-13.27, scalp_liquidity_pull_suspected: n=1 sum $-3.03, scalp_profit_lock: n=1 sum $-0.31, scalp_run_end: n=1 sum $+0.15, scalp_runner_breakeven_stop: n=1 sum $+0.20, scalp_runner_take_profit: n=14 sum $+8.57, scalp_runner_trailing_stop: n=8 sum $+1.66, scalp_session_end: n=5 sum $+1.00, scalp_stop_loss: n=9 sum $-7.68, scalp_take_profit: n=6 sum $+4.06, scalp_take_profit_full: n=1 sum $-0.11, scalp_time_stop: n=1 sum $-0.32, scalp_trailing_stop: n=1 sum $+0.32

Suggested tuning:
- winners had higher bs_m5 (4.18 vs 3.22) -> raise its min
- 10 losers were up >=10% first -> lower lock/trail triggers
