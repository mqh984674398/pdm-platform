# TASK-025 — Historical replay and rapid parameter optimization

- **ID:** T025
- **Status:** TODO
- **Phase:** 6 — Optimization and Local LLM
- **Gate:** None

## Goal

Replay history through the pipeline and run controlled Path A/B optimization with comparison UI.

## Dependencies

T024, T005

## Allowed Scope

- backend/app/core/replay, optimization
- optimization comparison view

Anything outside this list requires Principal Agent approval.

## Related Requirements

OPT-01, OPT-02, OPT-04, OPT-05, TST-02, UI-10

## Acceptance Criteria

1. Replay is time-ordered with no future leakage.
2. Candidate configs evaluated on replay and golden cases; safety rules unchanged.
3. Comparison view shows champion vs candidate.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/replay`
- Playwright

## Deliverables

- Replay and optimization

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
