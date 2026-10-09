# TASK-022 — Decision-tree and XGBoost modeling

- **ID:** T022
- **Status:** TODO
- **Phase:** 5 — Predictive Models
- **Gate:** None

## Goal

Train and evaluate decision-tree and XGBoost models with leakage-safe validation.

## Dependencies

T021, T005

## Allowed Scope

- backend/app/prediction/models
- trainer jobs
- evaluation reports

Anything outside this list requires Principal Agent approval.

## Related Requirements

L5-03, L5-06, TST-03, TST-04

## Acceptance Criteria

1. Splits by lifecycle/time; leakage test passes.
2. Evaluation reports clearly marked as simulated performance.
3. Models registered with versions and feature schema references.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/models`
- evaluation report in contracts/evidence/T022/

## Deliverables

- Models and evaluation

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
