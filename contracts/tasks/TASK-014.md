# TASK-014 — Component lifecycle and maintenance services

- **ID:** T014
- **Status:** IN_PROGRESS
- **Phase:** 3 — Backend and Industrial Domain
- **Gate:** G2 (approval requested after this task)

## Goal

Implement topology, lifecycle, maintenance events, and the maintenance workflow state machine with persistence.

## Dependencies

T013

## Allowed Scope

- backend/app/equipment/lifecycle, maintenance
- Alembic migrations
- APIs

Anything outside this list requires Principal Agent approval.

## Related Requirements

L3-01, L3-05, L3-06, L3-07, L3-08, SEC-02

## Acceptance Criteria

1. Replacement (S12) preserves history and starts a new lifecycle.
2. Lubrication (S09/S10) does not reset aging.
3. Workflow transitions MAINTENANCE_EVENT → STABILIZATION → POST_MAINTENANCE_VALIDATION → NORMAL_MONITORING | REVIEW_REQUIRED enforced and audited.
4. Migrations apply and roll back cleanly on PostgreSQL.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/lifecycle`
- `alembic upgrade/downgrade on test DB`

## Deliverables

- Lifecycle and maintenance services
- G2 demonstration package (bilingual)

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
