# TASK-017 — Statistical rules and alarm-event engine

- **ID:** T017
- **Status:** IN_PROGRESS
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Implement EWMA, CUSUM, change detection, deterministic rules, hysteresis, and alarm events.

## Dependencies

T016

## Allowed Scope

- backend/app/monitoring/rules, alarms
- alarm APIs

Anything outside this list requires Principal Agent approval.

## Related Requirements

L4-07, L6-03, UI-09

## Acceptance Criteria

1. Detects S04–S08 and S19 with expected responses from golden cases; no alarms on S01.
2. Safety rules are deterministic, versioned, and cannot be disabled by non-admins.
3. Alarm lifecycle (raised, acknowledged, resolved) with audit.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/rules (golden cases)`

## Deliverables

- Rule and alarm engine

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
