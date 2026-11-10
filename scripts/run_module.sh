#!/usr/bin/env bash
# run_module.sh URL SHA MODULE LOG_DIR RESULT_JSON
#
# One IDoFT module. Clone that SHA, build with JDK 8 then 11 then 17,
# run iDFlakies and NonDex only in that module, and keep the logs.
# Whole-reactor runs are not this script.

set -uo pipefail

URL="${1:?url}"
SHA="${2:?sha}"
MODULE="${3:-}"
LOG_DIR="${4:?log dir}"
OUT_JSON="${5:?json}"

IDF_ROUNDS="${IDF_ROUNDS:-5}"
NONDEX_RUNS="${NONDEX_RUNS:-3}"
IDF_TIMEOUT="${IDF_TIMEOUT:-600}"
NONDEX_TIMEOUT="${NONDEX_TIMEOUT:-480}"
BUILD_TIMEOUT="${BUILD_TIMEOUT:-600}"

mkdir -p "$LOG_DIR"
NAME="$(echo "$URL" | awk -F/ '{print $(NF-1)"/"$NF}' | sed 's/\.git$//')"

SKIP=(
  -Dcheckstyle.skip=true -Dfindbugs.skip=true -Dspotbugs.skip=true
  -Dpmd.skip=true -Dfmt.skip=true -Dformatter.skip=true
  -Dspotless.check.skip=true -Drat.skip=true -Dlicense.skip=true
  -Denforcer.skip=true -Djacoco.skip=true -Dmaven.javadoc.skip=true
  -Dmaven.source.skip=true -Dgpg.skip=true -DskipITs=true
  -DfailIfNoTests=false
)

pick_java() {
  local v="$1" name="JAVA_HOME_${v}_X64" jh="" c
  if [ -n "${!name+x}" ]; then
    jh="${!name}"
  fi
  for c in "$jh" "/usr/lib/jvm/temurin-${v}-jdk-amd64" "/usr/lib/jvm/java-${v}-openjdk-amd64"; do
    if [ -n "$c" ] && [ -x "$c/bin/java" ]; then
      echo "$c"
      return 0
    fi
  done
  echo ""
}

use_jdk() {
  local jh
  jh="$(pick_java "$1")"
  if [ -z "$jh" ]; then
    return 1
  fi
  export JAVA_HOME="$jh"
  export PATH="$JAVA_HOME/bin:$PATH"
}

PL=()
if [ -n "$MODULE" ] && [ "$MODULE" != "." ]; then
  PL=(-pl "$MODULE" -am)
fi

WORKDIR="$(mktemp -d)"
CLONE="$WORKDIR/repo"
BUILD="install failed"
JDK_USED=""
IDF_RC=""
ND_RC=""
IDF_SEC=0
ND_SEC=0

cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

{
  echo "url=$URL"
  echo "sha=$SHA"
  echo "module=${MODULE:-<root>}"
} > "$LOG_DIR/meta.txt"

if ! git clone --filter=blob:none "$URL" "$CLONE" > "$LOG_DIR/clone.log" 2>&1; then
  echo '{"project":"'"$NAME"'","url":"'"$URL"'","sha":"'"$SHA"'","module":"'"$MODULE"'","build":"clone failed","jdk":"","idflakies":[],"nondex":[],"idflakies_run":"skipped (clone failed)","nondex_run":"skipped (clone failed)"}' > "$OUT_JSON"
  exit 0
fi

if ! git -C "$CLONE" checkout --force "$SHA" >> "$LOG_DIR/clone.log" 2>&1; then
  echo '{"project":"'"$NAME"'","url":"'"$URL"'","sha":"'"$SHA"'","module":"'"$MODULE"'","build":"checkout failed","jdk":"","idflakies":[],"nondex":[],"idflakies_run":"skipped (checkout failed)","nondex_run":"skipped (checkout failed)"}' > "$OUT_JSON"
  exit 0
fi

for v in 8 11 17; do
  if ! use_jdk "$v"; then
    echo "JDK $v not installed" >> "$LOG_DIR/install-jdk${v}.log"
    continue
  fi
  echo "=== JDK $v JAVA_HOME=$JAVA_HOME ===" > "$LOG_DIR/install-jdk${v}.log"
  if timeout "$BUILD_TIMEOUT" mvn -B -DskipTests "${SKIP[@]}" "${PL[@]}" install \
      -f "$CLONE/pom.xml" >> "$LOG_DIR/install-jdk${v}.log" 2>&1; then
    BUILD="install ok"
    JDK_USED="$v"
    cp "$LOG_DIR/install-jdk${v}.log" "$LOG_DIR/install.log"
    break
  fi
