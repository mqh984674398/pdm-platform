# TASK-020 — Full-stack component health dashboard

- **ID:** T020
- **Status:** DONE
- **Phase:** 4 — Statistical Monitoring
- **Gate:** G3 (approval requested after this task)

## Goal

Connect overview, component map, charts, alarms, and maintenance views to live backend results on simulated data.

## Dependencies

T007, T017, T018, T019

## Allowed Scope

- frontend views switched to real APIs
- backend aggregation endpoints

Anything outside this list requires Principal Agent approval.

## Related Requirements

UI-01, UI-02, UI-03, UI-08, UI-09, L6-04

## Acceptance Criteria

1. End-to-end flow: simulated adapter → features → monitoring → alarms → UI.
2. Alarm review and feedback recorded.
3. All G3 scenarios demonstrable in UI with simulated badge.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest API integration`
- Playwright E2E

## Deliverables

- Full-stack dashboard
- G3 demonstration package (bilingual)

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

- **Date:** 2026-10-09. Decision record D-021. Full log: `contracts/evidence/T020/ci_local.log` (`tools/ci_local.sh`: Python 3.11 and 3.12 with PostgreSQL 16 tests, schema drift, frontend unit and E2E).
- **Backend:** 405 passed on 3.11 and 3.12. New `tests/fleet/test_fleet.py` (8, API integration on PostgreSQL): four demo machines replayed through `app/simulation/demo_pipeline.py`; `/api/fleet` computed and marked simulated (A02-BS1 CRITICAL by ST-TORQUE, A02-LM1 NORMAL); A05 replacement judged against LC2's own reference; A05 workflow NORMAL_MONITORING and A10 REVIEW_REQUIRED; `/api/components/{id}/health` evidence trail (rule hits, reference verified by `demo-engineer (SIMULATED)`, alarms, DETERIORATED impact); alarm acknowledge and resolve audited; references verified only by the labeled demo account; stale or unreferenced components UNKNOWN; viewer required.
- **Frontend:** vitest 41 passed (new `alarms.spec.ts`; `fleet.spec.ts` now reads the fleet API). Playwright 12 passed; new `tests/e2e/health.spec.ts` against the demo server: 11 machines with simulated badge and scenario source, component evidence trail, A10 review state and DETERIORATED evidence, alarm acknowledged and resolved with the outcome stored as `ui-engineer`.
- **AC1:** met (pipeline above, demo server runs it at start, about 7 s for 11 machines). **AC2:** met (alarm review audited; `alarms.spec.ts`, E2E, `test_alarm_review_is_recorded`). **AC3:** met for every G3 checklist item with screenshots in `contracts/evidence/G3/`; the comparison with the Golden Cases (1048/1310 windows within the allowed levels, deviations listed in the G3 README) is reported, not tuned away.
- **Found and fixed:** CUSUM-triggered hits reported the WATCH threshold (4) instead of `cusum_h` (12), and held levels read as if the value exceeded the threshold; hits now carry `basis`. The rule engine recomputed its statistics over the whole series per window (O(n²)); now incremental with identical values (`/api/fleet` from about 2 s to about 0.3 s).
- **Outside listed scope (D-021):** demo pipeline module, rule engine and `RuleHit.basis`, demo server seeding, Studio E2E expectations relative to the seeded configuration version.
