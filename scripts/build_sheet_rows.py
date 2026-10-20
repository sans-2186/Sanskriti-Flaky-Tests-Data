#!/usr/bin/env python3
"""Build Google Sheet rows; uses pass_count/pass_trials when present (pass-rate CSVs)."""

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


def flaky_result_cell(pass_count, pass_trials, tool: str) -> str:
    if pass_count != "" and pass_trials != "":
        try:
            p, t = int(pass_count), int(pass_trials)
            return f"pass {p}/{t}"
        except ValueError:
            pass
    if tool == "FlakeSync":
        return "pass N/A"
    return "pass ≤74/100"


def load_pr_data(path: str):
    by_url, by_name, by_name_test = {}, {}, {}
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
            by_name[(name, sha, test)] = meta
            by_name_test.setdefault((name, test), meta)
    return by_url, by_name, by_name_test


def load_urls_from_summary():
    path = os.path.join(DATA, "summary.csv")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["project_name"].strip(): r["project_url"].strip() for r in csv.DictReader(f)}


def resolve_meta(by_url, by_name, by_name_test, url, name, sha, test, tool, in_pr_csv):
    test = canon(test)
    meta = None
    loose = False
    if url and (url, sha, test) in by_url:
        meta = dict(by_url[(url, sha, test)])
    elif (name, sha, test) in by_name:
        meta = dict(by_name[(name, sha, test)])
    elif (name, test) in by_name_test:
        meta = dict(by_name_test[(name, test)])
        loose = True
    else:
        meta = {"module": "", "category": "", "status": "", "pr_link": "", "notes": "", "url": url or ""}

    in_pr = in_pr_csv or ("yes" if not loose and ((url, sha, test) in by_url or (name, sha, test) in by_name) else "no")

    if not meta["category"]:
        if tool == "iDFlakies":
            meta["category"] = "OD"
        elif tool == "NonDex":
            meta["category"] = "ID"
        elif tool == "FlakeSync":
            meta["category"] = "TD (checked)"

    if in_pr == "no" and not meta["status"]:
        meta["status"] = "New detection"
    elif in_pr == "yes" and not meta["status"]:
        meta["status"] = "Listed in idoft pr-data"

    return meta, in_pr


def read_tool_csv(filename, tool):
    path = os.path.join(DATA, filename)
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        has_pass = "pass_count" in (reader.fieldnames or [])
        for row in reader:
            name = row["project_name"]
            sha = row["sha"]
            test = row["flaky_test"]
            in_pr = row.get("in_pr_data", "no")
            p = row.get("pass_count", "") if has_pass else ""
            tr = row.get("pass_trials", "") if has_pass else ""
            yield tool, name, sha, test, in_pr, p, tr


def main():
    import urllib.request
    urllib.request.urlretrieve(
        "https://raw.githubusercontent.com/TestingResearchIllinois/idoft/main/pr-data.csv",
        PR_DATA,
    )
    by_url, by_name, by_name_test = load_pr_data(PR_DATA)
    name_to_url = load_urls_from_summary()
    rows = []

    idf_file = "Sanskriti_Tiwari_idflakies_pass100.csv"
    if not os.path.exists(os.path.join(DATA, idf_file)):
        idf_file = "Sanskriti_Tiwari_idflakies.csv"
    nd_file = "Sanskriti_Tiwari_nondex_pass100.csv"
    if not os.path.exists(os.path.join(DATA, nd_file)):
        nd_file = "Sanskriti_Tiwari_nondex.csv"

    for tool, name, sha, test, in_pr, p, tr in read_tool_csv(idf_file, "iDFlakies"):
        url = name_to_url.get(name, "")
        meta, in_pr = resolve_meta(by_url, by_name, by_name_test, url, name, sha, test, tool, in_pr)
        if not url:
            url = meta.get("url") or name_to_url.get(name, "")
        rows.append([
            tool, flaky_result_cell(p, tr, tool), in_pr, url, sha,
            meta["module"], canon(test), meta["category"], meta["status"],
            meta["pr_link"], meta["notes"],
        ])

    for tool, name, sha, test, in_pr, p, tr in read_tool_csv(nd_file, "NonDex"):
        url = name_to_url.get(name, "")
        meta, in_pr = resolve_meta(by_url, by_name, by_name_test, url, name, sha, test, tool, in_pr)
        if not url:
            url = meta.get("url") or name_to_url.get(name, "")
        rows.append([
            tool, flaky_result_cell(p, tr, tool), in_pr, url, sha,
            meta["module"], canon(test), meta["category"], meta["status"],
            meta["pr_link"], meta["notes"],
        ])

    fs_path = os.path.join(DATA, "Sanskriti_Tiwari_flakesync.csv")
    if os.path.exists(fs_path):
        in_pr_map = {}
        inp = os.path.join(DATA, "flakesync_input.csv")
        if os.path.exists(inp):
            with open(inp, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    in_pr_map[(row["project_name"], row["sha"], canon(row["flaky_test"]))] = row["in_pr_data"]
        with open(fs_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name, sha, test = row["project_name"], row["sha"], row["flaky_test"]
                in_pr = in_pr_map.get((name, sha, canon(test)), "no")
                url = row.get("project_url") or name_to_url.get(name, "")
                meta, in_pr = resolve_meta(by_url, by_name, by_name_test, url, name, sha, test, "FlakeSync", in_pr)
                st = row.get("flakesync_status", "")
                fr = "pass N/A" if "failed" in st else flaky_result_cell("", "", "FlakeSync")
                rows.append([
                    "FlakeSync", fr, in_pr, url or meta.get("url", ""), sha,
                    meta["module"], canon(test), meta["category"], meta["status"],
                    meta["pr_link"], meta["notes"],
                ])

    out = os.path.join(DATA, "RIDE_sheet_gid1918767711.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
