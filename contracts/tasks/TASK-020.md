# TASK-020 — Full-stack component health dashboard

- **ID:** T020
- **Status:** TODO
- **Phase:** 4 — Statistical Monitoring
- **Gate:** G3 (approval requested after this task)

## Goal

Connect overview, component map, charts, alarms, and maintenance views to live backend results on simulated data.

## Dependencies

T007, T017, T018, T019

## Allowed Scope

- frontend views switched to real APIs
- backend aggregation endpoints

Anything outside this list requires Principal Agent approval.

## Related Requirements

UI-01, UI-02, UI-03, UI-08, UI-09, L6-04

## Acceptance Criteria

1. End-to-end flow: simulated adapter → features → monitoring → alarms → UI.
2. Alarm review and feedback recorded.
3. All G3 scenarios demonstrable in UI with simulated badge.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest API integration`
- Playwright E2E

## Deliverables

- Full-stack dashboard
- G3 demonstration package (bilingual)

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
