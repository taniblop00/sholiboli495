# YONI paper trader (v2 + rug escape) — GitHub Actions bundle

**Simulation only.** The engine never builds, signs or sends a transaction, has no wallet and no keys.
It reads public data only (DexScreener, GeckoTerminal, RugCheck, Jupiter lite *quotes*) and books simulated fills in `state.db`.

The live book is the v2 PumpSwap scalp from `v2_plan.md` (08:44 on 2 Nov 2026): age 3–20 min, $3.50, sell half at +15%, runner to +40%. Exits fill on the Jupiter sell quote, and that quote is not haircut a second time. Open positions are repriced every 3 seconds. A fast `rug_escape` sells at the quote if liquidity, the quote, or a large holder disappears. The ledger before this reset is in `archive/ledger-before-v2-rug-2026-11-03/`.

## Layout
| path | what |
|---|---|
| `main.py` | single entry point: `python main.py --minutes 340` (loop, then clean exit; SIGTERM/SIGINT/`STOP` file → clean exit) |
| `run.py` | shared helpers: HTTP (hard timeouts), DB, quotes, simulated buy/sell, reports. Paths are relative to the repo (`MT_HOME` overrides) |
| `scalp.py` | v2 PumpSwap scalp plus `rug_escape`. Sell-quote fills, partial take-profit, runner |
| `review.py` | self-review every 30 min: never raises, version-scoped, bounded by `_bounded_ok` (never touches safety/tiers/sizes/stops) |
| `export_state.py` | writes `docs/data/state.json` (every 30 s from `main.py`) |
| `config.json` | v2 rules (`scalp.*`) plus the rug-escape block. `config.strict.json` = swing safety floor |
| `state.db` | sqlite ledger. Reset to $30.00 for v2 + rug escape. The previous ledger is archived |
| `docs/index.html` | black, Hebrew, mobile crypto-wallet dashboard. Polls `state.json` every 25 s (cache-busted). On GitHub Pages it prefers the raw URL so the ledger stays fresh between Pages builds |
| `scripts/push_state.sh` | commits listed files on top of the latest remote tip via git plumbing (never touches the working tree). Retries on a rejected push instead of rebasing the live working tree |
| `scripts/sync_state.sh` | background: pushes `state.json` every 120 s; creates `./STOP` if a `STOP` file appears on the remote |
| `.github/workflows/paper-trader.yml` | one paper run at a time: `workflow_dispatch` + push to `main` + cron every 15 min. Each run is 340 min, then dispatches the next. Cron keeps a successor queued so a failed dispatch still leaves only about a minute of gap |
| `.github/workflows/pages.yml` | publishes `docs/` to GitHub Pages when the dashboard HTML changes |
| `analysis/` | `trade_review.py` (full trade review + exit replay), `filter_exit_grid.py`, outputs, older backtests |
| `tests/test_exits_offline.py` | offline test of v4 exits on a temp copy (no network) |
| `logs/` | `cycle.log` (rotates at 3 MB) + the full pre-GitHub history log |
| `ANALYSIS.md` | findings and v4 rule changes (Hebrew) |

## Requirements
Python ≥ 3.10, standard library only (`requirements.txt` is intentionally empty). Linux/macOS (uses `signal.SIGALRM`).

## Run locally
```bash
python main.py --minutes 3 --drain-minutes 0.5 --verbose   # smoke test
python export_state.py                                      # one-off export
python analysis/trade_review.py                             # re-run the analysis
python tests/test_exits_offline.py
```

## GitHub Actions notes
- Public repo → standard runners are free. A job may last ≤ 6 h, so each run is 340 min plus the commit step.
- Only one run is active (`concurrency: paper-trader-<branch>`, `cancel-in-progress: false`). A push to `main`, a manual dispatch, or the 15-minute cron can start it. While a run is active the cron keeps exactly one successor queued, and the job also dispatches the next 340-minute run as it exits. The gap between runs is the time it takes a runner to start, not the cron interval.
- Bot commits do not retrigger the workflow (`GITHUB_TOKEN` pushes never do, and `state.db` / `docs/data/**` / logs are in `paths-ignore`). A human push of code, or a `STOP` file, does.
- `state.json` is pushed every 2 min during a run. `state.db`, `lessons.md`, `logs/cycle.log` and `config.json` are pushed at the end, on top of the latest remote tip (fetch + retry, no rebase of the live tree). The next run checks out that `state.db`, so cash and trade history continue. A remote `config.json` edit made during a run wins over the self-review.
- The job refuses to start if `state.db` has no cash row or no closed trades, so an empty checkout cannot reset the bankroll to $30.
- **Stop:** commit an empty `STOP` file to the repo root, or disable the workflow. **Resume:** delete `STOP`.
- **Dashboard:** https://taniblop00.github.io/sholiboli495/ once Pages is enabled (source: GitHub Actions). The page is labeled מסחר דמה and polls the ledger every 25 s. `?src=<url>` forces a different `state.json`.
- **No secrets are needed.** Never add wallet keys; the engine has no code path that could use them.
- The workflow uses `GITHUB_TOKEN` with `contents: write` and `actions: write`. If pushes are rejected, set Settings → Actions → General → Workflow permissions to **Read and write permissions**.

