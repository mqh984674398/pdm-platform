# TASK-008 — SQL Data Source Studio frontend Demo

- **ID:** T008
- **Status:** DONE
- **Phase:** 2 — High-Fidelity Frontend
- **Gate:** G1 (approval requested after this task)

## Goal

Deliver a guided Data Source Studio demo (mocked backend) covering the full configuration workflow.

## Dependencies

T003, T005, T006

## Allowed Scope

- frontend views for Data Source Studio and signal preview
- Mocked endpoints matching T003 schemas

Anything outside this list requires Principal Agent approval.

## Related Requirements

UI-04, UI-05, L1-05, L2-01, L2-02, L2-03, L2-04, L2-05

## Acceptance Criteria

1. Guided steps: connection, schema inspection, device/signal selection, template choice, field mapping, units, grouping, preview, sampling/quality, component association, viz template, version save.
2. Ordinary user completes the workflow without writing SQL; template SQL is view-only for non-admins.
3. Preview chart uses simulated data and shows quality summary.
4. Configuration version history visible.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- vitest
- Playwright E2E of the full workflow
- screenshots zh/en

## Deliverables

- Studio demo
- G1 demonstration package (bilingual)

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

2026-10-09:

- `tools/ci_local.sh` → exit 0 (log `contracts/evidence/T008/ci_local.log`): backend 71 passed on 3.11/3.12 (new `tests/test_studio_fixture.py`, 4 tests), Vitest 29 passed (new `studio.spec.ts`, 12 tests), vue-tsc/eslint/prettier clean, build OK, Playwright 5 passed (new `studio.spec.ts`, 2 tests: full 12-step workflow as operator; SQL visible only as administrator).
- Mock backend: `frontend/src/api/studio.ts` (`createMockStudioApi`) returns generated contract types (DataSourceConfig, SourceMetadata, QueryTemplate, SignalMapping, SignalConfigVersion). Data: `Data/fixtures/studio_demo.json` from `backend/app/simulation/studio_fixture.py` (scenarios S01, S13, S14, S16; `test_fixture_matches_generator`). No credentials: the source carries a `secret://` reference only; template SQL is SELECT-only with a LIMIT and parameters that match the template (`test_no_credentials_and_read_only_sql`).
- AC1: the 12 steps in contract order with a step rail grouped into five phases; Next is disabled with a one-line hint until a step is complete. Screenshots `studio-01-connection-zh.png` through `studio-12-version-zh.png`, English set `studio-*-en.png`.
- AC2: the operator path needs no SQL (E2E asserts the SQL block is absent and the locked notice shown); administrators see the query text (`studio-04-template-en-admin.png`). Production connections are shown as locked pending administrator approval (contract: explicit approval before any production connection).
- AC3: ECharts preview of converted values per observation window, simulated badge, flagged rows marked (`studio-08-preview-*.png`). Quality summary follows the DataQualityReport contract (`frontend/src/studio/quality.ts`): S13 shows missing samples and duplicates, S14 jitter and out-of-order rows, S16 a possible unit change, S01 clean (`studio-09-quality-*.png`; unit test `finds the faults built into the simulated scenarios`). Flagged rows are kept and marked, never deleted.
- AC4: version history with saved-by, time, note and SHA-256 content hash; saving appends an immutable version (`studio-12-version-*.png`; unit test `appends immutable versions with a content hash`). Versions 1 and 2 are labeled simulated history.
- Dependencies added: echarts 5, pinia 3 (both in the contract stack).
- Scope note: the quality summary is a demo implementation in the mock layer; the L2 quality service (T010) replaces it behind the same contract.
- G1 package: `contracts/evidence/G1/`.
- Tools used: Playwright (E2E, screenshots), frontend-design skill guidance from T006.
