#!/usr/bin/env bash
# run_flakesync_nod.sh URL SHA MODULE TESTS_FILE LOG_ROOT OUT_JSON
#
# TESTS_FILE holds IDoFT NOD tests, one per line. This is not the
# iDFlakies/NonDex output. FlakeSync writes Class.method-Locations.txt
# (a dot, not a hash). Counts come from those files.

set -uo pipefail

URL="${1:?}"
SHA="${2:?}"
MODULE="${3:-}"
TESTS_FILE="${4:?}"
LOG_ROOT="${5:?}"
OUT_JSON="${6:?}"

GOAL_TIMEOUT="${GOAL_TIMEOUT:-480}"
BUILD_TIMEOUT="${BUILD_TIMEOUT:-600}"
FS_PLUGIN="edu.utexas.ece:flakesync-maven-plugin:1.0-SNAPSHOT"

mkdir -p "$LOG_ROOT"
NAME="$(echo "$URL" | awk -F/ '{print $(NF-1)"/"$NF}' | sed 's/\.git$//')"
SLUG="$(echo "${NAME}__${MODULE:-root}" | tr '/ ' '__')"

pick_java() {
  local v="$1" var="JAVA_HOME_${v}_X64" jh="${!var:-}" c
  for c in "$jh" "/usr/lib/jvm/temurin-${v}-jdk-amd64" "/usr/lib/jvm/java-${v}-openjdk-amd64"; do
    [ -n "${c:-}" ] && [ -x "$c/bin/java" ] && { echo "$c"; return 0; }
  done
  echo ""
}
use_jdk() {
  local jh
  jh="$(pick_java "$1")"
  [ -n "$jh" ] || return 1
  export JAVA_HOME="$jh"
  export PATH="$JAVA_HOME/bin:$PATH"
}

SKIP=(
  -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dspotbugs.skip=true
  -Dpmd.skip=true -Drat.skip=true -Dlicense.skip=true
  -Denforcer.skip=true -Dmaven.javadoc.skip=true -Dmaven.source.skip=true
  -Dgpg.skip=true -DskipITs=true
)

WORKDIR="$(mktemp -d)"
CLONE="$WORKDIR/repo"
trap 'rm -rf "$WORKDIR"' EXIT

BUILD="clone failed"
JDK_USED=""
if git clone --filter=blob:none "$URL" "$CLONE" > "$LOG_ROOT/${SLUG}-clone.log" 2>&1; then
  if git -C "$CLONE" checkout --force "$SHA" >> "$LOG_ROOT/${SLUG}-clone.log" 2>&1; then
    BUILD="install failed"
    for v in 8 11 17; do
      use_jdk "$v" || continue
      pl=()
      if [ -n "$MODULE" ] && [ "$MODULE" != "." ]; then
        pl=(-pl "$MODULE" -am)
      fi
      if timeout "$BUILD_TIMEOUT" mvn -B -DskipTests "${SKIP[@]}" "${pl[@]}" install \
          -f "$CLONE/pom.xml" > "$LOG_ROOT/${SLUG}-install-jdk${v}.log" 2>&1; then
        BUILD="install ok"
        JDK_USED="$v"
        break
      fi
    done
  else
    BUILD="checkout failed"
  fi
fi

export FS_URL="$URL" FS_SHA="$SHA" FS_MODULE="$MODULE" FS_NAME="$NAME"
export FS_BUILD="$BUILD" FS_JDK="$JDK_USED" FS_CLONE="$CLONE" FS_LOG_ROOT="$LOG_ROOT"
export FS_SLUG="$SLUG" FS_PLUGIN="$FS_PLUGIN" FS_GOAL_TIMEOUT="$GOAL_TIMEOUT"
export FS_TESTS="$TESTS_FILE" FS_OUT="$OUT_JSON"
# shell-quoted -pl for the python runner
if [ -n "$MODULE" ] && [ "$MODULE" != "." ]; then
  export FS_PL="-pl
${MODULE}
-am"
else
  export FS_PL=""
fi

python3 << 'PY'
import json, os, shutil, subprocess, time

url = os.environ["FS_URL"]
sha = os.environ["FS_SHA"]
module = os.environ["FS_MODULE"]
name = os.environ["FS_NAME"]
build = os.environ["FS_BUILD"]
jdk = os.environ["FS_JDK"]
clone = os.environ["FS_CLONE"]
log_root = os.environ["FS_LOG_ROOT"]
slug = os.environ["FS_SLUG"]
plugin = os.environ["FS_PLUGIN"]
goal_timeout = os.environ["FS_GOAL_TIMEOUT"]
tests_file = os.environ["FS_TESTS"]
out = os.environ["FS_OUT"]
pl = [p for p in os.environ.get("FS_PL", "").split("\n") if p]

def nlines(path):
    if not path or not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for line in f if line.strip())

