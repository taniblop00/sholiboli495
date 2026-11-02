#!/usr/bin/env python3
"""Single entry point of the meme-coin PAPER trading engine (simulation only - it never signs, builds or sends a
transaction and holds no keys; it only reads public market data and Jupiter QUOTES).

    python main.py --minutes 340          # run the scalp loop for 340 minutes, then exit cleanly
    python main.py --minutes 3 --no-review

Designed for GitHub Actions (one job <= 6 h): no machine-specific paths (everything is relative to this folder),
state lives in state.db + docs/data/state.json (exported every ~30 s), logs in logs/cycle.log.
In the last `drain_min` minutes no new positions are opened; anything still open at the deadline is closed
(reason run_end) so nothing is left unmonitored between two runs. SIGTERM/SIGINT -> same clean shutdown."""
import os, sys, time, json, argparse, datetime, traceback, signal, platform
os.environ.setdefault("MT_NO_STDOUT", "1")
BASE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, BASE); os.chdir(BASE)

ap = argparse.ArgumentParser(description="PAPER-only meme-coin scalp engine")
ap.add_argument("--minutes", type=float, default=340, help="how long to run before a clean exit (default 340)")
ap.add_argument("--no-review", action="store_true", help="skip the automatic self-review")
ap.add_argument("--drain-minutes", type=float, default=None, help="no new entries in the last N minutes (default config loop.drain_min)")
ap.add_argument("--verbose", action="store_true", help="also print log lines to stdout")
args = ap.parse_args()
if args.verbose: os.environ["MT_NO_STDOUT"] = "0"

import run, scalp, review, export_state

if run.CFG["scalp"].get("version") is None: raise SystemExit("config.json has no scalp.version")

HB = os.path.join(BASE, "heartbeat.txt")
class StepTimeout(BaseException): pass       # BaseException so run.get's `except Exception` cannot swallow it
class Shutdown(BaseException): pass
def _alarm(signum, frame): raise StepTimeout()
STOP = {"flag": False, "why": None}
def _term(signum, frame):
    STOP["flag"] = True; STOP["why"] = signal.Signals(signum).name
signal.signal(signal.SIGALRM, _alarm); signal.signal(signal.SIGTERM, _term); signal.signal(signal.SIGINT, _term)

PHASE = {"phase": "start"}
def heartbeat(phase):
    PHASE["phase"] = phase
    try:
        tmp = HB + ".tmp"
        open(tmp, "w").write(f"{int(time.time())} {run.local_now().strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} phase={phase}\n")
        os.replace(tmp, HB)
    except Exception: pass

def reload_cfg():
    try: run.CFG = json.load(open(run.CFG_PATH))
    except Exception as e: run.log(f"WARN config reload failed, keeping old: {e}")

def L(): return run.CFG["scalp"]["loop"]
c = run.db()

def safe(name, fn, timeout=None):
    timeout = int(timeout or L().get("pass_timeout_s", 110))
    heartbeat(name); signal.alarm(timeout)
    try: return fn()
    except StepTimeout:
        run.log(f"WATCHDOG: step '{name}' exceeded {timeout}s - aborted, transaction rolled back, loop continues")
        try: c.rollback()
        except Exception: pass
    except Exception:
        run.log(f"ERROR in {name}: " + traceback.format_exc().replace("\n", " | ")[-1500:])
        try: c.rollback()
        except Exception: pass
    finally:
        signal.alarm(0)

def housekeeping():
    """Keep state.db small for git: drop old scan rows / RugCheck cache (cache kept for every traded mint)."""
    cut = run.iso(run.now() - datetime.timedelta(days=2))
    c.execute("DELETE FROM scalp_scans WHERE ts<?", (cut,)); c.execute("DELETE FROM scans WHERE ts<?", (cut,))
    c.execute("DELETE FROM rc_cache WHERE ts<? AND mint NOT IN (SELECT mint FROM positions)", (time.time() - 12 * 3600,))
    c.commit()

START = time.time(); DEADLINE = START + args.minutes * 60
DRAIN = (args.drain_minutes if args.drain_minutes is not None else L().get("drain_min", 12)) * 60
DRAIN = min(DRAIN, args.minutes * 60 * 0.5)
ver = run.CFG["scalp"]["version"]
if not c.execute("SELECT v FROM meta WHERE k=?", (f"{ver}_started",)).fetchone():
    c.execute("INSERT INTO meta VALUES(?,?)", (f"{ver}_started", run.iso()))
    try:
        sess = json.loads((c.execute("SELECT v FROM meta WHERE k='sessions'").fetchone() or ["[]"])[0])
        sess.append({"name": ver, "start": run.iso()}); c.execute("INSERT OR REPLACE INTO meta VALUES('sessions',?)", (json.dumps(sess),))
    except Exception: pass
    c.commit()