done

if [ "$BUILD" != "install ok" ]; then
  echo '{"project":"'"$NAME"'","url":"'"$URL"'","sha":"'"$SHA"'","module":"'"$MODULE"'","build":"install failed","jdk":"","idflakies":[],"nondex":[],"idflakies_run":"skipped (install failed)","nondex_run":"skipped (install failed)"}' > "$OUT_JSON"
  exit 0
fi

use_jdk "$JDK_USED"
IDF="edu.illinois.cs:idflakies-maven-plugin:2.0.0:detect"
NONDEX="edu.illinois:nondex-maven-plugin:2.2.1:nondex"

start=$(date +%s)
set +e
timeout "$IDF_TIMEOUT" mvn -B "${SKIP[@]}" "${PL[@]}" "$IDF" \
  -Ddetector.detector_type=random-class-method \
  -Ddt.randomize.rounds="$IDF_ROUNDS" \
  -Ddt.detector.original_order.all_must_pass=false \
  -f "$CLONE/pom.xml" > "$LOG_DIR/idflakies.log" 2>&1
IDF_RC=$?
set -e
IDF_SEC=$(( $(date +%s) - start ))

start=$(date +%s)
set +e
timeout "$NONDEX_TIMEOUT" mvn -B "${SKIP[@]}" "${PL[@]}" "$NONDEX" \
  -DnondexRuns="$NONDEX_RUNS" \
  -f "$CLONE/pom.xml" > "$LOG_DIR/nondex.log" 2>&1
ND_RC=$?
set -e
ND_SEC=$(( $(date +%s) - start ))

mkdir -p "$LOG_DIR/nondex-dir"
find "$CLONE" -path '*/.nondex/*/failures' -type f 2>/dev/null | while read -r f; do
  cp "$f" "$LOG_DIR/nondex-dir/$(echo "$f" | sha256sum | awk '{print $1}').failures" 2>/dev/null || true
done

python3 - "$CLONE" "$LOG_DIR/nondex.log" "$OUT_JSON" "$NAME" "$URL" "$SHA" "$MODULE" \
  "$BUILD" "$JDK_USED" "$IDF_RC" "$ND_RC" "$IDF_SEC" "$ND_SEC" << 'PY'
import json, os, re, sys

clone, nd_log, out, name, url, sha, module, build, jdk, idf_rc, nd_rc, idf_sec, nd_sec = sys.argv[1:]
TEST_RE = re.compile(r"^[\w$]+(\.[\w$]+)+$")

def canon(t):
    return t.strip().replace("#", ".").split("(")[0].strip()

idf = set()
for dirpath, _, filenames in os.walk(clone):
    if ".dtfixingtools" not in dirpath.replace("\\", "/"):
        continue
    for fn in filenames:
        path = os.path.join(dirpath, fn)
        if fn == "flaky-lists.json":
            try:
                data = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            for item in data.get("dts") or []:
                n = item.get("name", "") if isinstance(item, dict) else str(item)
                n = canon(n)
                if TEST_RE.match(n):
                    idf.add(n)
        elif fn == "list.txt":
            try:
                for line in open(path, encoding="utf-8", errors="replace"):
                    n = canon(line)
                    if TEST_RE.match(n):
                        idf.add(n)
            except OSError:
                pass

nd = set()
if os.path.isfile(nd_log):
    text = open(nd_log, encoding="utf-8", errors="replace").read()
    parts = text.split("Across all seeds:")
    if len(parts) > 1:
        for line in parts[-1].splitlines():
            raw = re.sub(r"^\[INFO\]\s*", "", line).strip()
            if not raw:
                continue
            n = canon(raw)
            if not TEST_RE.match(n):
                break
            nd.add(n)
for dirpath, _, filenames in os.walk(clone):
    if ".nondex" not in dirpath.replace("\\", "/"):
        continue
    if "failures" in filenames:
        try:
            for line in open(os.path.join(dirpath, "failures"), encoding="utf-8", errors="replace"):
                n = canon(line)
                if TEST_RE.match(n):
                    nd.add(n)
        except OSError:
            pass

def run_note(rc, sec):
    return f"rc={rc} seconds={sec}"

doc = {
    "project": name,
    "url": url,
    "sha": sha,
    "module": module,
    "build": build,
    "jdk": jdk,
    "idflakies": sorted(idf),
    "nondex": sorted(nd),
    "idflakies_run": run_note(idf_rc, idf_sec),
    "nondex_run": run_note(nd_rc, nd_sec),
}
json.dump(doc, open(out, "w"), indent=2)
print(f"{name} module={module or '<root>'} idf={len(idf)} nd={len(nd)} build={build}")
PY
