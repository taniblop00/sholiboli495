#!/usr/bin/env bash
# Runs in the background during a GitHub Actions job:
#  * every INTERVAL s pushes docs/data/state.json (live dashboard) - working tree is never touched
#  * if a file named STOP appears on the remote branch, creates ./STOP so main.py shuts down cleanly
INTERVAL="${1:-120}"
BR="${GITHUB_REF_NAME:-main}"
while sleep "$INTERVAL"; do
  scripts/push_state.sh "live state $(date -u +%Y-%m-%dT%H:%MZ)" docs/data/state.json >/dev/null 2>&1
  if git fetch -q origin "$BR" 2>/dev/null && git cat-file -e "origin/$BR:STOP" 2>/dev/null; then touch STOP; fi
done
