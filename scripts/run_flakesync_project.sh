#!/usr/bin/env bash
# run_flakesync_project.sh  PROJECT_URL  SHA  TESTS_FILE  RESULTS_DIR
#
# TESTS_FILE: one test per line, tab-separated: "<fqn_dot_sep>\t<module>"
#   where module may be empty. fqn uses dot separators everywhere
#   (org.example.Class.method) — converted internally to FlakeSync format
#   (org.example.Class#method) for the -Dflakesync.testName flag.
#
# FlakeSync plugin (edu.utexas.ece:flakesync-maven-plugin:1.0-SNAPSHOT) must
# already be installed in the local Maven repo before calling this script.
#
# Exit code: always 0. Failures are recorded in the JSON, not via exit code.

set -euo pipefail

PROJECT_URL="${1:?Usage: run_flakesync_project.sh PROJECT_URL SHA TESTS_FILE RESULTS_DIR}"
SHA="${2:?}"
TESTS_FILE="${3:?}"
_RAW_RESULTS_DIR="${4:?}"

NAME="$(basename "$PROJECT_URL" .git)"
SHA7="${SHA:0:7}"

# Resolve to absolute paths before any cd
mkdir -p "$_RAW_RESULTS_DIR" projects
RESULTS_DIR="$(cd "$_RAW_RESULTS_DIR" && pwd)"
CLONE_DIR="$(pwd)/projects/${NAME}_${SHA7}"
TESTS_FILE="$(cd "$(dirname "$TESTS_FILE")" && pwd)/$(basename "$TESTS_FILE")"
OUT_JSON="${RESULTS_DIR}/${NAME}_${SHA7}_flakesync.json"
RESULTS_TSV="${RESULTS_DIR}/${NAME}_${SHA7}_flakesync.tsv"

FS_PLUGIN="edu.utexas.ece:flakesync-maven-plugin:1.0-SNAPSHOT"

log() { echo "[$(date -u +%H:%M:%S)] [$NAME] $*"; }

# ── clone & build ─────────────────────────────────────────────────────────────

PROJ_STATUS="ok"

if [ -d "$CLONE_DIR/.git" ]; then
  log "Reusing existing clone"
else
  log "Cloning $PROJECT_URL"
  rm -rf "$CLONE_DIR"
  if ! timeout 300 git clone --depth=50 "$PROJECT_URL" "$CLONE_DIR" 2>&1; then
    if ! timeout 600 git clone "$PROJECT_URL" "$CLONE_DIR" 2>&1; then
      log "ERROR: clone failed"
      echo '{"project":"'"$NAME"'","url":"'"$PROJECT_URL"'","sha":"'"$SHA"'","status":"clone_failed","tests":{}}' > "$OUT_JSON"
      exit 0
    fi
  fi
fi

cd "$CLONE_DIR"
git checkout "$SHA" 2>/dev/null || git reset --hard "$SHA" 2>/dev/null || true

log "Building project (skip tests)"
if ! timeout 600 mvn -B -q install -DskipTests \
    -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dspotbugs.skip=true \
    -Dpmd.skip=true -Drat.skip=true -Dlicense.skip=true \
    -Denforcer.skip=true -Dmaven.javadoc.skip=true -Dmaven.source.skip=true \
    -Dgpg.skip=true 2>&1; then
  log "WARN: build failed — FlakeSync may still work on partial build"
  PROJ_STATUS="build_partial"
fi

# ── per-test FlakeSync pipeline ───────────────────────────────────────────────

# TSV columns: test_fqn  status  concurrent_methods  delay_locs  minimized_locs  crit_points  barrier_points  patch_generated
> "$RESULTS_TSV"

run_goal() {
  local goal="$1" fs_test="$2" module="$3" timeout_s="$4"
  local pl=""
  [ -n "$module" ] && pl="-pl $module"
  # shellcheck disable=SC2086
  timeout "$timeout_s" mvn -B -q \
    "$FS_PLUGIN:$goal" \
    -Dflakesync.testName="$fs_test" \
    $pl \
    -Dsurefire.failIfNoSpecifiedTests=false \
    2>&1
}

count_lines() {
  [ -f "$1" ] && grep -c '' "$1" 2>/dev/null || echo 0
}

