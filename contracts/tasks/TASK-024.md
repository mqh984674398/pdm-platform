# TASK-024 — Evidence fusion and maintenance decision engine

- **ID:** T024
- **Status:** TODO
- **Phase:** 6 — Optimization and Local LLM
- **Gate:** None

## Goal

Fuse rule, statistical, and model evidence into health states and recommendations under safety constraints.

## Dependencies

T017, T021, T022

## Allowed Scope

- backend/app/decision

Anything outside this list requires Principal Agent approval.

## Related Requirements

L6-01, L6-02, L6-03, L6-04, L6-05, GEN-04

## Acceptance Criteria

1. Typed outputs are never mixed without explicit interpretation rules.
2. Conflicting evidence and low eligibility produce WATCH or UNKNOWN with reasons.
3. Safety constraints cannot be overridden by models or LLM (tests).
4. Recommendations reference evidence and versions.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/decision (golden cases)`

## Deliverables

- Decision engine

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
