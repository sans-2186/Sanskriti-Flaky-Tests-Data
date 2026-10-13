#!/usr/bin/env bash
# run_one.sh  PROJECT_URL  SHA  RESULTS_DIR  [JDK_VERSION]
#
# Clones the project, checks out the SHA, builds it, then runs iDFlakies and
# NonDex over the whole project. Writes a small per-project result JSON to
# RESULTS_DIR/<name>_<sha7>.json. Raw detector output directories are left
# inside the clone so the caller can tar them up if needed.
#
# Exit codes: 0 always (failures are recorded in the JSON, not via exit code).

set -euo pipefail

PROJECT_URL="${1:?Usage: run_one.sh PROJECT_URL SHA RESULTS_DIR [JDK_VERSION]}"
SHA="${2:?}"
RESULTS_DIR="${3:?}"
JDK="${4:-8}"

NAME="$(basename "$PROJECT_URL" .git)"
SHA7="${SHA:0:7}"
CLONE_DIR="$(pwd)/projects/${NAME}_${SHA7}"
OUT_JSON="${RESULTS_DIR}/${NAME}_${SHA7}.json"

mkdir -p "$RESULTS_DIR"

IDFLAKIES="edu.illinois.cs:idflakies-maven-plugin:2.0.0:detect"
NONDEX="edu.illinois:nondex-maven-plugin:2.2.1:nondex"

SKIP_FLAGS=(
  -Dcheckstyle.skip=true
  -Dfindbugs.skip=true
  -Dspotbugs.skip=true
  -Dpmd.skip=true
  -Dfmt.skip=true
  -Dformatter.skip=true
  -Dspotless.check.skip=true
  -Dimpsort.skip=true
  -Dsort.skip=true
  -Drat.skip=true
  -Dlicense.skip=true
  -Danimal.sniffer.skip=true
  -Denforcer.skip=true
  -Djapicmp.skip=true
  -Drevapi.skip=true
  -Ddependency-check.skip=true
  -Djacoco.skip=true
  -Dmaven.javadoc.skip=true
  -Dmaven.source.skip=true
  -Dmaven.site.skip=true
  -Dgpg.skip=true
  -Dinvoker.skip=true
  -DskipITs=true
)

# Pick JAVA_HOME based on requested JDK version
pick_java() {
  local v="$1"
  # GitHub Actions runners expose pre-installed JDK paths as JAVA_HOME_8_X64, etc.
  local jh_var="JAVA_HOME_${v}_X64"
  local jh="${!jh_var:-}"   # bash indirect expansion
  local candidates=(
    "${jh}"
    "/usr/lib/jvm/temurin-${v}-jdk-amd64"
    "/usr/lib/jvm/java-${v}-openjdk-amd64"
    "/usr/lib/jvm/java-${v}-amazon-corretto"
  )
  for c in "${candidates[@]}"; do
    [ -d "${c:-}" ] && { echo "$c"; return 0; }
  done
  echo ""
}

set_jdk() {
  local jh
  jh="$(pick_java "$1")"
  if [ -n "$jh" ]; then
    export JAVA_HOME="$jh"
    export PATH="$JAVA_HOME/bin:$PATH"
  fi
}

# ---------- helpers ----------

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

log() { echo "[$(ts)] $*" >&2; }

write_json() {
  # write_json STATUS IDF_TESTS ND_TESTS MESSAGE
  local status="$1" idf="$2" nd="$3" msg="${4:-}"
  python3 - <<PYEOF
import json, sys
d = {
  "project": "$NAME",
  "url": "$PROJECT_URL",
  "sha": "$SHA",
  "status": "$status",
  "idflakies": $idf,
  "nondex": $nd,
  "message": "$msg"
}
print(json.dumps(d, indent=2))
PYEOF
}

# ---------- parse helpers ----------