# positions left open by a crashed/cancelled previous run: re-priced immediately by the first update (exits apply as usual)
start_eq = run.cash(c) + run.open_value(c)
RUN = {"started_ts": START, "started_at": run.iso(), "ends_at": run.iso(run.now() + datetime.timedelta(seconds=args.minutes * 60)),
       "start_equity": round(start_eq, 4), "runner": "github-actions" if os.environ.get("GITHUB_ACTIONS") else platform.node()}
def status(state="running", msg=None):
    return {"state": state, "phase": PHASE["phase"], "message": msg, "scanner": scalp.STATUS}
def do_export(state="running", msg=None):
    safe("export", lambda: export_state.export(c, RUN, status(state, msg)), timeout=30)

run.log(f"=== RUN start pid {os.getpid()} {ver} PAPER ONLY | {args.minutes:.0f} min (until {run.local(RUN['ends_at'])} Asia/Jerusalem), drain last {DRAIN/60:.0f} min | "
        f"update {L()['update_every_s']}s scan {L()['scan_every_s']}s export {L().get('export_every_s', 30)}s | equity ${start_eq:.2f} ===")
safe("housekeeping", housekeeping)
heartbeat("start"); do_export("starting")
_lr = c.execute("SELECT v FROM meta WHERE k='review_last_run_ts'").fetchone()
last = {"scan": 0, "eq": 0, "export": time.time(), "beat": time.time(),
        "review": max(float(_lr[0]) if _lr else 0, time.time() - L().get("self_review_every_s", 1800) + 600)}
_last_tick = [0.0]
def _intra_scan_tick():
    if time.time() - _last_tick[0] < L().get("intra_scan_update_every_s", 5): return
    _last_tick[0] = time.time()
    if c.execute("SELECT COUNT(*) FROM positions WHERE status='open' AND strategy='scalp'").fetchone()[0]:
        scalp.update(c); heartbeat("scalp_scan+tick")
    if time.time() - last["export"] >= L().get("export_every_s", 30):
        last["export"] = time.time()
        try: export_state.export(c, RUN, status("running", "scanning"))
        except Exception as e: run.log(f"WARN export during scan failed: {e}")
run.TICK_HOOK = _intra_scan_tick

def one_pass():
    t = time.time()
    if t - last["beat"] > 60: run.log(f"WARN loop wall-clock gap of {t - last['beat']:.0f}s - positions re-priced at current market")
    last["beat"] = t
    reload_cfg(); run._SOLPX = None
    _last_tick[0] = time.time(); safe("scalp_update", lambda: scalp.update(c))
    draining = DEADLINE - time.time() <= DRAIN
    if not draining and time.time() - last["scan"] >= L()["scan_every_s"]:
        last["scan"] = time.time(); safe("scalp_scan", lambda: scalp.scan(c))
    if time.time() - last["eq"] >= 60:
        last["eq"] = time.time(); safe("equity", lambda: run.record_equity(c))
    if not args.no_review and time.time() - last["review"] >= L().get("self_review_every_s", 1800):
        last["review"] = time.time(); safe("self_review", lambda: review.review(c, loop_started_ts=START)); safe("lessons", lambda: run.lessons(c))
    if time.time() - last["export"] >= L().get("export_every_s", 30):
        last["export"] = time.time(); do_export("draining" if draining else "running", "no new entries (end of run)" if draining else None)
    heartbeat("sleep")
    return t

STOP_FILE = os.path.join(BASE, "STOP")
while not STOP["flag"] and time.time() < DEADLINE:
    if os.path.exists(STOP_FILE):   # created by scripts/sync_state.sh when a STOP file is pushed to the repo
        STOP["flag"] = True; STOP["why"] = "STOP file"; break
    try:
        t = one_pass()
        time.sleep(max(0.5, min(L()["update_every_s"] - (time.time() - t), DEADLINE - time.time())))
    except StepTimeout:
        signal.alarm(0); run.log("WATCHDOG: pass-level timeout caught - continuing")
    except Exception:
        signal.alarm(0); run.log("ERROR in pass (caught, loop continues): " + traceback.format_exc().replace("\n", " | ")[-1500:]); time.sleep(3)

why = f"signal {STOP['why']}" if STOP["flag"] else "time limit reached"
run.log(f"=== RUN END ({why}): closing any open scalp positions (reason run_end) and saving state ===")
signal.signal(signal.SIGTERM, signal.SIG_IGN); signal.signal(signal.SIGINT, signal.SIG_IGN)
safe("final_scalp_close", lambda: scalp.update(c, force_close_reason="run_end"), timeout=60)
if not args.no_review: safe("final_review", lambda: review.review(c, loop_started_ts=START), timeout=60)
safe("final_lessons", lambda: run.lessons(c), timeout=60); safe("final_equity", lambda: run.record_equity(c))
safe("final_report", lambda: run.log("\n" + run.report(c, short=True)), timeout=60)
heartbeat("ended"); do_export("ended", f"run finished ({why})")
c.commit(); c.close()
run.log("=== RUN ended cleanly ===")
print(f"PAPER run finished ({why}). Equity ${run.cash(run.db()):.2f}. State: state.db, docs/data/state.json")
