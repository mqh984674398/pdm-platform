# TASK-002 — Frontend/backend skeleton and test infrastructure

- **ID:** T002
- **Status:** IN_PROGRESS
- **Phase:** 1 — Contracts and Simulation
- **Gate:** None

## Goal

Create runnable backend and frontend skeletons with test, lint, and type-check tooling and CI.

## Dependencies

T001

## Allowed Scope

- backend/ (FastAPI app factory, settings, health endpoint, layer packages per ARCHITECTURE §3, Alembic init, pytest)
- frontend/ (Vite + Vue 3 + TS + Router, Vitest, vue-tsc, Playwright config, ESLint/Prettier)
- CI workflow running backend and frontend checks
- Developer README sections

Anything outside this list requires Principal Agent approval.

## Related Requirements

STK-01, STK-02, STK-06, TST-01

## Acceptance Criteria

1. `GET /api/health` returns 200 with version and `llm_required: false`.
2. Backend layer packages exist with an import-direction test enforcing the dependency rule.
3. Frontend app builds and renders a shell route.
4. pytest, vitest, vue-tsc, lint all run green locally and in CI.
5. Works on Python 3.11 and 3.12 (CI matrix).

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `cd backend && pytest`
- `cd frontend && npm run test && npm run typecheck && npm run build`
- CI run link

## Deliverables

- backend/ skeleton
- frontend/ skeleton
- .github/workflows/ci.yml

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
