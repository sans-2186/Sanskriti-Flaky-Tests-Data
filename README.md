# Sanskriti Tiwari — Flaky Test Data

**Student:** Sanskriti Tiwari (`sut230001@utdallas.edu`) · **Course:** RIDE

The run follows the course sample ([Ride-Flaky-Test-Detection](https://github.com/Reliable-SE-Research/Ride-Flaky-Test-Detection)): two separate inputs, one module at a time, logs kept.

## Flow

1. **iDFlakies and NonDex** run on **100 IDoFT modules** (`inputs/modules.csv`). Maven is limited to that module (`-pl <module> -am`), not the whole repository. JDK 8, then 11, then 17. iDFlakies uses 5 rounds (10 min cap). NonDex uses 3 runs (8 min cap).
2. **FlakeSync** does not use those findings. It runs on **140 NOD (async) tests** already listed in IDoFT (`inputs/nod_tests.csv`), grouped by module. A delay reproduction is a test with `delay_locations` > 0. Output files are `Class.method-Locations.txt` (a dot before the method name).
3. **Logs** for clone, install, iDFlakies, NonDex, and each FlakeSync goal are uploaded with the run and copied into `Sanskriti_Tiwari/logs/` when the merge job finishes.

"New" means the test name does not appear anywhere in IDoFT `pr-data.csv`.

Outputs land in `Sanskriti_Tiwari/` after the workflow **RIDE module flow** finishes: the same files as the sample (`*_idflakies.csv`, `*_nondex.csv`, `*_flakesync.csv`, `*_summary.csv`, `*_per_project.csv`, `*_report.md`, `table_cells/`).

The counts can differ from the sample. The order of work is the same.

This first run is 100 modules so the logs and FlakeSync delay counts can be checked against the sample. More modules are added later by appending rows to `inputs/modules.csv`. The workflow reads that file, so the next run picks them up.

## Earlier whole-repository run

`data/` is the previous run over entire repositories, with FlakeSync pointed at those iDFlakies/NonDex tests. That is why it reported thousands of tests and zero delay reproductions. It is not the result of this flow.
