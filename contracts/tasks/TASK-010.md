# TASK-010 — Secure read-only SQL query service

- **ID:** T010
- **Status:** DONE
- **Phase:** 3 — Backend and Industrial Domain
- **Gate:** None

## Goal

Provide a template-based, parameterized, bounded, read-only query service.

## Dependencies

T009

## Allowed Scope

- backend/app/datasource/query_service
- template registry (admin-only, audited)
- API endpoints

Anything outside this list requires Principal Agent approval.

## Related Requirements

L1-02, L1-05, L1-06, SEC-02, SEC-03

## Acceptance Criteria

1. Only approved templates execute; parameters bound; identifiers allowlisted.
2. Non-SELECT, multi-statement, and comment-injection attempts rejected (tests).
3. Row, time-range, timeout, and concurrency limits enforced.
4. Template changes are audited; credentials never returned by any API.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/query_service (includes injection cases)`
- security review notes

## Deliverables

- Query service
- Security test suite

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

Executed 2026-10-09 by the executing agent.

### Commands and results

- `PDM_TEST_PG_URL=postgresql+psycopg://pdm@127.0.0.1:5433/pdmtest pytest -v tests/query_service` (PostgreSQL 16.15 local test cluster): **59 passed, 0 skipped, 0 failed**. Log: `contracts/evidence/T010/pytest_query_service.log`.
  - `test_sql_guard.py`: 10 accepted templates, 30 rejected (write/DDL keywords, `SET`, `COPY`, multi-statement, `--`/`/* */`/`#` comments, backslashes, dollar quoting, NUL, unterminated literals, row locking, dangerous functions, tables outside the allowlist including comma joins and table functions, missing LIMIT, undeclared/unused placeholders).
  - `test_api.py`: roles, admin-only SQL text, bound execution, parameter validation, truncation, range limits, 429 busy, PG 504 statement timeout, sanitized DB errors, versioning and audit, no credentials in any response, secrets resolved server-side.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 191 passed on Python 3.11 and 3.12 (ruff clean), frontend 29 unit and 5 end-to-end tests passed, typecheck/lint/build clean, schema drift check OK. Log: `contracts/evidence/T010/ci_local.log`.
- `tests/test_migrations.py::test_migrations_match_models`: Alembic `0001_audit_and_query_templates` produces exactly the ORM tables (no autogenerate diff).

### Acceptance criteria

1. Only approved templates execute; parameters bound; identifiers allowlisted: `QueryService.run` loads ACTIVE templates from the registry only; values go through `bind()` as SQLAlchemy bind parameters; IDENTIFIER parameters must be a discovered device/key; tables must be discovered tables. Tests: `test_run_returns_bound_rows_in_order`, `test_string_parameters_are_bound_not_spliced`, `test_bad_parameters_are_rejected_before_execution`, guard `table not allowed` cases.
2. Non-SELECT, multi-statement, comment injection rejected: 30 guard rejection cases; `test_unsafe_template_is_rejected_and_not_stored` shows the API refuses them with 422 and stores nothing.
3. Row, time-range, timeout, concurrency limits: `test_row_limit_truncates_and_says_so`, `limit_exceeded` range case, `test_statement_timeout_returns_504_on_postgres`, `test_concurrency_limit_returns_busy`.
4. Template changes audited; credentials never returned: `test_changes_are_versioned_and_audited`, `test_no_endpoint_returns_credentials`, `test_database_errors_are_not_echoed`, `test_sources_file_resolves_secrets_server_side`.

Security review notes: `contracts/evidence/T010/security-review.md` (self-review; residual risks listed there, an independent review is recommended before G4).

### Scope notes

Outside the literal Allowed Scope, needed to deliver it and kept minimal:
- `app/core/security.py` (role check, dev header provider per D-010), `app/core/audit.py` (audit table), `app/core/db.py`/`config.py` (session dependency, `auth_mode`, `datasources_file`).
- `app/datasource/sql.py`: `_connect`/`_to_db`/`_from_db` made public (`connection`, `to_db_time`, `from_db_time`) so the query service shares the adapter's read-only engine, concurrency slots and time-zone handling. No behavior change; T009 tests pass unchanged apart from the rename.
- `app/api/errors.py`, `app/main.py` wiring, Alembic env and migration, `tests/__init__.py`, contract registry and regenerated OpenAPI/TypeScript types.

### Risks

- Dev authentication (D-010) is not safe on a shared network until T028.
- The guard is pattern-based; the read-only database session is the backstop.
- Verified only against the IoTSharp-like test layout; the real IoT database schema is still unverified (needed before G2).
