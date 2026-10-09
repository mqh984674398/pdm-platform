# TASK-007 — Machine dashboard and component status map

- **ID:** T007
- **Status:** TODO
- **Phase:** 2 — High-Fidelity Frontend
- **Gate:** None

## Goal

Deliver the multi-machine overview and interactive SVG component status map driven by simulated scenario data.

## Dependencies

T003, T005, T006

## Allowed Scope

- frontend views: overview, machine detail, component detail drawer
- SVG diagrams for the six component types
- Mock API layer reading fixtures

Anything outside this list requires Principal Agent approval.

## Related Requirements

UI-01, UI-02, UI-03, GEN-03

## Acceptance Criteria

1. Overview shows multiple machines with health summaries and simulated badge.
2. SVG map highlights components by health state; hover and click show details.
3. Component detail shows history, health, lifecycle, and recent maintenance from fixtures.
4. Every health state including UNKNOWN is demonstrated with meaningful scenario data.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- vitest
- Playwright E2E navigation
- screenshots zh/en

## Deliverables

- Overview and machine views
- Evidence screenshots

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
