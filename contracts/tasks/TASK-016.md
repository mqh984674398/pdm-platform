# TASK-016 — Healthy/adaptive baselines and degradation monitoring

- **ID:** T016
- **Status:** TODO
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Implement the three independent baselines and degradation tracking.

## Dependencies

T015, T014

## Allowed Scope

- backend/app/monitoring/baselines, degradation

Anything outside this list requires Principal Agent approval.

## Related Requirements

L4-05, L4-06, L4-07, OPT-05

## Acceptance Criteria

1. Verified healthy reference only changes through an explicit, audited verification action.
2. Adaptive baseline tracks regime-normalized behavior; normal aging (S03) is visible against the frozen reference.
3. Degradation history persists across maintenance and lifecycle boundaries correctly.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/baselines (S01, S03, S04, S09–S12)`

## Deliverables

- Baseline and degradation modules

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
