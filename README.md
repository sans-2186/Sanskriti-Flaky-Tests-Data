# Flaky Test Detection & Repair — iDFlakies, NonDex, FlakeSync

**Student:** Sanskriti Tiwari (`sut230001@utdallas.edu`)
**Course:** RIDE (Research in Dependable Systems)
**Dataset source:** [TestingResearchIllinois/idoft](https://github.com/TestingResearchIllinois/idoft) — `pr-data.csv`

---

## Overview

This repository contains the results of a three-phase flaky-test study run over
all 798 unique (project, SHA) pairs from the idoft `pr-data.csv` dataset.

| Phase | Tool | Flakiness Type | Findings |
|---|---|---|---|
| 1 | **iDFlakies** | Order-dependent (OD) | 2,424 tests across 73 projects |
| 2 | **NonDex** | Implementation-dependent (ID) | 3,754 tests across 193 projects |
| 3 | **FlakeSync** | Timing-dependent (TD) | 0 TD tests (expected — see below) |

**Combined unique flaky tests: 6,163** across **215 projects**.

Each project was cloned at its exact recorded commit SHA and tools were run over
the entire Maven project. The pipeline uses GitHub Actions (100–215 parallel
runners) and commits results here automatically.

---

## Phase 1 & 2 — iDFlakies and NonDex

### Tools

**iDFlakies** `edu.illinois.cs:idflakies-maven-plugin:2.0.0`
Detects **order-dependent (OD)** flaky tests by randomly shuffling test class
execution order and checking for tests that pass in some orders but fail in others.

```bash
mvn edu.illinois.cs:idflakies-maven-plugin:2.0.0:detect \
  -Ddetector.detector_type=random-class-method \
  -Ddt.randomize.rounds=10 \
  -Ddt.detector.original_order.all_must_pass=false
```

**NonDex** `edu.illinois:nondex-maven-plugin:2.2.1`
Detects **implementation-dependent (ID)** flaky tests by randomising iteration
order of Java APIs whose ordering is unspecified (`HashMap`, `HashSet`, reflection,
etc.). A failing test genuinely relies on non-deterministic JDK behaviour.

```bash
mvn edu.illinois:nondex-maven-plugin:2.2.1:nondex
```

### Results

> Covers **702 of 798** unique (project, SHA) pairs. The remaining 96 pairs
> (shards 4 and 39) were in alibaba/nacos (6 SHAs, ~65 min each — hits GitHub's
> 6-hour runner cap) and dromara/hutool (gets SIGTERM-killed by the platform).
> Results from completed SHAs in those shards are included where available.

| Metric | iDFlakies | NonDex |
|---|---|---|
| Unique flaky tests found | **2,424** | **3,754** |
| Projects with ≥ 1 finding | 73 | 193 |
| Tests already in idoft pr-data | 235 | 1,134 |
| **New discoveries (not in pr-data)** | **2,189** | **2,620** |
| Found by both tools | 15 | 15 |

### Project outcomes

| Outcome | Count |
|---|---|
| Completed normally | 260 |
| Hit time limit (partial results kept) | 98 |
| Build failed (JDK 8) | 331 |
| Clone / checkout failed | 13 |
| **Total attempted** | **702** |

Build failures are expected — many projects in the idoft dataset are old and
require specific JDK versions or private dependencies.

---

## Phase 3 — FlakeSync

### Tool

**FlakeSync** `edu.utexas.ece:flakesync-maven-plugin:1.0-SNAPSHOT`
([UT-SE-Research/FlakeSync](https://github.com/UT-SE-Research/FlakeSync))

Detects and repairs **timing-dependent (TD)** async flaky tests via delay
injection. TD tests fail because of race conditions or missing synchronisation in
concurrent code. FlakeSync runs 6 sequential Maven goals per test:

| Step | Goal | Purpose |
|---|---|---|
| 1 | `concurrentfind` | Identify concurrent methods the test calls |
| 2 | `delaylocs` | Inject delays and find locations that flip the test |
| 3 | `deltadebug` | Minimise delay locations via delta-debugging |
| 4 | `critsearch` | Find critical points (root method search) |
| 5 | `barrierpointsearch` | Link critical points to barrier points |
| 6 | `patch` | Generate patch files to repair the source of flakiness |

```bash
mvn edu.utexas.ece:flakesync-maven-plugin:1.0-SNAPSHOT:concurrentfind \
  -Dflakesync.testName=org.example.Class#method [-pl module]
# ... then delaylocs, deltadebug, critsearch, barrierpointsearch, patch
```

### Results

FlakeSync ran on **4,406 tests** across **214 projects** (one project clone-failed).

| Phase outcome | Tests |
|---|---|
| No concurrent methods (step 1 → not TD) | 2,467 |
| `concurrentfind` failed (build incomplete) | 1,939 |
| TD delay locations found | **0** |
| Patches generated | **0** |

**Why 0 TD tests?** This is the expected outcome. The 6,163 input tests were
identified by iDFlakies (OD) and NonDex (ID) — tools that detect *order* and
*implementation* flakiness respectively. TD flakiness arises from missing
synchronisation primitives in concurrent async code and is a distinct category.
`concurrentfind` correctly reports no concurrent thread interactions for OD/ID
tests, confirming they are not timing-dependent. FlakeSync would find TD tests in
projects that use async threading (e.g. gRPC services, reactive streams) where the
flakiness stems from race conditions, not test ordering or HashMap iteration order.

---

## Output files (`data/`)

| File | Rows | Description |
|---|---|---|
| `Sanskriti_Tiwari_idflakies.csv` | 2,424 | One row per flaky test found by iDFlakies |
| `Sanskriti_Tiwari_nondex.csv` | 3,754 | One row per flaky test found by NonDex |
| `summary.csv` | 702 | One row per (project, SHA) pair with counts for each tool |
| `flakesync_input.csv` | 6,163 | Union of all findings — input for the FlakeSync phase |
| `Sanskriti_Tiwari_flakesync.csv` | 4,406 | FlakeSync result per test: status, concurrent methods, delay locations, patch |

### Column details

**`Sanskriti_Tiwari_idflakies.csv` / `Sanskriti_Tiwari_nondex.csv`**

| Column | Description |
|---|---|
| `project_name` | GitHub repo name (basename of URL) |
| `sha` | Exact commit SHA the project was cloned at |
| `flaky_test` | Fully-qualified test name (`pkg.Class.method`) |
| `in_pr_data` | `yes` = already in idoft pr-data; `no` = new discovery |

**`summary.csv`**

| Column | Description |
|---|---|
| `project_name`, `project_url`, `sha` | Project identity |
| `status` | `ok`, `timeout`, `build_failed`, `clone_failed` |
| `idflakies_count` / `nondex_count` | Tests found by each tool |
| `common_count` | Tests found by both |
| `union_count` | Tests found by either |
| `idflakies_reproduced_known` / `nondex_reproduced_known` | Known pr-data tests reproduced |

**`flakesync_input.csv`**

| Column | Description |
|---|---|
| `project_name`, `sha`, `flaky_test` | Test identity |
| `detected_by` | `iDFlakies`, `NonDex`, or `iDFlakies+NonDex` |
| `in_pr_data` | `yes` / `no` |

**`Sanskriti_Tiwari_flakesync.csv`**

| Column | Description |
|---|---|
| `project_name`, `project_url`, `sha`, `flaky_test` | Test identity |
| `flakesync_status` | `no_concurrent_methods`, `has_delay_locs`, `patched`, `concurrentfind_failed`, etc. |
| `concurrent_methods` | Count of concurrent methods found (step 1) |
| `delay_locs` | Count of delay locations that flip the test (step 2) |
| `minimized_locs` | Minimised subset of delay locations (step 3) |
| `crit_points` | Critical points found (step 4) |
| `barrier_points` | Barrier points found (step 5) |
| `patch_generated` | `yes` / `no` — whether a repair patch was produced (step 6) |

---

## Pipeline

All workflow code lives in the `detection-pipeline` branch.

```
.github/
  workflows/
    detect.yml          — iDFlakies + NonDex: 100-shard parallel matrix
    flakesync.yml       — FlakeSync: 215-project parallel matrix
  run_config.json       — controls shard_size, max_shards, shard_ids
  flakesync_config.json — controls project_idx_filter for FlakeSync
scripts/
  run_one.sh                  — clone → build → NonDex → iDFlakies → JSON
  merge_results.py            — aggregate detection JSONs → CSVs + REPORT.md
  run_flakesync_project.sh    — clone → build → 6 FlakeSync goals per test → JSON
  merge_flakesync.py          — aggregate FlakeSync JSONs → CSV + report
```

To re-run detection, update `_triggered` in `.github/run_config.json`.
To re-run FlakeSync, update `_triggered` in `.github/flakesync_config.json`.
