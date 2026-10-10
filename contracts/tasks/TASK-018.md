# TASK-018 — Maintenance stabilization and impact analysis

- **ID:** T018
- **Status:** DONE
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Analyze pre/post-maintenance behavior under compatible regimes and drive the workflow outcome.

## Dependencies

T014, T016, T017

## Allowed Scope

- backend/app/equipment/maintenance_impact

Anything outside this list requires Principal Agent approval.

## Related Requirements

L3-07, L3-08, L4-05

## Acceptance Criteria

1. Pre vs post comparison restricted to compatible regimes.
2. S09 yields improvement, S10 deterioration → REVIEW_REQUIRED, S11 partial effect reported.
3. Stabilization window configurable; insufficient data yields UNKNOWN.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/maintenance_impact`

## Deliverables

- Impact analysis module

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

Executed 2026-10-09 by the executing agent. All data is simulated; nothing was run on real equipment.

### Commands and results

- `pytest -v tests/maintenance_impact`: **14 passed**. Log: `contracts/evidence/T018/pytest_maintenance_impact.log`.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 389 passed on Python 3.11 and 3.12 (ruff clean), frontend 33 unit and 5 end-to-end tests, schema drift OK. Log: `contracts/evidence/T018/ci_local.log`.

### Acceptance criteria

1. Only KNOWN-regime windows are compared. A regime counts only when it has at least 3 windows before the event and windows after it. Regime-defining features (speeds, operation intervals) are never reported as effects. On S02, fake "events" at 150, 200 and 250 h, where recipes change but nothing is maintained, give NO_CHANGE or UNKNOWN. Tests: `test_only_compatible_regimes_are_compared`, `test_recipe_change_is_not_a_maintenance_effect`.
2. S09 lubrication gives IMPROVED (cruise torque residual change < −2, post level within ±3). S10 gives DETERIORATED. S11 partial repair gives PARTIAL: the extension median improves by more than 2 robust units but stays at least 3 above the regime reference. Driven by `ImpactService.advance`, the workflows follow the Golden Case paths exactly and finish before each case's next span:
   - S09 and S12: MAINTENANCE_EVENT, STABILIZATION, POST_MAINTENANCE_VALIDATION, NORMAL_MONITORING.
   - S10 and S11: the same path, ending in REVIEW_REQUIRED.
   The system never closes a review. Every analysis is audited (`maintenance_impact.analyze`) and stored. Tests: `test_analysis.py`, `test_workflow.py`.
3. `ImpactConfig` sets pre 72 h, stabilization 4 h, validation 36 h (up to 120 h while data is insufficient), at least 3 pre windows per regime and 3 post windows, effect 2 and elevated 3 robust units. With too little data the outcome is UNKNOWN. The workflow then keeps waiting with a longer comparison period and goes to REVIEW_REQUIRED after the maximum. Tests: `test_insufficient_data_is_unknown`, `test_stabilization_window_is_configurable`, `test_waiting_for_data_then_review`.

Decision recorded: D-019.

### Scope notes

- New: `app/equipment/maintenance_impact/` (`analysis.py`, `service.py`), Alembic `0007_maintenance_impacts`, contracts `ImpactOutcome`, `ImpactConfig`, `RegimeComparison`, `FeatureImpact`, `MaintenanceImpact`. OpenAPI and TS types regenerated.
- The analysis uses T013 regime assignments, which are in the equipment layer, not the T015 feature store. Layer 3 may not import layer 4.
- No API endpoint yet. A scheduler or the T020 dashboard calls `advance` with series loaded through the read-only adapters.

### Risks

- With about 4 observation windows a day, 36 h of validation holds only a few comparable windows. S12 needed the extension (UNKNOWN until enough windows of a compatible regime followed).
- Thresholds were tuned on simulated data. Longer actuator durations and higher torque count as worse, which may not hold for every real signal.
- Maintenance events have no duration (D-014). Stabilization starts at the recorded event time.
