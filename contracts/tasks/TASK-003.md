# TASK-003 — Domain, signal, API, and result schemas

- **ID:** T003
- **Status:** DONE
- **Phase:** 1 — Contracts and Simulation
- **Gate:** None

## Goal

Define the core Pydantic domain contracts and API schemas listed in ARCHITECTURE §5, plus generated TypeScript types.

## Dependencies

T002

## Allowed Scope

- backend/app/*/schemas.py
- OpenAPI export script
- frontend/src/api/types (generated)
- Schema docs in contracts/

Anything outside this list requires Principal Agent approval.

## Related Requirements

L2-01, L2-02, L2-05, L3-02, L3-03, L3-05, L3-06, L3-07, L4-05, L5-02, L5-06, L6-04, GEN-06, GEN-07

## Acceptance Criteria

1. All enums match REQUIREMENTS exactly (OperatingState, HealthState, MaintenanceWorkflowState, Baseline kinds).
2. PredictionResult is a discriminated union; anomaly score, class probability, degradation indicator, failure probability are distinct types.
3. UnsupportedPrediction exists and is a valid result everywhere a prediction is.
4. Every result schema carries model_version, feature_version, config_version, computed_at, data_window, is_simulated.
5. OperatorSpec declares all fields required by L5-02.
6. TypeScript types are generated from OpenAPI and a CI check fails on drift.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/schemas`
- type generation drift check
- vue-tsc

## Deliverables

- Schema modules
- openapi.json
- Generated TS types

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

2026-10-09:

- `tools/ci_local.sh` → exit 0 (log `contracts/evidence/T003/ci_local.log`): pytest 25 passed on Python 3.11 and 3.12; schema drift check OK; Vitest 4 passed; vue-tsc clean; build OK; Playwright 1 passed.
- AC1: `test_enum_values_match_requirements` parses REQUIREMENTS.md L3-02, L6-04, L3-07 and compares enum values in order; baseline kinds tested.
- AC2: `PredictionResult` discriminated union on `kind`; `test_kinds_are_not_interchangeable`, `test_union_members_cover_every_output_kind_plus_unsupported`; frontend `contracts.spec.ts` exhaustive switch type-checks.
- AC3: `test_union_accepts_unsupported_prediction`.
- AC4: `test_every_result_schema_carries_result_meta`, `test_simulated_flag_is_required_wherever_data_is_carried`.
- AC5: `test_operator_spec_declares_all_l5_02_fields`.
- AC6: `tools/check_schema_drift.sh` passes; negative test (renamed a field without regenerating) → exit 1. Wired into `ci.yml` and `tools/ci_local.sh`.
- Schema docs: `contracts/schemas/README.md`; generated `contracts/schemas/openapi.json` (67 component schemas).
