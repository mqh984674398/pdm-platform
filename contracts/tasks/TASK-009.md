# TASK-009 — Time-series database adapter

- **ID:** T009
- **Status:** DONE
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

2026-10-09:

- `tools/ci_local.sh` with `PDM_TEST_PG_URL` pointing at a throwaway local PostgreSQL 16.15 cluster → exit 0 (log `contracts/evidence/T009/ci_local.log`): backend 131 passed on Python 3.11 and 3.12; frontend unchanged and green.
- `pytest tests/datasource -rA` → 60 passed, 0 skipped (log `contracts/evidence/T009/pytest_datasource.log`). Without `PDM_TEST_PG_URL` the PostgreSQL cases skip and the rest run on SQLite. GitHub CI now starts a `postgres:16` service and sets the variable.
- AC1: `TimeSeriesAdapter` has `discover`, `inspect_schema`, `query_range`, `query_incremental` (`app/datasource/adapter.py`).
- AC2: `SqlAdapter` (`app/datasource/sql.py`) verified against SQLite and PostgreSQL databases seeded from the raw rows of S13 (missing and duplicate rows) and S14 (jitter and out-of-order rows).
- AC3: table, schema, column names, value columns and time zone of naive timestamps come from `SqlTableLayout` and are reflected and checked on start-up (`LayoutError`). The two test layouts use different names (IoTSharp-style naive `datetime` in SQLite; `iot.raw_telemetry` with `timestamptz` in PostgreSQL). Documented in `backend/app/datasource/README.md`. `verified` defaults to false: the real IoT database is still unverified (L1-08).
- AC4: `tests/datasource/test_adapter_contract.py` runs the same 8 checks on the simulated, SQLite and PostgreSQL adapters (48 cases).
- Read-only (L1-02): PostgreSQL sessions start with `default_transaction_read_only=on` and `statement_timeout`; a DELETE fails with a read-only error and `pg_sleep(3)` is cancelled at a 1 s timeout. SQLite uses `PRAGMA query_only`. Unverified engines are refused.
- Bounds (L1-06): row limit, maximum time range, statement timeout, concurrency limit, each with a test.
- Contract additions: `ColumnInfo`, `TableInfo`, `SourceSchema`, `SqlTableLayout` (openapi.json and frontend types regenerated; drift check green). `app/api/contracts.py` gained the four names (registry only).
- Known limitation: watermark reads use `ts > since`, so rows sharing the boundary timestamp at a batch edge are skipped; documented for the ingestion task.
