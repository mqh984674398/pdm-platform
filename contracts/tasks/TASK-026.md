# TASK-026 — Model registry, evaluation, and rollback

- **ID:** T026
- **Status:** IN_PROGRESS
- **Phase:** 6 — Optimization and Local LLM
- **Gate:** None

## Goal

Provide champion–challenger registry, Path C retraining, evaluation, promotion approval, and rollback.

## Dependencies

T022, T025

## Allowed Scope

- backend/app/core/registry
- model version view

Anything outside this list requires Principal Agent approval.

## Related Requirements

OPT-03, OPT-04, OPT-06, SEC-02, UI-11

## Acceptance Criteria

1. Promotion requires passing replay/golden gates and an authorized, audited action.
2. Rollback restores previous model and config in one action.
3. Drifting online data never enters verified healthy training data.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/registry`
- Playwright

## Deliverables

- Registry and UI

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
