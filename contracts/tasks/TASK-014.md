# TASK-014 — Component lifecycle and maintenance services

- **ID:** T014
- **Status:** DONE
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

Executed 2026-10-09 by the executing agent.

### Commands and results

- `PDM_TEST_PG_URL=… pytest -v tests/lifecycle`: **14 passed** with the application database on PostgreSQL 16 (the same suite passes on SQLite, where the PostgreSQL migration test is skipped). Log: `contracts/evidence/T014/pytest_lifecycle_pg.log`.
- Alembic on PostgreSQL (`tests/lifecycle/test_migrations_pg.py`): upgrade head → downgrade 0002 (the five T014 tables gone) → upgrade head → downgrade base (no tables left). On SQLite, `tests/test_migrations.py` checks upgrade/downgrade and that the migrated schema matches the models.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 301 passed on Python 3.11 and 3.12 (ruff clean), frontend 33 unit and 5 end-to-end tests, typecheck/lint/build clean, schema drift OK. Log: `contracts/evidence/T014/ci_local.log`.

### Acceptance criteria

1. S12: recording the simulator's REPLACEMENT through `POST /api/maintenance-events` retires `M01-BS1-LC1` at the event time and starts `M01-BS1-LC2` with `predecessor_lifecycle_id = M01-BS1-LC1`; the lifecycle list equals the simulator's topology (ids, dates, statuses, predecessor) and the event's lifecycle ids equal the simulator's event. Earlier events stay on LC1, aging before the replacement reports LC1, after it LC2. Usage from T013's derived RUNNING time is within 5 % of the simulator's accumulated hours for each lifecycle, and the same period cannot be counted twice. Tests: `test_replacement.py` (4).
2. S09, S10 (lubrication) and S11 (partial repair): the event leaves the single lifecycle ACTIVE with the same id and installation time; accumulated hours and cycles continue from their pre-event values and calendar age keeps counting. Tests: `test_lubrication.py` (3).
3. Workflow: the full path to NORMAL_MONITORING and the REVIEW_REQUIRED path work; every other move (for example MAINTENANCE_EVENT → POST_MAINTENANCE_VALIDATION) returns 409 `workflow_transition_refused` and records nothing; a stale `expected_state` is refused; closing a review needs engineer (403 otherwise) and a comment. Each start, transition and supersession writes an audit row with actor and states, read back through `/api/admin/audit`. Tests: `test_workflow.py` (6).
4. See the Alembic result above.

Decision recorded: D-014.

### Scope notes

- New: `app/equipment/lifecycle.py`, `app/equipment/maintenance.py`, `app/api/equipment.py`, Alembic `0003_equipment_and_maintenance`, contracts in `app/equipment/schemas.py` (`ComponentLifecycle.usage_counted_until`, `LifecycleInstall`, `UsageRecord`, `ComponentAging`, `MaintenanceEventCreate`, `MaintenanceWorkflow`, `WorkflowTransition`, `WorkflowTransitionRequest`, `MaintenanceRecordResult`), error mappings, OpenAPI and TS types.
- Outside the literal scope: `app/simulation/writer.py` leaves the new `usage_counted_until` field out of generated lifecycles so the stored simulated datasets and their checksums stay unchanged.

### Risks

- Workflow steps after MAINTENANCE_EVENT are moved by people; the automatic stabilization and validation checks arrive in T018.
- Maintenance events have a single time, not a duration; MAINTENANCE operating state (T013) needs the interval from another record.
- Accumulated cycles are only meaningful for actuators (counted operations). Motion components sampled every 2 s cannot be counted reliably.
- Real topology and maintenance records have not been seen yet; importing them is part of real-data verification.
