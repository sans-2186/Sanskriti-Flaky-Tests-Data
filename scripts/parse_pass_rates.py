#!/usr/bin/env python3
"""Parse iDFlakies / NonDex outputs into per-test pass counts (for pass X/100 sheets)."""

import json
import os
import re
import sys
from collections import defaultdict

TEST_RE = re.compile(r"^[\w$]+(\.[\w$]+)*(\.[\w$]+)+$")


def canon(t: str) -> str:
    t = (t or "").strip().replace("#", ".").split("(")[0].strip()
    return t


def parse_nondex(root: str, logfile: str, trials: int) -> dict:
    """Return {canon_test: {pass, trials}} for tests that failed ≥1 shuffled run."""
    fail_runs: dict[str, set] = defaultdict(set)  # test -> set of run_dir paths
    run_dirs: set[str] = set()

    for dirpath, _, filenames in os.walk(root):
        if ".nondex" not in dirpath.replace("\\", "/").split("/"):
            continue
        if "failures" not in filenames:
            continue
        run_dirs.add(dirpath)
        fpath = os.path.join(dirpath, "failures")
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    t = canon(line)
                    if TEST_RE.match(t):
                        fail_runs[t].add(dirpath)
        except OSError:
            pass

    total = len(run_dirs) if run_dirs else 0
    if total == 0 and os.path.exists(logfile):
        total = trials
        with open(logfile, encoding="utf-8", errors="replace") as f:
            content = f.read()
        block = content.split("Across all seeds:")
        if len(block) > 1:
            for line in block[-1].splitlines():
                raw = re.sub(r"^\[INFO\]\s*", "", line).strip()
                if not raw:
                    continue
                t = canon(raw.replace("#", "."))
                if not TEST_RE.match(t):
                    break
                fail_runs[t].add("_summary_")

    if total == 0:
        total = trials

    rates = {}
    for t, runs in fail_runs.items():
        fc = len(runs)
        rates[t] = {"pass": max(0, total - fc), "trials": total}
    return rates


def _harvest_idf_json(obj, rates: dict, trials: int) -> None:
    if isinstance(obj, dict):
        name = obj.get("name") or obj.get("testName") or obj.get("test")
        if isinstance(name, str) and TEST_RE.match(name.strip()):
            c = canon(name)
            if "passCount" in obj and "failCount" in obj:
                p, f = int(obj["passCount"]), int(obj["failCount"])
                t = p + f or trials
                rates[c] = {"pass": p, "trials": t}
            elif "numPass" in obj and "numFail" in obj:
                p, f = int(obj["numPass"]), int(obj["numFail"])
                t = p + f or trials
                rates[c] = {"pass": p, "trials": t}
            elif "results" in obj and isinstance(obj["results"], list):
                res = obj["results"]
                p = sum(1 for x in res if x in (True, "PASS", "pass", "Pass"))
                f = sum(1 for x in res if x in (False, "FAIL", "fail", "Fail"))
                t = len(res) or trials
                rates[c] = {"pass": p, "trials": t}
        for v in obj.values():
            _harvest_idf_json(v, rates, trials)
    elif isinstance(obj, list):
        for v in obj:
            _harvest_idf_json(v, rates, trials)


def parse_idflakies(root: str, trials: int) -> dict:
    rates: dict = {}
    flaky_names: set[str] = set()

    for dirpath, _, filenames in os.walk(root):
        if ".dtfixingtools" not in dirpath.replace("\\", "/"):
            continue
        for fn in filenames:
            if not fn.endswith(".json"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            _harvest_idf_json(data, rates, trials)
            if isinstance(data, dict) and "dts" in data:
                for item in data["dts"]:
                    n = item.get("name", "") if isinstance(item, dict) else str(item)
                    if TEST_RE.match(n.strip()):
                        flaky_names.add(canon(n))

    for t in flaky_names:
        if t not in rates:
            # Detected flaky but no per-round stats in JSON — at least one failing order.
            rates[t] = {"pass": max(0, trials - 1), "trials": trials}
    return rates


def main():
    if len(sys.argv) < 3:
        print("Usage: parse_pass_rates.py nondex ROOT LOG TRIALS", file=sys.stderr)
        print("       parse_pass_rates.py idflakies ROOT TRIALS", file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[1]
    trials = int(sys.argv[-1])
    if mode == "nondex":
        root, logfile = sys.argv[2], sys.argv[3]
        print(json.dumps(parse_nondex(root, logfile, trials)))
    elif mode == "idflakies":
        root = sys.argv[2]
        print(json.dumps(parse_idflakies(root, trials)))
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
