# TASK-005 — Golden Cases and scenario fixtures

- **ID:** T005
- **Status:** IN_PROGRESS
- **Phase:** 1 — Contracts and Simulation
- **Gate:** None

## Goal

Produce the 20 required scenarios and the Golden Case suite used for regression and replay.

## Dependencies

T004

## Allowed Scope

- Data/scenarios/, Data/fixtures/, Data/golden_cases/
- Scenario configs and generation script
- Golden-case loader for tests

Anything outside this list requires Principal Agent approval.

## Related Requirements

SIM-03, SIM-04, TST-02, GEN-07

## Acceptance Criteria

1. All 20 scenarios S01–S20 exist with seed, metadata, expected observable behavior, ground truth, expected health response, and required abstention/fallback cases.
2. Raw and normalized representations are provided per scenario.
3. Golden cases include explicit UNKNOWN/abstention expectations (S13–S18, S20).
4. Scenario regeneration is reproducible and verified against stored checksums.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/scenarios`
- checksum verification script

## Deliverables

- 20 scenario packages
- Golden case index

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
