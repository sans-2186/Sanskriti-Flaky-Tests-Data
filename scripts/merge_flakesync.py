#!/usr/bin/env python3
"""Merge per-project FlakeSync JSON results into deliverable CSVs and a report.

Usage:
    python3 merge_flakesync.py  --results-dir DIR  --out-dir DIR
"""

import argparse
import csv
import json
import os
from collections import Counter

FLAKESYNC_CSV = "Sanskriti_Tiwari_flakesync.csv"
REPORT_MD = "flakesync_REPORT.md"


def load_results(results_dir: str):
    records = []
    for fn in sorted(os.listdir(results_dir)):
        if not fn.endswith("_flakesync.json"):
            continue
        path = os.path.join(results_dir, fn)
        try:
            with open(path, encoding="utf-8") as f:
                records.append(json.load(f))
        except Exception as e:
            print(f"  Warning: could not read {fn}: {e}")
    return records


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"Wrote {os.path.relpath(path)} ({len(rows)} data rows)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    records = load_results(args.results_dir)
    if not records:
        print("No *_flakesync.json files found in", args.results_dir)
        return

    print(f"Loaded {len(records)} project results")

    proj_status_counts = Counter()
    test_status_counts = Counter()
    patched_tests = []
    has_delay_locs_tests = []
    all_rows = []
    projects_with_td = set()

    for rec in records:
        name = rec.get("project", "")
        sha = rec.get("sha", "")
        url = rec.get("url", "")
        proj_status = rec.get("status", "unknown")
        proj_status_counts[proj_status] += 1

        for test_fqn, tr in rec.get("tests", {}).items():
            status = tr.get("status", "unknown")
            cf = tr.get("concurrent_methods", 0)
            dl = tr.get("delay_locs", 0)
            ml = tr.get("minimized_locs", 0)
            cr = tr.get("crit_points", 0)
            br = tr.get("barrier_points", 0)
            patched = tr.get("patch_generated", False)

            test_status_counts[status] += 1

            if dl > 0:
                projects_with_td.add(name)
            if patched:
                patched_tests.append((name, sha, test_fqn))

            all_rows.append((
                name, url, sha, test_fqn, status,
                cf, dl, ml, cr, br,
                "yes" if patched else "no",
            ))

    all_rows.sort()

    write_csv(
        os.path.join(args.out_dir, FLAKESYNC_CSV),
        ["project_name", "project_url", "sha", "flaky_test",
         "flakesync_status", "concurrent_methods", "delay_locs",
         "minimized_locs", "crit_points", "barrier_points", "patch_generated"],
        all_rows,
    )

    total_tests = len(all_rows)
    td_tests = sum(1 for r in all_rows if r[6] > 0)  # delay_locs > 0
    n_patched = sum(1 for r in all_rows if r[10] == "yes")
    no_concurrent = test_status_counts.get("no_concurrent_methods", 0)
    no_delay = test_status_counts.get("no_delay_locs", 0)

    print("\n" + "=" * 64)
    print(" FLAKESYNC SUMMARY")
    print("=" * 64)
    print(f"Projects processed    : {len(records)}")
    print(f"  built ok            : {proj_status_counts.get('ok', 0)}")
    print(f"  partial build       : {proj_status_counts.get('build_partial', 0)}")
    print(f"  clone failed        : {proj_status_counts.get('clone_failed', 0)}")
    print(f"Tests analyzed        : {total_tests}")
    print(f"  no concurrent (OD/ID not TD) : {no_concurrent}")
    print(f"  no delay locations  : {no_delay}")
    print(f"  has delay locs (TD) : {td_tests}")
    print(f"  patched             : {n_patched}")
    print(f"Projects with TD tests: {len(projects_with_td)}")
    print("=" * 64)

    report_path = os.path.join(args.out_dir, REPORT_MD)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"""# FlakeSync Results Report

Source: `flakesync_input.csv` (6,163 tests from iDFlakies + NonDex detection).
FlakeSync detects and repairs **timing-dependent (TD)** async flaky tests via delay injection.

## 1. Projects

| | Count |
|---|---|
| Projects processed | {len(records)} |
| Built successfully | {proj_status_counts.get('ok', 0)} |
| Partial build | {proj_status_counts.get('build_partial', 0)} |
| Clone failed | {proj_status_counts.get('clone_failed', 0)} |

## 2. Test Analysis

| Phase outcome | Tests |
|---|---|
| No concurrent methods found (not TD) | {no_concurrent} |
| Concurrent found but no delay locations | {no_delay} |
| Has delay locations (TD candidate) | {td_tests} |
| **Patch generated (repaired)** | **{n_patched}** |

## 3. FlakeSync Pipeline

Each test runs through 6 sequential Maven goals:

| Step | Goal | Purpose |
|---|---|---|
| 1 | `concurrentfind` | Find concurrent methods the test touches |
| 2 | `delaylocs` | Inject delays to find locations that flip the test |
| 3 | `deltadebug` | Minimize delay locations via delta-debugging |
| 4 | `critsearch` | Find critical points (root method search) |
| 5 | `barrierpointsearch` | Find barrier points linking critical points |
| 6 | `patch` | Generate patch files to repair the flakiness |

## 4. Results

- Tests with TD behavior (delay locations found): **{td_tests}** across **{len(projects_with_td)}** projects
- Tests with generated patch: **{n_patched}**
- Full data: `{FLAKESYNC_CSV}`
""")
    print(f"Wrote {os.path.relpath(report_path)}")


if __name__ == "__main__":
    main()
