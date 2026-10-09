# TASK-015 — Feature extraction and feature versioning

- **ID:** T015
- **Status:** TODO
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Extract per-window/per-cycle features with declared, versioned feature schemas.

## Dependencies

T013, T014

## Allowed Scope

- backend/app/monitoring/features
- feature store tables

Anything outside this list requires Principal Agent approval.

## Related Requirements

L4-03, L4-04, GEN-06

## Acceptance Criteria

1. Feature sets per component type with versioned schemas.
2. Condition-normalized residuals for torque vs speed/regime.
3. Features carry regime, lifecycle, and source window references; no future data used.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/features (includes leakage test)`

## Deliverables

- Feature module and store

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