while IFS=$'\t' read -r test_fqn module || [ -n "$test_fqn" ]; do
  [ -z "$test_fqn" ] && continue
  # trim whitespace/CR
  test_fqn="${test_fqn%%$'\r'}"
  module="${module%%$'\r'}"

  # org.pkg.Class.method → org.pkg.Class#method (replace last dot with #)
  FS_TEST="${test_fqn%.*}#${test_fqn##*.}"
  log "▶ $FS_TEST (module=${module:-root})"

  STATUS="no_concurrent_methods"
  CF=0; DL=0; ML=0; CR=0; BR=0; PATCHED=false

  FS_DIR=".flakesync"
  [ -n "$module" ] && FS_DIR="${module}/.flakesync"

  # Step 1 – concurrentfind (find concurrent methods touched by test)
  if run_goal "concurrentfind" "$FS_TEST" "$module" 300 ; then
    CF=$(count_lines "${FS_DIR}/${FS_TEST}-ResultMethods.txt")
    log "  concurrentfind: $CF methods"

    if [ "$CF" -gt 0 ]; then
      # Step 2 – delaylocs (inject delays and find locations that flip the test)
      if run_goal "delaylocs" "$FS_TEST" "$module" 600 ; then
        DL=$(count_lines "${FS_DIR}/${FS_TEST}-Locations.txt")
        log "  delaylocs: $DL locations"

        if [ "$DL" -gt 0 ]; then
          STATUS="has_delay_locs"

          # Step 3 – deltadebug (minimize locations)
          run_goal "deltadebug" "$FS_TEST" "$module" 600 || true
          ML=$(count_lines "${FS_DIR}/${FS_TEST}-Locations_minimized.txt")
          log "  deltadebug: $ML minimized"

          # Step 4 – critsearch
          if run_goal "critsearch" "$FS_TEST" "$module" 600 ; then
            CR=$(count_lines "${FS_DIR}/Results-CritSearch/${FS_TEST}-CriticalPoints.csv")
            log "  critsearch: $CR critical points"

            # Step 5 – barrierpointsearch
            if run_goal "barrierpointsearch" "$FS_TEST" "$module" 600 ; then
              BR=$(count_lines "${FS_DIR}/Results-BarrierSearch/${FS_TEST}-BarrierPoints.csv")
              log "  barrierpointsearch: $BR barrier points"

              # Step 6 – patch
              if run_goal "patch" "$FS_TEST" "$module" 300 ; then
                log "  patch: generated"
                PATCHED=true
                STATUS="patched"
              else
                STATUS="patch_failed"
              fi
            else
              STATUS="barrierpointsearch_failed"
            fi
          else
            STATUS="critsearch_failed"
          fi
        else
          STATUS="no_delay_locs"
        fi
      else
        STATUS="delaylocs_failed"
      fi
    fi
  else
    STATUS="concurrentfind_failed"
  fi

  log "  → $STATUS"
  printf '%s\t%s\t%d\t%d\t%d\t%d\t%d\t%s\n' \
    "$test_fqn" "$STATUS" "$CF" "$DL" "$ML" "$CR" "$BR" "$PATCHED" \
    >> "$RESULTS_TSV"

done < "$TESTS_FILE"

cd - > /dev/null

# ── write JSON ────────────────────────────────────────────────────────────────
python3 - "$NAME" "$PROJECT_URL" "$SHA" "$PROJ_STATUS" "$RESULTS_TSV" "$OUT_JSON" <<'PYEOF'
import json, sys, csv

name, url, sha, proj_status, tsv_path, out_path = sys.argv[1:]

tests = {}
if __import__('os').path.exists(tsv_path):
    with open(tsv_path) as f:
        for row in csv.reader(f, delimiter='\t'):
            if len(row) < 8:
                continue
            test_fqn, status, cf, dl, ml, cr, br, patched = row[:8]
            tests[test_fqn] = {
                "status": status,
                "concurrent_methods": int(cf),
                "delay_locs": int(dl),
                "minimized_locs": int(ml),
                "crit_points": int(cr),
                "barrier_points": int(br),
                "patch_generated": patched.lower() == "true",
            }

out = {"project": name, "url": url, "sha": sha,
       "status": proj_status, "tests": tests}
with open(out_path, "w") as f:
    json.dump(out, f, indent=2)
print(f"Wrote {out_path} ({len(tests)} tests)")
PYEOF

exit 0
