# TASK-004 — Deterministic Data/ simulator

- **ID:** T004
- **Status:** IN_PROGRESS
- **Phase:** 1 — Contracts and Simulation
- **Gate:** None

## Goal

Implement a seeded, configurable synthetic telemetry generator and the Data/ workspace.

## Dependencies

T003

## Allowed Scope

- Data/ (README.md, manifest.json, config/, simulated/)
- backend/app/datasource/simulator/
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

_Filled in by the executing agent with actual commands and results._
