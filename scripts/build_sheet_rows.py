#!/usr/bin/env python3
"""Build Google Sheet rows matching RIDE flaky-test template (gid 1918767711)."""

import csv
import os

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PR_DATA = "/tmp/pr-data.csv"

# Course sheet: stable if pass ≥74 out of 100; flaky if below.
PASS_STABLE_MIN = 74
PASS_TRIALS = 100

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


def load_pr_data(path: str):
    by_exact_url = {}
    by_exact_name = {}
    by_name_test = {}
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
            by_exact_url[(url, sha, test)] = meta
            by_exact_name[(name, sha, test)] = meta
            # Prefer first row for loose match; pr-data may have duplicates
            by_name_test.setdefault((name, test), meta)
    return by_exact_url, by_exact_name, by_name_test


def load_urls_from_summary():
    name_to_url = {}
    path = os.path.join(DATA, "summary.csv")
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name_to_url[row["project_name"].strip()] = row["project_url"].strip()
    return name_to_url


def load_flakesync_input_meta():
    """(name, sha, test) -> detected_by, in_pr_data"""
    m = {}
    with open(os.path.join(DATA, "flakesync_input.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            k = (row["project_name"], row["sha"], canon(row["flaky_test"]))
            m[k] = row["detected_by"]
    return m


def category_from_detected_by(detected_by: str) -> str:
    if not detected_by:
        return "TD (FlakeSync checked)"
    if "iDFlakies" in detected_by and "NonDex" in detected_by:
        return "OD; ID"
    if "NonDex" in detected_by:
        return "ID"
    if "iDFlakies" in detected_by:
        return "OD"
    return detected_by


def resolve_meta(by_exact_url, by_exact_name, by_name_test, url, name, sha, test, tool, detected_by):
    test = canon(test)
    loose = False
    meta = None
    if url and (url, sha, test) in by_exact_url:
        meta = dict(by_exact_url[(url, sha, test)])
    elif (name, sha, test) in by_exact_name:
        meta = dict(by_exact_name[(name, sha, test)])
    elif (name, test) in by_name_test:
        meta = dict(by_name_test[(name, test)])
        loose = True
    else:
        meta = {
            "module": "",
            "category": "",
            "status": "",
            "pr_link": "",
            "notes": "",
            "url": url or "",
        }

    in_pr = "yes" if not loose and (
        (url and (url, sha, test) in by_exact_url)
        or (name, sha, test) in by_exact_name
    ) else "no"

    if not meta["category"]:
        if tool == "iDFlakies":
            meta["category"] = "OD"
        elif tool == "NonDex":
            meta["category"] = "ID"
        elif tool == "FlakeSync":
            meta["category"] = category_from_detected_by(detected_by)

    if in_pr == "no":
        if loose:
            extra = (
                f"Same test name in pr-data under a different SHA for this project; "
                f"Category/Status/PR from that catalog row. Current SHA: {sha[:7]}."
            )
        else:
            extra = f"Automated detection ({tool}); not in idoft pr-data at this SHA."
        if meta["notes"]:
            if extra not in meta["notes"]:
                meta["notes"] = meta["notes"] + " | " + extra
        else:
            meta["notes"] = extra
        if not meta["status"]:
            meta["status"] = "New detection"
    elif not meta["status"]:
        meta["status"] = "Listed in idoft pr-data"

    if in_pr == "yes" and not meta["notes"]:
        meta["notes"] = "Row matched idoft pr-data at this project URL, SHA, and test name."

    return meta, in_pr


def append_note(meta: dict, line: str) -> None:
    if line in (meta.get("notes") or ""):
        return
    meta["notes"] = f"{meta['notes']} | {line}" if meta.get("notes") else line


def idflakies_flaky_result() -> str:
    # Detector flagged order-dependent failure; treat as below stable pass threshold.
    return (
        f"pass ≤{PASS_STABLE_MIN - 1}/{PASS_TRIALS} "
        f"(flaky; stable needs ≥{PASS_STABLE_MIN}/{PASS_TRIALS} pass)"
    )


def nondex_flaky_result() -> str:
    return (
        f"pass ≤{PASS_STABLE_MIN - 1}/{PASS_TRIALS} "
        f"(flaky; stable needs ≥{PASS_STABLE_MIN}/{PASS_TRIALS} pass)"
    )


def flakesync_result(status: str) -> str:
    mapping = {
        "no_concurrent_methods": "pass N/A — not TD (no concurrent methods)",
        "no_delay_locs": "pass N/A — not TD (no delay locations)",
        "has_delay_locs": (
            f"pass ≤{PASS_STABLE_MIN - 1}/{PASS_TRIALS} (TD candidate; delay locs found)"
        ),
        "patched": (
            f"pass ≤{PASS_STABLE_MIN - 1}/{PASS_TRIALS} (TD; repair patch generated)"
        ),
        "concurrentfind_failed": "pass N/A — FlakeSync incomplete (concurrentfind)",
        "delaylocs_failed": "pass N/A — FlakeSync incomplete (delaylocs)",
        "critsearch_failed": "pass N/A — FlakeSync incomplete (critsearch)",
        "barrierpointsearch_failed": "pass N/A — FlakeSync incomplete (barrierpointsearch)",
        "patch_failed": "pass N/A — FlakeSync incomplete (patch)",
    }
    base = mapping.get(status or "", f"pass N/A — {status or 'FlakeSync run'}")
    return f"{base}; stable threshold ≥{PASS_STABLE_MIN}/{PASS_TRIALS} pass"


def main():
    by_exact_url, by_exact_name, by_name_test = load_pr_data(PR_DATA)
    name_to_url = load_urls_from_summary()
    detected_by_map = load_flakesync_input_meta()
    rows = []

    def add_row(
        tool,
        flaky_result,
        name,
        sha,
        test,
        url="",
        detected_by="",
        in_pr_csv="",
        detector_note="",
    ):
        if not url:
            url = name_to_url.get(name, "")
        meta, in_pr_exact = resolve_meta(
            by_exact_url, by_exact_name, by_name_test,
            url, name, sha, test, tool, detected_by,
        )
        if detector_note:
            append_note(meta, detector_note)
        in_pr = in_pr_csv if in_pr_csv else ("yes" if in_pr_exact else "no")
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
            add_row(
                "iDFlakies",
                idflakies_flaky_result(),
                row["project_name"],
                row["sha"],
                row["flaky_test"],
                in_pr_csv=row["in_pr_data"],
                detector_note=(
                    "iDFlakies: 10 random class-method rounds; "
                    "per-test pass X/100 not logged (detector reports flaky if order-dependent failure seen)."
                ),
            )

    with open(os.path.join(DATA, "Sanskriti_Tiwari_nondex.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            add_row(
                "NonDex",
                nondex_flaky_result(),
                row["project_name"],
                row["sha"],
                row["flaky_test"],
                in_pr_csv=row["in_pr_data"],
                detector_note=(
                    "NonDex: 5 seeds (nondexRuns=5 in CI); "
                    "per-test pass X/100 not logged (flaky if any seed fails)."
                ),
            )

    in_pr_map = {}
    with open(os.path.join(DATA, "flakesync_input.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            in_pr_map[(row["project_name"], row["sha"], canon(row["flaky_test"]))] = row["in_pr_data"]

    with open(os.path.join(DATA, "Sanskriti_Tiwari_flakesync.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name, sha, test = row["project_name"], row["sha"], row["flaky_test"]
            db = detected_by_map.get((name, sha, canon(test)), "")
            add_row(
                "FlakeSync",
                flakesync_result(row.get("flakesync_status", "")),
                name,
                sha,
                test,
                row.get("project_url") or "",
                detected_by=db,
                in_pr_csv=in_pr_map.get((name, sha, canon(test)), "no"),
            )

    out = os.path.join(DATA, "RIDE_sheet_gid1918767711.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} data rows)")


if __name__ == "__main__":
    main()
