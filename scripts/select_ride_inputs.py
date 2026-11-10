#!/usr/bin/env python3
"""Pick the two inputs the RIDE sample uses. They are not the same list.

Detection: 100 (project, SHA, module) rows that contain an ID or OD test.
FlakeSync: NOD (async) tests from IDoFT, spread across projects, more than
100 so a failed clone or build does not leave the run short.

"NOD" is a category token. NDOD alone is not NOD.
"""

import csv
import os
import sys

PR_DATA = os.environ.get("PR_DATA", "/tmp/pr-data.csv")
OUT_DIR = os.environ.get("OUT_DIR", "inputs")
N_MODULES = int(os.environ.get("N_MODULES", "100"))
N_NOD_TARGET = int(os.environ.get("N_NOD", "140"))
MAX_MODULES_PER_REPO = 2
MAX_NOD_PER_MODULE = 3

DETECT_CATS = {"ID", "OD", "OD-Vic", "OD-Brit"}


def tokens(cat: str):
    return [t.strip() for t in (cat or "").split(";") if t.strip()]


def owner_repo(url: str) -> str:
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        return parts[-1]
    return parts[-2] + "/" + parts[-1].replace(".git", "")


def module_of(raw: str) -> str:
    m = (raw or "").strip()
    if m in ("", ".", "(root)"):
        return ""
    return m


def main():
    if not os.path.isfile(PR_DATA):
        print(f"missing {PR_DATA}", file=sys.stderr)
        sys.exit(1)
    os.makedirs(OUT_DIR, exist_ok=True)

    # module key -> one representative row, and whether it has ID/OD
    modules = {}
    nod_rows = []
    with open(PR_DATA, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row["Project URL"].strip()
            sha = row["SHA Detected"].strip()
            module = module_of(row["Module Path"])
            test = row["Fully-Qualified Test Name (packageName.ClassName.methodName)"].strip()
            cat = tokens(row["Category"])
            key = (url, sha, module)
            rec = modules.setdefault(key, {"id_od": False, "url": url, "sha": sha, "module": module})
            if DETECT_CATS.intersection(cat):
                rec["id_od"] = True
            if "NOD" in cat:
                nod_rows.append({
                    "url": url,
                    "sha": sha,
                    "module": module,
                    "test": test,
                    "project": owner_repo(url),
                })

    # 100 modules: ID/OD first, at most 2 per repository, stable order
    per_repo = {}
    chosen = []
    ranked = sorted(modules.values(), key=lambda r: (not r["id_od"], r["url"].lower(), r["sha"], r["module"]))
    for rec in ranked:
        if not rec["id_od"]:
            continue
        repo = owner_repo(rec["url"])
        if per_repo.get(repo, 0) >= MAX_MODULES_PER_REPO:
            continue
        per_repo[repo] = per_repo.get(repo, 0) + 1
        chosen.append(rec)
        if len(chosen) >= N_MODULES:
            break

    mod_path = os.path.join(OUT_DIR, "modules.csv")
    with open(mod_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["idx", "project", "url", "sha", "module"])
        w.writeheader()
        for i, rec in enumerate(chosen):
            w.writerow({
                "idx": i,
                "project": owner_repo(rec["url"]),
                "url": rec["url"],
                "sha": rec["sha"],
                "module": rec["module"],
            })

    # NOD tests: up to 3 per module, round-robin by project until N_NOD_TARGET
    by_key = {}
    for rec in nod_rows:
        by_key.setdefault((rec["url"], rec["sha"], rec["module"]), []).append(rec)
    keys = sorted(by_key)
    picked = []
    round_i = 0
    while len(picked) < N_NOD_TARGET and round_i < MAX_NOD_PER_MODULE:
        progressed = False
        for key in keys:
            bucket = by_key[key]
            if round_i < len(bucket):
                picked.append(bucket[round_i])
                progressed = True
                if len(picked) >= N_NOD_TARGET:
                    break
        if not progressed:
            break
        round_i += 1

    # One FlakeSync job per (url, sha, module)
    groups = {}
    for rec in picked:
        groups.setdefault((rec["url"], rec["sha"], rec["module"]), []).append(rec["test"])

    nod_path = os.path.join(OUT_DIR, "nod_tests.csv")
    with open(nod_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["idx", "project", "url", "sha", "module", "test"])
        w.writeheader()
        for i, rec in enumerate(picked):
            w.writerow({"idx": i, **rec})

    group_path = os.path.join(OUT_DIR, "nod_groups.csv")
    with open(group_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["idx", "project", "url", "sha", "module", "tests"])
        for i, ((url, sha, module), tests) in enumerate(sorted(groups.items())):
            w.writerow([i, owner_repo(url), url, sha, module, "|".join(tests)])

    print(f"modules {len(chosen)} -> {mod_path}")
    print(f"nod tests {len(picked)} in {len(groups)} groups -> {nod_path}")


if __name__ == "__main__":
    main()
