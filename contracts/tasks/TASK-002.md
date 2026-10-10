# TASK-002 — Frontend/backend skeleton and test infrastructure

- **ID:** T002
- **Status:** DONE
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

2026-10-09 (Python 3.11.17 and 3.12.3, Node 22.22.0, Playwright 1.56.1 with pre-installed Chromium):

- `tools/ci_local.sh` → exit 0, log `contracts/evidence/T002/ci_local.log`:
  - contracts check OK; ruff check/format clean; `pytest` 5 passed on 3.11 and on 3.12 (1 third-party Starlette deprecation warning).
  - frontend: eslint (0 warnings) and prettier clean; `vue-tsc --build` clean; Vitest 2 files / 3 tests passed; `vite build` OK; Playwright 1 passed.
- AC1: `GET /api/health` → `{"status":"ok","version":"0.1.0","llm_enabled":false,"llm_required":false}` (test_health.py, and live via the frontend preview proxy).
- AC2: `tests/test_layering.py` enforces ARCHITECTURE §3 import direction, including a probe test that the checker detects violations.
- AC3: shell route renders; screenshot with live backend `contracts/evidence/T002/shell-with-backend.png`.
- AC4: CI workflow `.github/workflows/ci.yml` written; it has not run on GitHub yet because no remote exists. Local equivalent used per DECISIONS D-007.
- AC5: Python 3.11 and 3.12 both pass locally; CI matrix covers both.
- Alembic: environment wired to `PDM_DATABASE_URL`; upgrade/downgrade verified on a throwaway SQLite DB (`tests/test_migrations.py`). PostgreSQL migration testing starts with the first real migration (T014).
