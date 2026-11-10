#!/usr/bin/env python3
"""Turn per-module and per-NOD-group JSON into the sample layout.

  Sanskriti_Tiwari_idflakies.csv
  Sanskriti_Tiwari_nondex.csv
  Sanskriti_Tiwari_flakesync.csv
  Sanskriti_Tiwari_summary.csv
  Sanskriti_Tiwari_per_project.csv
  Sanskriti_Tiwari_report.md
  table_cells/*.csv

"New" means the test name never appears in IDoFT pr-data.csv.
"""

import csv
import glob
import json
import os
import sys

PR_DATA = os.environ.get("PR_DATA", "pr-data.csv")
DETECT_DIR = os.environ.get("DETECT_DIR", "detect_results")
FS_DIR = os.environ.get("FS_DIR", "fs_results")
OUT = os.environ.get("OUT_DIR", "Sanskriti_Tiwari")


def canon(t: str) -> str:
    return (t or "").strip().replace("#", ".").split("(")[0].strip()


def owner_repo(url: str) -> str:
    parts = [p for p in url.rstrip("/").split("/") if p]
    if len(parts) >= 2:
        return parts[-2] + "/" + parts[-1].replace(".git", "")
    return parts[-1] if parts else ""


def module_label(m: str) -> str:
    m = (m or "").strip()
    if m in ("", "."):
        return "(root)"
    return m


def load_known(path):
    names = set()
    if not os.path.isfile(path):
        return names
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            names.add(canon(row["Fully-Qualified Test Name (packageName.ClassName.methodName)"]))
    return names


