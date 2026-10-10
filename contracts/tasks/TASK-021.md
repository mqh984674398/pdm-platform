# TASK-021 — Component-specific model routing

- **ID:** T021
- **Status:** DONE
- **Phase:** 5 — Predictive Models
- **Gate:** None

## Goal

Implement operator specs, component analysis templates, and routing with eligibility, timeout, and fallback.

## Dependencies

T015, T017

## Allowed Scope

- backend/app/prediction/routing, templates

Anything outside this list requires Principal Agent approval.

## Related Requirements

L5-01, L5-02, L6-01, GEN-07

## Acceptance Criteria

1. Each operator declares all L5-02 fields; registry rejects incomplete specs.
2. Routing per component type; ineligible inputs yield UnsupportedPrediction.
3. Timeouts trigger declared fallback.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/routing`

## Deliverables

- Routing engine and templates

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

- **Date:** 2026-10-09. Decision D-023. `pytest tests/routing -v`: 18 passed (`contracts/evidence/T021/pytest_routing.log`). Full `tools/ci_local.sh`: backend 423 passed on 3.11 and 3.12 (PostgreSQL), schema drift OK, vitest 41, Playwright 12 (`contracts/evidence/T021/ci_local.log`).
- **AC1:** built-in specs carry every L5-02 field; the registry rejects missing version, uncovered signals, unknown or foreign feature schema, unknown eligibility codes, empty eligibility (schema) and duplicates. **AC2:** routing per component type on SIMULATED S04 windows gives a typed degradation indicator and anomaly score; cam is COMPONENT_TEMPLATE_ONLY; missing reference, missing or sparse sampling and a mismatched feature version give UnsupportedPrediction with the reason. **AC3:** a 0.1 s timeout returns TIMEOUT, or falls back to the statistical operator or the previous version as declared; a crashing model gives MODEL_UNAVAILABLE.
