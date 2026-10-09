# TASK-016 — Healthy/adaptive baselines and degradation monitoring

- **ID:** T016
- **Status:** DONE
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Implement the three independent baselines and degradation tracking.

## Dependencies

T015, T014

## Allowed Scope

- backend/app/monitoring/baselines, degradation

Anything outside this list requires Principal Agent approval.

## Related Requirements

L4-05, L4-06, L4-07, OPT-05

## Acceptance Criteria

1. Verified healthy reference only changes through an explicit, audited verification action.
2. Adaptive baseline tracks regime-normalized behavior; normal aging (S03) is visible against the frozen reference.
3. Degradation history persists across maintenance and lifecycle boundaries correctly.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/baselines (S01, S03, S04, S09–S12)`

## Deliverables

- Baseline and degradation modules

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

Executed 2026-10-09 by the executing agent. All data is simulated; nothing was run on real equipment.

### Commands and results

- `pytest -v tests/baselines` (S01, S03, S04, S09, S10, S11, S12): **14 passed**. Log: `contracts/evidence/T016/pytest_baselines.log`.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 336 passed on Python 3.11 and 3.12 (ruff clean; baseline tables on PostgreSQL 16), frontend 33 unit and 5 end-to-end tests, schema drift OK. Log: `contracts/evidence/T016/ci_local.log`.

### Acceptance criteria

1. A verified healthy reference is created only by `BaselineService.verify` (`POST /api/baselines/verified`): engineer role (403 for maintenance), a non-empty comment (422 otherwise), at least 5 stored feature windows of that lifecycle in the period. Statistics are frozen; the action writes an audit row `baseline.verify` with period, lifecycle, feature version, comment and superseded id. Saving an adaptive snapshot, or storing more feature vectors, leaves the reference identical; `save_snapshot` refuses a VERIFIED_HEALTHY baseline. Re-verifying supersedes the previous reference and keeps both. Tests: `test_verified.py` (5).
2. The adaptive baseline is an exponentially weighted mean and spread (alpha 0.1) of a feature, restarted at each lifecycle start. S03 (normal aging): against the reference verified for 96–500 h, the adaptive cruise-torque residual sits within ±2 at first and above 3 reference spreads at the end, while recent values stay close to the adaptive mean; the cylinder extension median shows the same. Tests: `test_adaptive.py` (3).
3. Degradation history keeps all windows of all lifecycles. S09/S10 (lubrication) and S11 (partial repair) keep one continuous segment and report the step across the event: S09 improvement (change < −1), S10 deterioration (> +1), S11 extension median down. S12 (replacement) has two segments; LC2 has no deviations until its own reference is verified, never borrowing LC1's; LC1's history is unchanged afterwards; S04 deviation rises above 10. Also checked through `GET /api/components/{id}/degradation`. Tests: `test_degradation.py` (6).

Decision recorded: D-017.

### Scope notes

- New: `app/monitoring/baselines/` (`stats.py`, `adaptive.py`, `verified.py`), `app/monitoring/degradation/history.py`, Alembic `0005_baselines`. Contracts: `Baseline.comment`, `superseded_by`, `regime_stats`; new `BaselineVerification`, `AdaptivePoint`, `DegradationPoint`, `DegradationSegment`, `MaintenanceStep`, `DegradationHistory`. OpenAPI and TS types regenerated.
- Outside the literal scope (Principal Agent clarification): `app/api/baselines.py` (three endpoints), error mappings in `app/api/errors.py`, router in `app/main.py`, model imports in `alembic/env.py` and test fixtures.

### Risks

- Residual sensitivity differs by regime (robust scale per regime). Deviations therefore use per-regime reference statistics when the verified period has at least 5 windows of that regime. In S12 the low-load regime shows wear only at about 2.7 reference spreads.
- Choosing the healthy period is the engineer's judgment. The system checks data sufficiency, not health.
- The alpha and step-window values were chosen on simulated data.
