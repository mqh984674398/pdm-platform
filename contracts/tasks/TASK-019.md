# TASK-019 — Advanced interactive time-series charting

- **ID:** T019
- **Status:** DONE
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

- **Date:** 2026-10-09. Decision record D-020. Full log: `contracts/evidence/T019/ci_local.log` (`tools/ci_local.sh`, Python 3.11 and 3.12, PostgreSQL 16 tests, schema drift, frontend).
- **Backend:** 397 passed on 3.11 and 3.12 (8 new in `tests/timeseries`: server-side min/max downsampling of 1.2M points in under 3 s, spike kept, gaps for missing values, unit conversion, extent, full-resolution CSV export streamed and audited with `_SIMULATED` file name, auth).
- **Frontend unit (vitest):** 39 passed; `tests/unit/charts.spec.ts` covers detail splicing, zoom jitter, alarm periods, maintenance markers and reference bands.
- **E2E (Playwright):** 8 passed. `tests/e2e/charts.spec.ts` runs the analysis view on the demo server's SIMULATED bench signal (1,100,000 points). Measured in this run: first render 1380 ms including page load, wheel zoom to detail loaded 973 ms, overview 1998 points (limits asserted: 5000 ms each). Baseline comparison and maintenance timeline are checked with mocked API data (pipeline output arrives in T020).
- **AC1:** met by the measurements above. **AC2:** reference band, adaptive baseline, maintenance and alarm overlays rendered (unit + E2E). **AC3:** downsample note and CSV export verified in E2E.
- **Found and fixed:** the slider label formatter threw on a non-finite value; now guarded.
- **Outside listed scope (D-020):** `TimeSeriesAdapter.query_arrays`, `app/api/timeseries.py`, `app/simulation/bench.py`, demo server bench seeding, Studio E2E expectations updated for the seeded config version.
