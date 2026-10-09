# TASK-008 — SQL Data Source Studio frontend Demo

- **ID:** T008
- **Status:** TODO
- **Phase:** 2 — High-Fidelity Frontend
- **Gate:** G1 (approval requested after this task)

## Goal

Deliver a guided Data Source Studio demo (mocked backend) covering the full configuration workflow.

## Dependencies

T003, T005, T006

## Allowed Scope

- frontend views for Data Source Studio and signal preview
- Mocked endpoints matching T003 schemas

Anything outside this list requires Principal Agent approval.

## Related Requirements

UI-04, UI-05, L1-05, L2-01, L2-02, L2-03, L2-04, L2-05

## Acceptance Criteria

1. Guided steps: connection, schema inspection, device/signal selection, template choice, field mapping, units, grouping, preview, sampling/quality, component association, viz template, version save.
2. Ordinary user completes the workflow without writing SQL; template SQL is view-only for non-admins.
3. Preview chart uses simulated data and shows quality summary.
4. Configuration version history visible.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- vitest
- Playwright E2E of the full workflow
- screenshots zh/en

## Deliverables

- Studio demo
- G1 demonstration package (bilingual)

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
