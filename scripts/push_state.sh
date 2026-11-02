#!/usr/bin/env bash
# Commit the given files on top of the LATEST remote branch tip and push - without touching the working tree
# (the engine keeps writing state.db while this runs, so no checkout/rebase/stash is ever done here).
# Usage: scripts/push_state.sh "message" file1 [file2 ...]
set -u
MSG="$1"; shift
BR="${GITHUB_REF_NAME:-main}"
git config user.name  >/dev/null || git config user.name  "paper-trader-bot"
git config user.email >/dev/null || git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
for attempt in 1 2 3 4 5 6; do
  git fetch -q origin "$BR" || { echo "push_state: fetch failed (attempt $attempt)" >&2; sleep 5; continue; }
  BASE_C=$(git rev-parse "origin/$BR")
  IDX=$(mktemp); export GIT_INDEX_FILE="$IDX"
  git read-tree "$BASE_C"
  for f in "$@"; do
    [ -f "$f" ] || continue
    if [ "$f" = "config.json" ]; then
      # keep a config edited on the remote during the run (user/agent change wins over the self-review)
      [ "$(git rev-parse "$BASE_C:config.json" 2>/dev/null)" = "$(git rev-parse "HEAD:config.json" 2>/dev/null)" ] || continue
    fi
    cp "$f" "$IDX.blob"   # snapshot first (sqlite may be mid-write; the engine commits often, a copy is consistent enough)
    git update-index --add --cacheinfo 100644,"$(git hash-object -w "$IDX.blob")","$f"
  done
  TREE=$(git write-tree); unset GIT_INDEX_FILE; rm -f "$IDX" "$IDX.blob"
  if [ "$TREE" = "$(git rev-parse "$BASE_C^{tree}")" ]; then exit 0; fi
  C=$(git commit-tree "$TREE" -p "$BASE_C" -m "$MSG")
  # Fast-forward only: if the remote moved, the push is rejected and the next attempt rebuilds on the new tip.
  if git push origin "$C:refs/heads/$BR"; then echo "push_state: pushed $C"; exit 0; fi
  echo "push_state: push rejected (attempt $attempt) — rebasing onto the new tip" >&2
  sleep $((attempt * 3))
done
echo "push_state: giving up after 6 attempts" >&2; exit 0
