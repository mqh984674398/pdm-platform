# TASK-018 — Maintenance stabilization and impact analysis

- **ID:** T018
- **Status:** TODO
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Analyze pre/post-maintenance behavior under compatible regimes and drive the workflow outcome.

## Dependencies

T014, T016, T017

## Allowed Scope

- backend/app/equipment/maintenance_impact

Anything outside this list requires Principal Agent approval.

## Related Requirements

L3-07, L3-08, L4-05

## Acceptance Criteria

1. Pre vs post comparison restricted to compatible regimes.
2. S09 yields improvement, S10 deterioration → REVIEW_REQUIRED, S11 partial effect reported.
3. Stabilization window configurable; insufficient data yields UNKNOWN.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/maintenance_impact`

## Deliverables

- Impact analysis module

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
