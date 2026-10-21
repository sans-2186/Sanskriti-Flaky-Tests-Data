# Sanskriti Tiwari — Flaky Test Data

**Student:** Sanskriti Tiwari (`sut230001@utdallas.edu`) · **Course:** RIDE

Adds `data/`: iDFlakies and NonDex on **702** (project, SHA) pairs from [idoft](https://github.com/TestingResearchIllinois/idoft) `pr-data.csv`, and FlakeSync on **6,163** union flaky tests from that detection run.

| | Flaky tests | New (not in IDoFT) |
|---|---:|---:|
| **iDFlakies** | [2,424](data/Sanskriti_Tiwari_idflakies.csv) | 2,189 |
| **NonDex** | [3,754](data/Sanskriti_Tiwari_nondex.csv) | 2,620 |
| **Both** | 15 | 11 |
| **Unique total** | [6,163](data/flakesync_input.csv) | 4,798 |
| **FlakeSync (TD confirmed)** | [0](data/Sanskriti_Tiwari_flakesync.csv) | — |

New counts are rows with `in_pr_data=no` in the linked CSVs. iDFlakies and NonDex numbers are detector candidates (5 NonDex seeds, 10 iDFlakies rounds). FlakeSync did not confirm any of them as timing-dependent.

| FlakeSync outcome | Tests |
|---|---:|
| TD (delay locations found) | **0** |
| No concurrent methods | 2,467 |
| `concurrentfind` failed (build / plugin) | 1,939 |
| Listed in the union, never run | 2,501 |
| Patches | **0** |

Per (project, SHA), [summary.csv](data/summary.csv) has the detection counts plus `flakesync_checked`, `flakesync_no_concurrent`, `flakesync_failed`, `flakesync_not_run`, `flakesync_td`, and `flakesync_patched`. A large `nondex_count` with `flakesync_td` = 0 means FlakeSync did not treat that batch as timing-dependent flakes.

---

## Tools (detection settings)

- **iDFlakies** `2.0.0` — random class/method order, **10** rounds (`random-class-method`).
- **NonDex** `2.2.1` — default **5** seeds over the full Maven project.
- **FlakeSync** `1.0-SNAPSHOT` — six goals per test (`concurrentfind` … `patch`) on the union input list.

702/798 idoft pairs completed (96 missing: mostly nacos shard timeouts and hutool runner kills). Pipeline workflows live on branch `detection-pipeline`.

---

## Files in `data/`

| File | Description |
|---|---|
| [Sanskriti_Tiwari_idflakies.csv](data/Sanskriti_Tiwari_idflakies.csv) | OD flaky tests (`project_name`, `sha`, `flaky_test`, `in_pr_data`) |
| [Sanskriti_Tiwari_nondex.csv](data/Sanskriti_Tiwari_nondex.csv) | ID flaky tests (same columns) |
| [flakesync_input.csv](data/flakesync_input.csv) | Union of findings (`detected_by`, `in_pr_data`) |
| [Sanskriti_Tiwari_flakesync.csv](data/Sanskriti_Tiwari_flakesync.csv) | FlakeSync status and counts per test |
| [summary.csv](data/summary.csv) | One row per (project, SHA): iDFlakies, NonDex, and FlakeSync counts |
