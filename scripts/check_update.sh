#!/usr/bin/env bash
# Check-ONLY update detector for claude-cowork-agentops.
#
# Designed to run INSIDE the Cowork VM from a scheduled task. It never pulls and
# never writes to .git: it uses `git ls-remote` (a pure network query) to compare
# the remote branch tip against the local HEAD. Because nothing under .git is
# written, no lock files are created — this avoids the stale-lock problem that
# makes VM-side `git pull` fragile. Pulling + re-registering tasks stays manual,
# on the host.
#
# Output (stdout):
#   UP_TO_DATE <sha>
#   UPDATE_AVAILABLE local=<sha> remote=<sha>   (also prints a compare= URL)
#   CHECK_FAILED <reason>
# Exit codes: 0 up to date, 10 update available, 1 check failed.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || { echo "CHECK_FAILED bad repo dir"; exit 1; }

ORIGIN=$(git remote get-url origin 2>/dev/null)
# Normalize SSH origin -> anonymous HTTPS (public repo, no credentials needed).
URL=$(printf '%s' "$ORIGIN" | sed -E 's#^git@github.com:#https://github.com/#; s#^ssh://git@github.com/#https://github.com/#')
WEB=$(printf '%s' "$URL" | sed -E 's#\.git$##')
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null); [ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ] && BRANCH=main

LOCAL=$(git rev-parse HEAD 2>/dev/null)
REMOTE=$(git ls-remote "$URL" -h "refs/heads/$BRANCH" 2>/dev/null | cut -f1)

if [ -z "$REMOTE" ]; then echo "CHECK_FAILED could not reach $URL ($BRANCH)"; exit 1; fi
if [ "$LOCAL" = "$REMOTE" ]; then echo "UP_TO_DATE $LOCAL"; exit 0; fi

echo "UPDATE_AVAILABLE local=$LOCAL remote=$REMOTE"
echo "compare=$WEB/compare/${LOCAL}...${REMOTE}"
exit 10
