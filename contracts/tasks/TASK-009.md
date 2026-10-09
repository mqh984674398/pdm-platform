# TASK-009 — Time-series database adapter

- **ID:** T009
- **Status:** TODO
- **Phase:** 3 — Backend and Industrial Domain
- **Gate:** None

## Goal

Implement the adapter abstraction and the SQL time-series adapter with metadata discovery.

## Dependencies

T003

## Allowed Scope

- backend/app/datasource (adapter interface, SQL adapter, simulated adapter wiring)
- Test DB via container or SQLite-compatible fixture

Anything outside this list requires Principal Agent approval.

## Related Requirements

L1-01, L1-03, L1-04, L1-07, L1-08

## Acceptance Criteria

1. Common interface for historical range, incremental since-watermark, and metadata discovery.
2. SQL adapter verified against a test database seeded from simulated raw rows.
3. Engine/schema/field assumptions are configurable and documented, not hard-coded to the example query.
4. Simulated and SQL adapters pass the same contract test suite.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/datasource`

## Deliverables

- Adapters
- Adapter contract tests

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
