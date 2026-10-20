#!/usr/bin/env python3
"""Build Google Sheet rows matching RIDE flaky-test template (gid 1918767711)."""

import csv
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PR_DATA = "/tmp/pr-data.csv"

HEADER = [
    "Tool",
    "Flaky Result (e.g. pass 74/100)",
    "In pr-data (yes/no)",
    "Project URL",
    "SHA Detected",
    "Module Path",
    "Fully-Qualified Test Name (packageName.ClassName.methodName)",
    "Category",
    "Status",
    "PR Link",
    "Notes",
]


def canon(t: str) -> str:
    return t.strip().replace("#", ".").split("(")[0].strip()


def load_pr_meta(path: str):
    by_url = {}
    by_name = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row["Project URL"].strip()
            sha = row["SHA Detected"].strip()
            test = canon(row["Fully-Qualified Test Name (packageName.ClassName.methodName)"])
            name = url.rstrip("/").split("/")[-1].replace(".git", "")
            meta = {
                "module": row["Module Path"].strip(),
                "category": row["Category"].strip(),
                "status": row["Status"].strip(),
                "pr_link": row["PR Link"].strip(),
                "notes": row["Notes"].strip(),
                "url": url,
            }
            by_url[(url, sha, test)] = meta
            by_name.setdefault((name, sha, test), meta)
    return by_url, by_name


def load_urls_from_summary():
    name_to_url = {}
    path = os.path.join(DATA, "summary.csv")
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name_to_url[row["project_name"].strip()] = row["project_url"].strip()
    return name_to_url


def load_in_pr_map():
    m = {}
    with open(os.path.join(DATA, "flakesync_input.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m[(row["project_name"], row["sha"], canon(row["flaky_test"]))] = row["in_pr_data"]
    return m


def meta_for(by_url, by_name, url, name, sha, test, in_pr):
    test = canon(test)
    if url and (url, sha, test) in by_url:
        return by_url[(url, sha, test)]
    if (name, sha, test) in by_name:
        return by_name[(name, sha, test)]
    return {
        "module": "",
        "category": "",
        "status": "",
        "pr_link": "",
        "notes": "",
        "url": url or "",
    }


def flakesync_result(status: str) -> str:
    mapping = {
        "no_concurrent_methods": "Not TD — no concurrent methods (step 1)",
        "no_delay_locs": "Not TD — no delay locations (step 2)",
        "has_delay_locs": "TD candidate — delay locations found",
        "patched": "TD — patch generated",
        "concurrentfind_failed": "FlakeSync incomplete (concurrentfind_failed)",
        "delaylocs_failed": "FlakeSync incomplete (delaylocs_failed)",
        "critsearch_failed": "FlakeSync incomplete (critsearch_failed)",
        "barrierpointsearch_failed": "FlakeSync incomplete (barrierpointsearch_failed)",
        "patch_failed": "FlakeSync incomplete (patch_failed)",
    }
    return mapping.get(status or "", status or "FlakeSync run")


def main():
    by_url, by_name = load_pr_meta(PR_DATA)
    name_to_url = load_urls_from_summary()
    in_pr_map = load_in_pr_map()
    rows = []

    def add_row(tool, flaky_result, in_pr, url, name, sha, test):
        meta = meta_for(by_url, by_name, url, name, sha, test, in_pr)
        if not url:
            url = meta.get("url") or name_to_url.get(name, "")
        rows.append([
            tool,
            flaky_result,
            in_pr,
            url,
            sha,
            meta["module"],
            canon(test),
            meta["category"],
            meta["status"],
            meta["pr_link"],
            meta["notes"],
        ])

    with open(os.path.join(DATA, "Sanskriti_Tiwari_idflakies.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name, sha, test = row["project_name"], row["sha"], row["flaky_test"]
            add_row(
                "iDFlakies",
                "OD flaky — detected (10 random class-method rounds)",
                row["in_pr_data"],
                name_to_url.get(name, ""),
                name,
                sha,
                test,
            )

    with open(os.path.join(DATA, "Sanskriti_Tiwari_nondex.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name, sha, test = row["project_name"], row["sha"], row["flaky_test"]
            add_row(
                "NonDex",
                "ID flaky — detected (non-deterministic API randomization)",
                row["in_pr_data"],
                name_to_url.get(name, ""),
                name,
                sha,
                test,
            )

    with open(os.path.join(DATA, "Sanskriti_Tiwari_flakesync.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["project_name"]
            sha, test = row["sha"], row["flaky_test"]
            in_pr = in_pr_map.get((name, sha, canon(test)), "no")
            url = row.get("project_url") or name_to_url.get(name, "")
            add_row(
                "FlakeSync",
                flakesync_result(row.get("flakesync_status", "")),
                in_pr,
                url,
                name,
                sha,
                test,
            )

    out = os.path.join(DATA, "RIDE_sheet_gid1918767711.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} data rows)")


if __name__ == "__main__":
    main()
