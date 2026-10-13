#!/usr/bin/env bash
# trigger_run.sh  [pilot|full|N_shards]
#
# Triggers the detection workflow via a throw-away branch push.
# Requires a GitHub token with 'workflow' scope: set GITHUB_TOKEN env var or
# pass it as GH_TOKEN. You can also just go to:
#
#   https://github.com/sans-2186/Sanskriti-Flaky-Tests-Data/actions/workflows/detect.yml
#
# and click "Run workflow" from the UI (no token needed).
#
# Usage:
#   ./scripts/trigger_run.sh pilot    # 3 projects (1 shard of 3)
#   ./scripts/trigger_run.sh 20       # 20 projects  (use max_shards=3 shard_size=7)
#   ./scripts/trigger_run.sh full     # all 798 pairs

set -euo pipefail
MODE="${1:-pilot}"
REPO="sans-2186/Sanskriti-Flaky-Tests-Data"

case "$MODE" in
  pilot)
    SHARD_SIZE=3; MAX_SHARDS=1 ;;
  full)
    SHARD_SIZE=8; MAX_SHARDS=0 ;;
  *)
    # Treat as a number of projects
    N="${MODE}"
    SHARD_SIZE=8
    MAX_SHARDS=$(( (N + SHARD_SIZE - 1) / SHARD_SIZE ))
    ;;
esac

TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"

if [ -n "$TOKEN" ]; then
  echo "Dispatching via API (max_shards=$MAX_SHARDS shard_size=$SHARD_SIZE)..."
  curl -s -X POST \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/$REPO/actions/workflows/detect.yml/dispatches" \
    -d "{
      \"ref\": \"main\",
      \"inputs\": {
        \"shard_size\": \"$SHARD_SIZE\",
        \"max_shards\": \"$MAX_SHARDS\",
        \"jdk\": \"8\"
      }
    }"
  echo
  echo "Check progress: https://github.com/$REPO/actions"
else
  echo "No GITHUB_TOKEN found. Triggering via branch push..."
  BRANCH="run-detection-${MODE}-$(date +%Y%m%d%H%M%S)"
  git checkout -b "$BRANCH"
  # Write the trigger config into a file the workflow will read
  cat > .github/run_config.json <<JSON
{"shard_size": $SHARD_SIZE, "max_shards": $MAX_SHARDS, "jdk": "8"}
JSON
  git add .github/run_config.json
  git commit -m "trigger: $MODE run (shard_size=$SHARD_SIZE max_shards=$MAX_SHARDS)"
  git push origin "$BRANCH"
  echo
  echo "Triggered via branch push."
  echo "Check progress: https://github.com/$REPO/actions"
  echo "(You can delete the branch $BRANCH after the run starts.)"
fi
