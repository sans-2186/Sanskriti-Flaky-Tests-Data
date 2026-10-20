#!/usr/bin/env python3
"""Merge per-project JSON results into the deliverable CSVs and a summary report.

Usage:
    python3 merge_results.py  --results-dir DIR  --pr-data pr-data.csv  --out-dir DIR

The results-dir contains one JSON file per project written by run_one.sh.
"""

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict

IDFLAKIES_CSV = "Sanskriti_Tiwari_idflakies.csv"
NONDEX_CSV = "Sanskriti_Tiwari_nondex.csv"
SUMMARY_CSV = "summary.csv"
FLAKESYNC_CSV = "flakesync_input.csv"
REPORT_MD = "REPORT.md"


def canon(t: str) -> str:
    return t.strip().replace("#", ".").split("(")[0].strip()


def load_pr_data(path: str):
    """Return a set of (project_name, sha, canon_test) known from pr-data.csv."""
    known_exact = set()
    known_any_sha = set()
    if not path or not os.path.exists(path):
        return known_exact, known_any_sha
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row["Project URL"].strip()
            sha = row["SHA Detected"].strip()
            test = canon(row["Fully-Qualified Test Name (packageName.ClassName.methodName)"].strip())
            name = url.rstrip("/").split("/")[-1].replace(".git", "")
            known_exact.add((name, sha, test))
            known_any_sha.add((name, test))
    return known_exact, known_any_sha


