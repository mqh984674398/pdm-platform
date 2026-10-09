# TASK-019 — Advanced interactive time-series charting

- **ID:** T019
- **Status:** TODO
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Build high-performance time-series charts with baseline overlays, events, and maintenance timeline.

## Dependencies

T006, T011, T016

## Allowed Scope

- frontend/src/charts
- time-series dashboard, baseline comparison, maintenance timeline views
- downsampling API usage

Anything outside this list requires Principal Agent approval.

## Related Requirements

UI-06, UI-07, UI-08, L2-06

## Acceptance Criteria

1. Smooth interaction on ≥1M points via server-side downsampling and dataZoom.
2. Healthy reference vs adaptive baseline overlay; maintenance and alarm markers.
3. Downsampled indicator shown; full-resolution export available.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- vitest
- Playwright E2E and performance measurement

## Deliverables

- Chart components and views

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