parse_idflakies() {
  # Scan all .dtfixingtools under the given directory tree.
  local root="$1"
  python3 - "$root" <<'PYEOF'
import json, os, re, sys

root = sys.argv[1]
found = set()

TEST_RE = re.compile(r'^[\w$]+(\.[\w$]+)+$')

def harvest(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("name", "testName") and isinstance(v, str) and v.strip():
                n = v.strip()
                if TEST_RE.match(n):
                    found.add(n)
            else:
                harvest(v)
    elif isinstance(obj, list):
        for v in obj:
            harvest(v)

for dirpath, dirnames, filenames in os.walk(root):
    if '.dtfixingtools' not in dirpath:
        continue
    for fn in filenames:
        if fn == 'flaky-lists.json' or fn == 'list.txt':
            path = os.path.join(dirpath, fn)
            if fn.endswith('.json'):
                try:
                    with open(path) as f:
                        data = json.load(f)
                    # dts is the standard key
                    for item in (data.get('dts') or []):
                        n = item.get('name', '') if isinstance(item, dict) else str(item)
                        if TEST_RE.match(n.strip()):
                            found.add(n.strip())
                except Exception:
                    pass
            else:
                try:
                    with open(path) as f:
                        for line in f:
                            line = line.strip()
                            if TEST_RE.match(line):
                                found.add(line)
                except Exception:
                    pass

print(json.dumps(sorted(found)))
PYEOF
}

parse_nondex() {
  local root="$1" logfile="$2"
  python3 - "$root" "$logfile" <<'PYEOF'
import os, re, sys, json

root = sys.argv[1]
logfile = sys.argv[2]
found = set()

TEST_RE = re.compile(r'^[\w$]+(\.[\w$]+)*[.#][\w$]+$')

def add(t):
    t = t.strip().replace('#', '.')
    t = t.split('(')[0]
    if TEST_RE.match(t):
        found.add(t)

# 1. Parse "Across all seeds:" summary from the Maven log (most reliable)
if os.path.exists(logfile):
    with open(logfile, errors='replace') as f:
        content = f.read()
    parts = content.split('Across all seeds:')
    if len(parts) > 1:
        for line in parts[-1].splitlines():
            raw = re.sub(r'^\[INFO\]\s*', '', line).strip()
            if not raw:
                continue
            if not TEST_RE.match(raw.replace('#', '.')):
                break
            add(raw)

# 2. Per-seed failures files under .nondex
for dirpath, dirnames, filenames in os.walk(root):
    if '.nondex' not in dirpath:
        continue
    if 'failures' in filenames:
        try:
            with open(os.path.join(dirpath, 'failures'), errors='replace') as f:
                for line in f:
                    add(line)
        except Exception:
            pass

print(json.dumps(sorted(found)))
PYEOF
}

# ---------- main ----------

log "=== Starting $NAME @ $SHA7 (JDK $JDK) ==="

# Clone
if [ -d "$CLONE_DIR/.git" ]; then
  log "Reusing existing clone at $CLONE_DIR"
else
  rm -rf "$CLONE_DIR"
  if ! timeout 300 git clone --filter=blob:none --quiet "$PROJECT_URL" "$CLONE_DIR"; then
    log "Clone failed"
    write_json "clone_failed" "[]" "[]" "" > "$OUT_JSON"
    exit 0
  fi
fi

# Checkout
if ! (cd "$CLONE_DIR" && git checkout --quiet "$SHA" 2>&1); then
  log "Checkout failed"
  write_json "checkout_failed" "[]" "[]" "" > "$OUT_JSON"
  exit 0
fi

# Set JDK
set_jdk "$JDK"
log "JAVA_HOME=$JAVA_HOME java=$(java -version 2>&1 | head -1)"

export MAVEN_OPTS="-Xmx2g -Xms256m"
MVN=(mvn -B -fae)

# ---------- Build ----------
log "Building..."
BUILD_LOG="$CLONE_DIR/build.log"
if ! timeout 600 "${MVN[@]}" install -DskipTests "${SKIP_FLAGS[@]}" \
      -f "$CLONE_DIR/pom.xml" > "$BUILD_LOG" 2>&1; then
  # Try with Java 11 if Java 8 failed
  if [ "$JDK" = "8" ]; then
    log "Build failed with JDK 8, retrying with JDK 11..."
    set_jdk 11
    if ! timeout 600 "${MVN[@]}" install -DskipTests "${SKIP_FLAGS[@]}" \
          -f "$CLONE_DIR/pom.xml" >> "$BUILD_LOG" 2>&1; then
      log "Build failed with JDK 11 too"
      write_json "build_failed" "[]" "[]" "" > "$OUT_JSON"
      exit 0
    fi
  else
    log "Build failed"
    write_json "build_failed" "[]" "[]" "" > "$OUT_JSON"
    exit 0
  fi
fi
log "Build succeeded"

# ---------- NonDex ----------
log "Running NonDex..."
ND_LOG="$CLONE_DIR/nondex.log"
ND_EXIT=0
timeout 1200 "${MVN[@]}" "$NONDEX" "${SKIP_FLAGS[@]}" \
  -DnondexRuns=5 \
  -DfailIfNoTests=false \
  -DfailIfNoSpecifiedTests=false \
  -f "$CLONE_DIR/pom.xml" > "$ND_LOG" 2>&1 || ND_EXIT=$?
log "NonDex exit: $ND_EXIT"

# ---------- iDFlakies ----------
log "Running iDFlakies..."
IDF_LOG="$CLONE_DIR/idflakies.log"
IDF_EXIT=0
timeout 2700 "${MVN[@]}" "$IDFLAKIES" "${SKIP_FLAGS[@]}" \
  -Ddetector.detector_type=random-class-method \
  -Ddt.randomize.rounds=10 \
  -Ddt.detector.original_order.all_must_pass=false \
  -f "$CLONE_DIR/pom.xml" > "$IDF_LOG" 2>&1 || IDF_EXIT=$?
log "iDFlakies exit: $IDF_EXIT"

# ---------- Parse ----------
log "Parsing results..."
IDF_TESTS="$(parse_idflakies "$CLONE_DIR")"
ND_TESTS="$(parse_nondex "$CLONE_DIR" "$ND_LOG")"

IDF_COUNT=$(echo "$IDF_TESTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
ND_COUNT=$(echo "$ND_TESTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")

STATUS="ok"
[ "$IDF_EXIT" -eq 124 ] || [ "$ND_EXIT" -eq 124 ] && STATUS="timeout"

log "Done: iDFlakies=$IDF_COUNT NonDex=$ND_COUNT status=$STATUS"
write_json "$STATUS" "$IDF_TESTS" "$ND_TESTS" "" > "$OUT_JSON"

exit 0