def load_jsons(folder):
    docs = []
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            docs.append(json.load(open(path, encoding="utf-8")))
        except Exception as e:
            print(f"skip {path}: {e}", file=sys.stderr)
    return docs


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    known = load_known(PR_DATA)
    detect = load_jsons(DETECT_DIR)
    fs_docs = load_jsons(FS_DIR)
    os.makedirs(OUT, exist_ok=True)
    cells = os.path.join(OUT, "table_cells")

    idf_rows = []
    nd_rows = []
    per = []
    for doc in detect:
        project = doc.get("project") or owner_repo(doc.get("url", ""))
        sha = doc.get("sha", "")
        module = module_label(doc.get("module", ""))
        idf = [canon(t) for t in doc.get("idflakies") or []]
        nd = [canon(t) for t in doc.get("nondex") or []]
        for t in idf:
            idf_rows.append((project, sha, t))
        for t in nd:
            nd_rows.append((project, sha, t))
        both = len(set(idf) & set(nd))
        per.append([
            project, sha, module, doc.get("build", ""),
            doc.get("idflakies_run", ""), doc.get("nondex_run", ""),
            len(idf), len(nd), both, len(set(idf) | set(nd)),
        ])

    def dedup(rows):
        seen = set()
        out = []
        for r in rows:
            if r in seen:
                continue
            seen.add(r)
            out.append(r)
        return out

    idf_rows = dedup(idf_rows)
    nd_rows = dedup(nd_rows)
    idf_set = set(idf_rows)
    nd_set = set(nd_rows)
    both_rows = sorted(idf_set & nd_set)
    union = {}
    for project, sha, test in idf_rows:
        union[(project, sha, test)] = "iDFlakies"
    for project, sha, test in nd_rows:
        key = (project, sha, test)
        union[key] = "iDFlakies+NonDex" if key in union else "NonDex"

    def is_new(test):
        return canon(test) not in known

    write_csv(os.path.join(OUT, "Sanskriti_Tiwari_idflakies.csv"),
              ["project_name", "sha", "flaky_tests"], idf_rows)
    write_csv(os.path.join(OUT, "Sanskriti_Tiwari_nondex.csv"),
              ["project_name", "sha", "flaky_tests"], nd_rows)
    write_csv(os.path.join(OUT, "Sanskriti_Tiwari_per_project.csv"),
              ["project_name", "sha", "module", "build", "idflakies_run", "nondex_run",
               "idflakies", "nondex", "both", "unique_total"], per)

    unique_rows = [(p, s, t, how) for (p, s, t), how in sorted(union.items())]
    both_how = [(p, s, t, "iDFlakies+NonDex") for p, s, t in both_rows]

    def split_new(rows, test_index):
        return [r for r in rows if is_new(r[test_index])]

    write_csv(os.path.join(cells, "Sanskriti_Tiwari_idflakies_all.csv"),
              ["project_name", "sha", "flaky_tests"], idf_rows)
    write_csv(os.path.join(cells, "Sanskriti_Tiwari_idflakies_new.csv"),
              ["project_name", "sha", "flaky_tests"], split_new(idf_rows, 2))
    write_csv(os.path.join(cells, "Sanskriti_Tiwari_nondex_all.csv"),
              ["project_name", "sha", "flaky_tests"], nd_rows)
    write_csv(os.path.join(cells, "Sanskriti_Tiwari_nondex_new.csv"),
              ["project_name", "sha", "flaky_tests"], split_new(nd_rows, 2))
    write_csv(os.path.join(cells, "Sanskriti_Tiwari_both_all.csv"),
              ["project_name", "sha", "flaky_tests", "found_by"], both_how)
    write_csv(os.path.join(cells, "Sanskriti_Tiwari_both_new.csv"),
              ["project_name", "sha", "flaky_tests", "found_by"], split_new(both_how, 2))
    write_csv(os.path.join(cells, "Sanskriti_Tiwari_unique_all.csv"),
              ["project_name", "sha", "flaky_tests", "found_by"], unique_rows)
    write_csv(os.path.join(cells, "Sanskriti_Tiwari_unique_new.csv"),
              ["project_name", "sha", "flaky_tests", "found_by"], split_new(unique_rows, 2))

    fs_rows = []
    for doc in fs_docs:
        project = doc.get("project") or owner_repo(doc.get("url", ""))
        sha = doc.get("sha", "")
        module = module_label(doc.get("module", ""))
        for t in doc.get("tests") or []:
            test = t.get("test", "")
            if "#" not in test and "." in test:
                test = test.rsplit(".", 1)[0] + "#" + test.rsplit(".", 1)[1]
            fs_rows.append([
                project, sha, module, test, t.get("jdk", ""),
                t.get("concurrent_methods", 0), t.get("delay_locations", 0),
                t.get("minimized_locations", 0), t.get("critical_points", 0),
                t.get("barrier_points", 0), t.get("patch_files", 0),
                t.get("result", ""), t.get("seconds", 0),
            ])
    write_csv(os.path.join(OUT, "Sanskriti_Tiwari_flakesync.csv"),
              ["project_name", "sha", "module", "flaky_test", "jdk",
               "concurrent_methods", "delay_locations", "minimized_locations",
               "critical_points", "barrier_points", "patch_files", "result", "seconds"],
              fs_rows)

    def count_new(rows):
        return sum(1 for r in rows if is_new(r[2]))

    summary = [
        ["iDFlakies", len(idf_rows), count_new(idf_rows)],
        ["NonDex", len(nd_rows), count_new(nd_rows)],
        ["Detected by both", len(both_rows), sum(1 for r in both_rows if is_new(r[2]))],
        ["Unique across both", len(unique_rows), sum(1 for r in unique_rows if is_new(r[2]))],
    ]
    write_csv(os.path.join(OUT, "Sanskriti_Tiwari_summary.csv"),
              ["metric", "flaky_tests", "new_not_in_idoft"], summary)

    from collections import Counter
    outcomes = Counter(r[11] for r in fs_rows)
    built = sum(1 for d in detect if d.get("build") == "install ok")
    failed_build = len(detect) - built
    lines = [
        "# RIDE flaky-test detection — Sanskriti_Tiwari",
        "",
        "Flow matches the course sample: iDFlakies and NonDex run on one IDoFT module at a time.",
        "FlakeSync runs on NOD (async) tests taken from IDoFT `pr-data.csv`, not on the tests just found above.",
        "",
        f"iDFlakies + NonDex: {built} modules built. {failed_build} candidates were clone, checkout, or install failures.",
        "Settings: iDFlakies 2.0.0, random-class-method, 5 rounds, 10 min cap. NonDex 2.2.1, 3 runs, 8 min cap.",
        "JDK 8, then 11, then 17. Logs are under `logs/`.",
        "",
        "## Answers",
        "",
        f"1. **iDFlakies:** {len(idf_rows)} flaky tests",
        f"2. **NonDex:** {len(nd_rows)} flaky tests",
        f"3. **Detected by both:** {len(both_rows)}",
        f"4. **Unique across both:** {len(unique_rows)}",
        "",
        "### New vs. already in IDoFT",
        "",
        '"New" = the fully-qualified test name does not appear anywhere in IDoFT `pr-data.csv`.',
        "",
        "| | Flaky tests | New (not in IDoFT) |",
        "|---|---:|---:|",
        f"| iDFlakies | {len(idf_rows)} | {count_new(idf_rows)} |",
        f"| NonDex | {len(nd_rows)} | {count_new(nd_rows)} |",
        f"| Detected by both | {len(both_rows)} | {sum(1 for r in both_rows if is_new(r[2]))} |",
        f"| Unique across both | {len(unique_rows)} | {sum(1 for r in unique_rows if is_new(r[2]))} |",
        "",
        "## FlakeSync",
        "",
        "Input is NOD tests from IDoFT. A delay reproduction is `delay_locations` > 0.",
        "",
        "| Outcome | Tests |",
        "|---|---:|",
    ]
    for label, n in outcomes.most_common():
        lines.append(f"| {label} | {n} |")
    lines += [
        "",
        "Per-module counts: `Sanskriti_Tiwari_per_project.csv`.",
        "One row per flaky test: `Sanskriti_Tiwari_idflakies.csv`, `Sanskriti_Tiwari_nondex.csv`.",
        "One row per NOD test: `Sanskriti_Tiwari_flakesync.csv`.",
        "",
    ]
    with open(os.path.join(OUT, "Sanskriti_Tiwari_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", OUT, "idf", len(idf_rows), "nd", len(nd_rows), "fs", len(fs_rows))


if __name__ == "__main__":
    main()
