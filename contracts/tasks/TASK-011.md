# TASK-011 — Signal mapping and preview APIs

- **ID:** T011
- **Status:** IN_PROGRESS
- **Phase:** 3 — Backend and Industrial Domain
- **Gate:** None

## Goal

Implement signal registry, mapping, grouping, viz templates, versioning, and preview APIs; connect Studio to them.

## Dependencies

T010

## Allowed Scope

- backend/app/signals
- API endpoints
- frontend Studio switched from mocks to API

Anything outside this list requires Principal Agent approval.

## Related Requirements

L2-01, L2-02, L2-03, L2-04, L2-05, UI-04, UI-05

## Acceptance Criteria

1. CRUD for signal definitions, mappings, groups; every change creates a config version.
2. Preview returns normalized and downsampled series separately.
3. Studio E2E works against the real backend with the simulated adapter.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/signals`
- Playwright E2E

## Deliverables

- Signal registry and APIs

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