def load_results(results_dir: str):
    records = []
    for fn in sorted(os.listdir(results_dir)):
        if not fn.endswith(".json"):
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
    ap.add_argument("--pr-data", default="")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    known_exact, known_any_sha = load_pr_data(args.pr_data)
    records = load_results(args.results_dir)

    if not records:
        print("No result JSON files found in", args.results_dir)
        return

    print(f"Loaded {len(records)} project results")

    # ---- per-tool unique test sets ----
    idf_rows = []   # (project, sha, test, in_pr_data)
    nd_rows = []

    status_counts = Counter()
    idf_set = set()   # (project, sha, canon_test)
    nd_set = set()
    idf_projects = set()
    nd_projects = set()
    known_targeted = 0
    idf_reproduced = 0
    nd_reproduced = 0

    for rec in records:
        name = rec["project"]
        sha = rec["sha"]
        status = rec.get("status", "unknown")
        status_counts[status] += 1

        idf_tests = [canon(t) for t in rec.get("idflakies", [])]
        nd_tests = [canon(t) for t in rec.get("nondex", [])]

        for t in idf_tests:
            in_pr = (name, sha, t) in known_exact
            idf_rows.append((name, sha, t, "yes" if in_pr else "no"))
            idf_set.add((name, sha, t))
            if in_pr:
                idf_reproduced += 1
        if idf_tests:
            idf_projects.add(name)

        for t in nd_tests:
            in_pr = (name, sha, t) in known_exact
            nd_rows.append((name, sha, t, "yes" if in_pr else "no"))
            nd_set.add((name, sha, t))
            if in_pr:
                nd_reproduced += 1
        if nd_tests:
            nd_projects.add(name)

        if status in ("ok", "timeout"):
            # Count how many known pr-data tests we targeted for this project
            for (pn, _, _t) in known_exact:
                if pn == name:
                    known_targeted += 1
                    break

    union_set = idf_set | nd_set
    common_set = idf_set & nd_set

    # deduplicate rows
    idf_rows_dedup = sorted({(r[0], r[1], r[2], r[3]) for r in idf_rows})
    nd_rows_dedup = sorted({(r[0], r[1], r[2], r[3]) for r in nd_rows})

    # ---- write CSVs ----
    write_csv(
        os.path.join(args.out_dir, IDFLAKIES_CSV),
        ["project_name", "sha", "flaky_test", "in_pr_data"],
        idf_rows_dedup,
    )
    write_csv(
        os.path.join(args.out_dir, NONDEX_CSV),
        ["project_name", "sha", "flaky_test", "in_pr_data"],
        nd_rows_dedup,
    )

    # summary per project
    summary_rows = []
    for rec in records:
        name = rec["project"]
        sha = rec["sha"]
        idf = [canon(t) for t in rec.get("idflakies", [])]
        nd = [canon(t) for t in rec.get("nondex", [])]
        common = set(idf) & set(nd)
        union = set(idf) | set(nd)
        idf_repr = sum(1 for t in idf if (name, sha, t) in known_exact)
        nd_repr = sum(1 for t in nd if (name, sha, t) in known_exact)
        summary_rows.append((
            name, rec.get("url", ""), sha,
            rec.get("status", ""),
            len(idf), len(nd), len(common), len(union),
            idf_repr, nd_repr,
        ))
    write_csv(
        os.path.join(args.out_dir, SUMMARY_CSV),
        ["project_name", "project_url", "sha", "status",
         "idflakies_count", "nondex_count", "common_count", "union_count",
         "idflakies_reproduced_known", "nondex_reproduced_known"],
        summary_rows,
    )

    # flakesync input: one row per unique test
    detected_by: dict[tuple, set] = defaultdict(set)
    module_of: dict[tuple, str] = {}
    for (name, sha, t, _) in idf_rows_dedup:
        k = (name, sha, t); detected_by[k].add("iDFlakies")
    for (name, sha, t, _) in nd_rows_dedup:
        k = (name, sha, t); detected_by[k].add("NonDex")
    write_csv(
        os.path.join(args.out_dir, FLAKESYNC_CSV),
        ["project_name", "sha", "flaky_test", "detected_by", "in_pr_data"],
        [
            (k[0], k[1], k[2], "+".join(sorted(v)),
             "yes" if (k[0], k[1], k[2]) in known_exact else "no")
            for k, v in sorted(detected_by.items())
        ],
    )

    # ---- console report ----
    attempted = len(records)
    built = status_counts["ok"] + status_counts["timeout"]
    failed = attempted - built

    print("\n" + "=" * 64)
    print(" DETECTION SUMMARY")
    print("=" * 64)
    print(f"Projects attempted              : {attempted}")
    print(f"Built and tested                : {built}")
    print(f"  completed normally            : {status_counts['ok']}")
    print(f"  hit time limit (partial kept) : {status_counts['timeout']}")
    print(f"Failed                          : {failed}")
    for s, n in sorted(status_counts.items()):
        if s not in ("ok", "timeout"):
            print(f"  {s:<30}: {n}")
    print("-" * 64)
    print(f"iDFlakies: {len(idf_set)} unique tests in {len(idf_projects)} projects")
    print(f"NonDex   : {len(nd_set)} unique tests in {len(nd_projects)} projects")
    print(f"Common (both)    : {len(common_set)}")
    print(f"Union (either)   : {len(union_set)}")
    print(f"iDFlakies only   : {len(idf_set - nd_set)}")
    print(f"NonDex only      : {len(nd_set - idf_set)}")
    print("-" * 64)
    print(f"Known pr-data tests reproduced by iDFlakies : {idf_reproduced}")
    print(f"Known pr-data tests reproduced by NonDex    : {nd_reproduced}")
    print(f"Tests NOT in pr-data (new discoveries)")
    new_idf = sum(1 for (n, s, t, ip) in idf_rows_dedup if ip == "no")
    new_nd  = sum(1 for (n, s, t, ip) in nd_rows_dedup  if ip == "no")
    print(f"  iDFlakies: {new_idf}  NonDex: {new_nd}")
    print("=" * 64)

    # ---- write REPORT.md ----
    report_path = os.path.join(args.out_dir, REPORT_MD)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"""# Flaky test detection report: iDFlakies vs NonDex

Source: `pr-data.csv` from TestingResearchIllinois/idoft.
Each project was cloned at its recorded SHA and both detectors were run over the
whole Maven project (no module restriction). Raw data: `summary.csv`.

## 1. Projects

| | Count |
|---|---|
| Attempted | {attempted} |
| Built and tested | {built} |
| &nbsp;&nbsp;completed normally | {status_counts['ok']} |
| &nbsp;&nbsp;hit time limit | {status_counts['timeout']} |
| Failed | {failed} |
""")
        for s, n in sorted(status_counts.items()):
            if s not in ("ok", "timeout"):
                f.write(f"| &nbsp;&nbsp;{s} | {n} |\n")

        f.write(f"""
## 2. Flaky tests found

| | iDFlakies | NonDex |
|---|---|---|
| Unique tests found | {len(idf_set)} | {len(nd_set)} |
| Projects with at least one find | {len(idf_projects)} | {len(nd_projects)} |
| Known pr-data tests reproduced | {idf_reproduced} | {nd_reproduced} |
| New (not in pr-data) | {new_idf} | {new_nd} |

## 3. Comparison

| | Tests |
|---|---|
| Found by both | {len(common_set)} |
| iDFlakies only | {len(idf_set - nd_set)} |
| NonDex only | {len(nd_set - idf_set)} |
| Total unique | {len(union_set)} |

## 4. FlakeSync input

File `flakesync_input.csv` — {len(detected_by)} unique tests from
{len({k[0] for k in detected_by})} projects, ready for FlakeSync phase analysis.
""")
    print(f"Wrote {os.path.relpath(report_path)}")


if __name__ == "__main__":
    main()