def find_file(test_dot, test_hash, suffix):
    want = {f"{test_dot}-{suffix}", f"{test_hash}-{suffix}"}
    # Locations.txt must not match Locations_tmp.txt or Locations_minimized.txt
    for dirpath, _, files in os.walk(clone):
        for fn in files:
            if fn in want:
                return os.path.join(dirpath, fn)
    return ""

def copy_out(tdir, test_dot, test_hash, suffix):
    src = find_file(test_dot, test_hash, suffix)
    if src:
        os.makedirs(os.path.join(tdir, "out"), exist_ok=True)
        shutil.copy(src, os.path.join(tdir, "out", os.path.basename(src)))
    return nlines(src)

def run_goal(goal, tdir, test_hash):
    cmd = ["timeout", goal_timeout, "mvn", "-B", f"{plugin}:{goal}",
           f"-Dflakesync.testName={test_hash}",
           "-Dsurefire.failIfNoSpecifiedTests=false",
           "-f", os.path.join(clone, "pom.xml")]
    # insert -pl/-am before -f
    if pl:
        cmd[-2:-2] = pl
    log_path = os.path.join(tdir, f"{goal}.log")
    with open(log_path, "w") as log:
        return subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode

def count_patches(test_dot):
    method = test_dot.rsplit(".", 1)[-1]
    n = 0
    for dirpath, _, files in os.walk(clone):
        low = dirpath.replace("\\", "/").lower()
        if "flakesync" not in low:
            continue
        for fn in files:
            if fn.endswith(".patch") and method in fn:
                n += 1
    return n

tests = []
with open(tests_file, encoding="utf-8") as f:
    raw_tests = [ln.strip() for ln in f if ln.strip()]

for raw in raw_tests:
    test_dot = raw.replace("#", ".")
    test_hash = test_dot.rsplit(".", 1)[0] + "#" + test_dot.rsplit(".", 1)[1]
    tdir = os.path.join(log_root, "flakesync", f"{slug}__{test_dot.split('.')[-1]}")
    os.makedirs(os.path.join(tdir, "out"), exist_ok=True)
    clone_log = os.path.join(log_root, f"{slug}-clone.log")
    if os.path.isfile(clone_log):
        shutil.copy(clone_log, os.path.join(tdir, "clone.log"))
    t0 = time.time()
    if build != "install ok":
        tests.append({
            "test": test_hash, "jdk": "", "concurrent_methods": 0,
            "delay_locations": 0, "minimized_locations": 0, "critical_points": 0,
            "barrier_points": 0, "patch_files": 0, "result": build, "seconds": 0,
        })
        continue
    inst = os.path.join(log_root, f"{slug}-install-jdk{jdk}.log")
    if os.path.isfile(inst):
        shutil.copy(inst, os.path.join(tdir, f"install-jdk{jdk}.log"))
        shutil.copy(inst, os.path.join(tdir, "install.log"))

    cf_rc = run_goal("concurrentfind", tdir, test_hash)
    cf = copy_out(tdir, test_dot, test_hash, "ResultMethods.txt")
    dl = ml = cr = br = patches = 0
    if cf_rc == 124 and cf == 0:
        result = "time cap reached in concurrentfind"
    elif cf == 0:
        result = "no concurrent methods found"
    else:
        run_goal("delaylocs", tdir, test_hash)
        dl = copy_out(tdir, test_dot, test_hash, "Locations.txt")
        if dl == 0:
            result = "no delay locations found"
        else:
            run_goal("deltadebug", tdir, test_hash)
            ml = copy_out(tdir, test_dot, test_hash, "Locations_minimized.txt")
            run_goal("critsearch", tdir, test_hash)
            cr = copy_out(tdir, test_dot, test_hash, "CriticalPoints.csv")
            run_goal("barrierpointsearch", tdir, test_hash)
            br = copy_out(tdir, test_dot, test_hash, "BarrierPoints.csv")
            run_goal("patch", tdir, test_hash)
            patches = count_patches(test_dot)
            if cr > 0 and patches == 0:
                result = "critical points found (no patch)"
            elif patches > 0:
                result = "patch generated"
            else:
                result = "failure reproduced by delay injection; root cause not isolated"
    tests.append({
        "test": test_hash, "jdk": jdk, "concurrent_methods": cf,
        "delay_locations": dl, "minimized_locations": ml, "critical_points": cr,
        "barrier_points": br, "patch_files": patches, "result": result,
        "seconds": int(time.time() - t0),
    })
    print(f"{test_hash} {result} cf={cf} delay={dl}")

json.dump({
    "project": name, "url": url, "sha": sha, "module": module,
    "build": build, "jdk": jdk, "tests": tests,
}, open(out, "w"), indent=2)
print(f"wrote {out} ({len(tests)} tests) build={build}")
PY
