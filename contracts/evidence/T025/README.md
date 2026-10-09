# T025 evidence: historical replay and rapid parameter optimization

All data is simulated.

- Replay: `backend/app/optimization/replay.py`. Windows are processed in time order. A truncated replay (`until`) gives the same decisions as the full replay up to the cut, which is checked at 30/60/90 % on three components. It also matches the live `FleetHealthService.window_decisions`.
- Candidates: `candidates.py`. Path A changes persistence, hold, CUSUM k/h and a scale on the STATISTICAL thresholds. Path B changes aging-grading parameters. `check_safety` refuses any change to a SAFETY rule, including removing one.
- Evaluation: `service.py` scores every window against the Golden Case regression suite, counting windows within, over and under the allowed levels. A challenger is recommended only if it has more windows within and no more under. Nothing is promoted; promotion with approval and rollback is T026. Every run is audited (`optimization.run`).
- API: `POST /api/optimization/runs` (engineer) and `GET /api/optimization/runs/latest` (viewer). Without a suite the run is refused with `no_regression_suite`.
- UI: `/optimization` (OptimizationView) shows the champion and candidates, the recommendation, and per-case counts for a selected candidate.
- Full-fleet run (`optimization_run.json`, from `backend/scripts/optimization_run.py`, seed 0, 12 candidates, about 19 s):
  - Champion: 1199/1310 within, 96 over, 15 under. This equals the T024 fused Golden match.
  - Recommended A05 (`cusum_h` 16, thresholds × 0.9): 1205/1310 within, 95 over, 10 under.
  - It is a recommendation on simulated data only and has not been applied.
- Tests: `pytest tests/replay` (9 passed); unit `tests/unit/optimization.spec.ts`; E2E `tests/e2e/optimization.spec.ts`.
- CI (`ci_local.log`): backend 475 passed on Python 3.11 and 3.12, schema drift OK, frontend 42 unit and 13 E2E passed.
