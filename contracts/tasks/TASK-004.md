# TASK-004 — Deterministic Data/ simulator

- **ID:** T004
- **Status:** DONE
- **Phase:** 1 — Contracts and Simulation
- **Gate:** None

## Goal

Implement a seeded, configurable synthetic telemetry generator and the Data/ workspace.

## Dependencies

T003

## Allowed Scope

- Data/ (README.md, manifest.json, config/, simulated/)
- backend/app/simulation/ (generator; see DECISIONS D-008) and backend/app/datasource/simulated.py (simulated L1 adapter)
- tools/ simulator CLI

Anything outside this list requires Principal Agent approval.

## Related Requirements

SIM-01, SIM-02, SIM-05, GEN-03, L1-07

## Acceptance Criteria

1. Same seed + config produces byte-identical output.
2. Supports multiple machines, component instances, regimes, timestamps, units, maintenance events, lifecycle IDs.
3. Emits raw IoT-style rows (deviceid/keyname/ts/value style) and normalized signal rows.
4. Covers ball screw (speed, torque), linear motor (speed), vacuum release duration, cylinder extend/retract durations; cam/gear as templates only.
5. Every generated file and record is labeled simulated; manifest.json lists files, seeds, and generator version.
6. Simulated adapter implements the L1 adapter interface.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/simulator (determinism, schema conformity, labeling)`

## Deliverables

- Data/ workspace
- Simulator package and CLI

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

2026-10-09:

- `tools/ci_local.sh` → exit 0 (log `contracts/evidence/T004/ci_local.log`): pytest 41 passed on Python 3.11 and 3.12 (16 in `tests/test_simulator.py`); drift check OK; frontend checks green.
- `python -m app.simulation ../Data/config/demo_small.json` → 19,329 raw rows in 0.34 s; dataset in `Data/simulated/demo_small/`.
- AC1 determinism: `test_same_seed_is_byte_identical` (all files) and `test_committed_demo_dataset_matches_generator` pass on 3.11 and 3.12; `.gitattributes` forces LF so Windows checkouts stay byte-identical.
- AC2: multiple machines/components/recipes/states (`test_multiple_regimes_and_states_present`), lifecycles and maintenance (`test_lubrication_improves_without_resetting_wear`, `test_replacement_creates_new_lifecycle_and_preserves_history`), effects (`test_torque_tracks_friction_drift`), data faults (`test_data_faults_are_applied_and_logged`).
- AC3: raw IoT-style `raw_telemetry.csv` and `normalized.csv`; `test_normalized_is_raw_with_mapping_conversion`.
- AC4: all four telemetry component types with plausible units (`test_units_physically_plausible`); cam/gear template-only (`test_template_only_components_have_no_telemetry`).
- AC5: `test_everything_is_labeled_simulated`; `SIM-` device prefix enforced by config schema; manifest lists files, seeds, generator version, checksums.
- AC6: `SimulatedAdapter` implements `TimeSeriesAdapter` (`test_adapter_contract`).
- Scope note: generator placed in `backend/app/simulation/` per DECISIONS D-008.
