# Flaky Test Detection — iDFlakies & NonDex

**Student:** Sanskriti Tiwari (`sut230001@utdallas.edu`)
**Course:** RIDE (Research in Dependable Systems)
**Dataset source:** [TestingResearchIllinois/idoft](https://github.com/TestingResearchIllinois/idoft) — `pr-data.csv`

---

## Overview

This repository contains the results of running two flaky-test detection tools —
**iDFlakies** and **NonDex** — over all 798 unique (project, SHA) pairs from the
idoft `pr-data.csv` dataset. Each project was cloned at its exact recorded commit
SHA and both detectors were run over the **entire Maven project** (no module
restriction), matching how the original idoft tests were identified.

The pipeline runs on GitHub Actions (100 parallel runners) so it completes in
roughly 2–6 hours and requires no local compute. Results are committed here
automatically after each run.

---

## Tools

### iDFlakies `edu.illinois.cs:idflakies-maven-plugin:2.0.0`

Detects **order-dependent (OD)** flaky tests by randomly shuffling the order in
which test classes are executed and checking for tests that pass in one order but
fail in another.

Command used:
```bash
mvn edu.illinois.cs:idflakies-maven-plugin:2.0.0:detect \
  -Ddetector.detector_type=random-class-method \
  -Ddt.randomize.rounds=10 \
  -Ddt.detector.original_order.all_must_pass=false
```

### NonDex `edu.illinois:nondex-maven-plugin:2.2.1`

Detects **implementation-dependent (ID)** flaky tests by randomising the
iteration order of Java APIs whose ordering is unspecified by the JDK spec
(e.g. `HashMap`, `HashSet`, reflection methods). A test that fails under
randomisation genuinely relies on non-deterministic behaviour.

Command used:
```bash
mvn edu.illinois:nondex-maven-plugin:2.2.1:nondex
```

---

## Results summary

> Numbers reflect the run over **702 of 798** unique (project, SHA) pairs.
> The remaining 96 pairs (shards 4 and 39) are being re-run due to a
> GitHub-side runner cancellation and are not yet included.

| Metric | iDFlakies | NonDex |
|---|---|---|
| Unique flaky tests found | **2,424** | **3,754** |
| Projects with ≥ 1 finding | 73 | 193 |
| Tests already in idoft pr-data | 235 | 1,134 |
| **New discoveries (not in pr-data)** | **2,189** | **2,620** |
| Found by both tools | 15 | 15 |
| Found by one tool only | 2,409 (iDFlakies) | 3,739 (NonDex) |

### Project outcomes

| Outcome | Count |
|---|---|
| Built and tested — completed | 260 |
| Built and tested — hit time limit (results kept) | 98 |
| Build failed (JDK 8 + 11) | 331 |
| Clone/checkout failed | 13 |
| **Total attempted** | **702** |

Build failures are expected — many projects in the idoft dataset are old and
require specific JDK versions or private dependencies. Results are recorded as
`build_failed` in `summary.csv` so they appear in the report.

---

## Output files

All files are in the `data/` folder.

| File | Description |
|---|---|
| `Sanskriti_Tiwari_idflakies.csv` | One row per flaky test found by iDFlakies. Columns: `project_name`, `sha`, `flaky_test`, `in_pr_data` |
| `Sanskriti_Tiwari_nondex.csv` | One row per flaky test found by NonDex. Same columns. |
| `summary.csv` | One row per (project, SHA) pair. Columns: `project_name`, `project_url`, `sha`, `status`, `idflakies_count`, `nondex_count`, `common_count`, `union_count`, `idflakies_reproduced_known`, `nondex_reproduced_known` |
| `flakesync_input.csv` | Union of all findings, one row per unique test. Columns: `project_name`, `sha`, `flaky_test`, `detected_by`, `in_pr_data`. Ready for the FlakeSync phase. |

### Column details

**`in_pr_data`** — `yes` if this exact (project, SHA, test) triple appears in the
idoft `pr-data.csv`; `no` if it is a new discovery not previously catalogued.

**`detected_by`** — in `flakesync_input.csv`, either `iDFlakies`, `NonDex`, or
`iDFlakies+NonDex` for tests flagged by both.

**`status`** in `summary.csv`:
- `ok` — both detectors ran to completion
- `timeout` — one or both detectors hit the time limit; partial results kept
- `build_failed` — Maven build failed on both JDK 8 and JDK 11
- `clone_failed` / `checkout_failed` — git operation failed

---

## How new discoveries were found

The idoft `pr-data.csv` contains tests that have been **manually confirmed** as
flaky through pull-request inspection. This study ran automated detection over the
same project SHAs and found additional tests that the detectors flag as flaky but
that have not yet been manually reviewed. These are labelled `in_pr_data=no`.

- **NonDex new discoveries** are high-confidence: if a test fails when HashMap
  iteration order is randomised, it definitively relies on unspecified JDK
  behaviour, which is a genuine source of flakiness.
- **iDFlakies new discoveries** are likely real but may include a small number of
  false positives caused by environment state rather than true test-order
  dependency.

---

## Pipeline

The detection pipeline lives in the `detection-pipeline` branch.

```
.github/
  workflows/detect.yml   — 3-job GitHub Actions pipeline
  run_config.json        — controls shard_size, max_shards, shard_ids
scripts/
  run_one.sh             — bash: clone → build → NonDex → iDFlakies → JSON
  merge_results.py       — aggregate shard JSONs → deliverable CSVs
```

To re-run the full pipeline, update `_triggered` in `.github/run_config.json`
on the `detection-pipeline` branch and push.

---

## Next step — FlakeSync

The `flakesync_input.csv` file (6,163 unique tests from 215 projects) is the
input for the FlakeSync phase, which attempts to reproduce each detected flaky
test in a controlled environment and classify it further.
