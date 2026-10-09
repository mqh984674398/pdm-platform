# TASK-010 — Secure read-only SQL query service

- **ID:** T010
- **Status:** IN_PROGRESS
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

_Filled in by the executing agent with actual commands and results._
