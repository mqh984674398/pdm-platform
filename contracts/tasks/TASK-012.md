# TASK-012 — Data quality, unit conversion, and time alignment

- **ID:** T012
- **Status:** IN_PROGRESS
- **Phase:** 3 — Backend and Industrial Domain
- **Gate:** None

## Goal

Compute data quality metrics, apply unit conversions, and align related signals.

## Dependencies

T011

## Allowed Scope

- backend/app/monitoring/quality, alignment
- quality report API

Anything outside this list requires Principal Agent approval.

## Related Requirements

L4-01, L4-02, L2-02, L2-06

## Acceptance Criteria

1. Detects missing, duplicate, out-of-order, jitter, gaps, sampling interval, unit plausibility on S13–S16 and S20 golden cases.
2. Unit mismatch and bias (S16) flagged, not silently corrected.
3. Speed/torque alignment with reported tolerance; misaligned windows flagged (S15).
4. Full-resolution normalized data preserved separately from visualization data.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/quality (golden cases)`

## Deliverables

- Quality and alignment modules
- Quality report

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
