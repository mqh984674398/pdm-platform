# TASK-003 — Domain, signal, API, and result schemas

- **ID:** T003
- **Status:** TODO
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

_Filled in by the executing agent with actual commands and results._
