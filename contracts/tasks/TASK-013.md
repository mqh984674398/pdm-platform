# TASK-013 — Operating-regime and movement-cycle processing

- **ID:** T013
- **Status:** IN_PROGRESS
- **Phase:** 3 — Backend and Industrial Domain
- **Gate:** None

## Goal

Classify operating state and regime, and segment actuator movement cycles.

## Dependencies

T012

## Allowed Scope

- backend/app/equipment/state, regimes, cycles

Anything outside this list requires Principal Agent approval.

## Related Requirements

L3-02, L3-03, L3-04, L4-03

## Acceptance Criteria

1. Operating state derivation with UNKNOWN when evidence is insufficient.
2. Regime assignment for S02; unknown regimes reported as unsupported (S17).
3. Cylinder extend/retract and vacuum release cycles segmented; incomplete operations flagged (S18).

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/equipment (golden cases)`

## Deliverables

- State, regime, cycle modules

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
