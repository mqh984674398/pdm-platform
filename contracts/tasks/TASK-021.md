# TASK-021 — Component-specific model routing

- **ID:** T021
- **Status:** TODO
- **Phase:** 5 — Predictive Models
- **Gate:** None

## Goal

Implement operator specs, component analysis templates, and routing with eligibility, timeout, and fallback.

## Dependencies

T015, T017

## Allowed Scope

- backend/app/prediction/routing, templates

Anything outside this list requires Principal Agent approval.

## Related Requirements

L5-01, L5-02, L6-01, GEN-07

## Acceptance Criteria

1. Each operator declares all L5-02 fields; registry rejects incomplete specs.
2. Routing per component type; ineligible inputs yield UnsupportedPrediction.
3. Timeouts trigger declared fallback.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/routing`

## Deliverables

- Routing engine and templates

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
