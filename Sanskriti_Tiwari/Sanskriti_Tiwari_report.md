# RIDE flaky-test detection — Sanskriti_Tiwari

Flow matches the course sample: iDFlakies and NonDex run on one IDoFT module at a time.
FlakeSync runs on NOD (async) tests taken from IDoFT `pr-data.csv`, not on the tests just found above.

iDFlakies + NonDex: 58 modules built. 40 candidates were clone, checkout, or install failures.
Settings: iDFlakies 2.0.0, random-class-method, 5 rounds, 10 min cap. NonDex 2.2.1, 3 runs, 8 min cap.
JDK 8, then 11, then 17. Logs are under `logs/`.

## Answers

1. **iDFlakies:** 58 flaky tests
2. **NonDex:** 359 flaky tests
3. **Detected by both:** 1
4. **Unique across both:** 416

### New vs. already in IDoFT

"New" = the fully-qualified test name does not appear anywhere in IDoFT `pr-data.csv`.

| | Flaky tests | New (not in IDoFT) |
|---|---:|---:|
| iDFlakies | 58 | 13 |
| NonDex | 359 | 94 |
| Detected by both | 1 | 1 |
| Unique across both | 416 | 106 |

## FlakeSync

Input is NOD tests from IDoFT. A delay reproduction is `delay_locations` > 0.

| Outcome | Tests |
|---|---:|
| install failed | 81 |
| failure reproduced by delay injection; root cause not isolated | 32 |
| no concurrent methods found | 20 |
| critical points found (no patch) | 3 |
| clone failed | 3 |
| no delay locations found | 1 |

Per-module counts: `Sanskriti_Tiwari_per_project.csv`.
One row per flaky test: `Sanskriti_Tiwari_idflakies.csv`, `Sanskriti_Tiwari_nondex.csv`.
One row per NOD test: `Sanskriti_Tiwari_flakesync.csv`.

