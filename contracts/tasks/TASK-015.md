# TASK-015 — Feature extraction and feature versioning

- **ID:** T015
- **Status:** DONE
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Extract per-window/per-cycle features with declared, versioned feature schemas.

## Dependencies

T013, T014

## Allowed Scope

- backend/app/monitoring/features
- feature store tables

Anything outside this list requires Principal Agent approval.

## Related Requirements

L4-03, L4-04, GEN-06

## Acceptance Criteria

1. Feature sets per component type with versioned schemas.
2. Condition-normalized residuals for torque vs speed/regime.
3. Features carry regime, lifecycle, and source window references; no future data used.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/features (includes leakage test)`

## Deliverables

- Feature module and store

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

Executed 2026-10-09 by the executing agent. All data is simulated (scenarios S01–S20); nothing was run on real equipment.

### Commands and results

- `pytest -v tests/features`: **21 passed** (includes the leakage tests). Log: `contracts/evidence/T015/pytest_features.log`.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 322 passed on Python 3.11 and 3.12 (ruff clean; the feature store tests ran on PostgreSQL 16), frontend 33 unit and 5 end-to-end tests, schema drift OK. Log: `contracts/evidence/T015/ci_local.log`.

### Acceptance criteria

1. Feature sets `ball_screw@1.0.0`, `linear_motor@1.0.0`, `pneumatic_cylinder@1.0.0`, `vacuum_cup@1.0.0` are declared in `app/monitoring/features/definitions.py` with bilingual descriptions and units; cam and gear (template only) have none and are reported as `not_supported`. The store registers each version once and refuses a changed definition under a published ref; every stored vector must carry exactly its schema's features. Tests: `test_definitions.py` (3), `test_store.py` (4).
2. Residuals: cruise torque and actuator duration medians are normalized against the matched regime's reference level (robust units). S02 (recipe changes): raw cruise torque differs by more than 1.3× between regimes while the residual median stays within ±3. S04 (torque drift): residual near 0 at the start, above 10 at the end. Windows without a known regime get no residual. Tests: `test_residuals.py` (4).
3. Each vector names its component, lifecycle, regime (status and id), regime catalog, source signals, feature ref and source window. S12: vectors switch from `M01-BS1-LC1` to `LC2` at the replacement; a window spanning a lifecycle change and windows overlapping maintenance get no vector and are listed as skipped. No future data: rows after `as_of` are dropped first, windows still open at `as_of` are not emitted, and the regime catalog must be learned before the extraction window. Replacing every row after the cut with 10^6, or not loading them, leaves all vectors identical. Tests: `test_leakage.py` (6), `test_references.py` (4).

Decision recorded: D-016.

### Scope notes

- New: `app/monitoring/features/` (`definitions.py`, `extract.py`, `store.py`), Alembic `0004_feature_store` (tables `feature_schemas`, `feature_vectors`), contracts `FeatureDef.residual`, `FeatureSchema.component_type`, extended `FeatureVector`, new `FeatureSkip`, `FeatureExtraction`; OpenAPI and TS types regenerated.
- Outside the literal scope: one import line each in `alembic/env.py` and `tests/test_migrations.py` so the new tables are part of the migrated schema check.
- No API endpoint yet; T016 baselines read the store directly.

### Risks

- Residuals need a known regime, which needs a speed signal. Machines with actuators only (S07) get raw durations without residuals.
- The regime reference must cover every recipe in use: with 72 h instead of 96 h of reference, about half of S01's later windows were UNSUPPORTED.
- Feature thresholds (minimum 3 completed operations per window) were chosen on simulated data.
