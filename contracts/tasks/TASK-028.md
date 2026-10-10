# TASK-028 — Windows/LAN deployment and final acceptance

- **ID:** T028
- **Status:** DONE
- **Phase:** 7 — Release
- **Gate:** G4 (approval requested after this task)

## Goal

Package for Windows server LAN deployment, complete security review, and run final acceptance.

## Dependencies

T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027

## Allowed Scope

- deploy/
- security review
- acceptance evidence

Anything outside this list requires Principal Agent approval.

## Related Requirements

STK-05, SEC-01, SEC-03, SEC-04, SEC-06, TST-01

## Acceptance Criteria

1. Services install and start on Windows; browser clients on LAN need no install.
2. Security review completed with findings resolved or accepted.
3. End-to-end acceptance evidence for all G4 items.
4. Production data connection and official alerting remain disabled until explicit user approval.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- Deployment log
- full test suite
- security review report

## Deliverables

- Deployment package
- G4 acceptance package (bilingual)

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

Commands actually run on 2026-10-10 (Linux build/test container; no Windows host available).

- Full CI: `tools/ci_local.sh` → backend 532 passed, 1 skipped (live Ollama, opt-in) on Python 3.11 and 3.12; ruff clean; frontend unit 44 passed; Playwright E2E 15 passed. Log: `contracts/evidence/T028/ci_local.log`.
- New tests: `backend/tests/auth/test_auth.py` (12), LLM settings admin checks in `tests/llm/test_llm.py`, `frontend/tests/unit/session.spec.ts` (2).
- Package: `backend/.venv/bin/python deploy/build_package.py` → `dist/pdm-0.1.0-windows.zip` (4.4 MB), `backend/requirements.lock` (35 runtime packages).
- Windows wheels: `pip download -r backend/requirements.lock --only-binary=:all: --platform win_amd64 --python-version 3.12` → all resolved (36 files, 114 MB). List: `windows_wheels_cp312.txt`.
- Deployment log: `deploy/smoke_test.py` unpacked the zip and ran it in production mode (local sign-in, PostgreSQL, static client, SIMULATED fleet, a production source configured but not approved) → 26 checks passed, 0 failed. `contracts/evidence/T028/deployment_log.txt`.
- Security review: `contracts/evidence/T028/security_review.md` (15 findings: 11 resolved, 4 accepted residual risks for G4, none open).
- Screenshots of the production-mode package: `contracts/evidence/G4/*.png`.

Not done here: `deploy/windows/install.ps1` was **not executed** on Windows (criterion 1 is verified only up to the Linux production-mode run); live Ollama was not available.
