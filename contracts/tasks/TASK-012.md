# TASK-012 — Data quality, unit conversion, and time alignment

- **ID:** T012
- **Status:** DONE
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

Executed 2026-10-09 by the executing agent.

### Commands and results

- `pytest -v tests/quality`: **43 passed** (golden cases, unit checks, API, clean scenarios). Log: `contracts/evidence/T012/pytest_quality.log`.
- `backend/scripts/quality_sweep.py` over all 20 simulated scenarios in 48 h chunks: flags appear only on S13, S14, S15, S16 and S20; the other 15 scenarios report no flags. Log: `contracts/evidence/T012/quality_sweep.log`.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 263 passed on Python 3.11 and 3.12 (ruff clean), frontend 33 unit and 5 end-to-end tests, typecheck/lint/build clean, schema drift OK. Log: `contracts/evidence/T012/ci_local.log`.

### Acceptance criteria

1. Per-signal checks (`app/monitoring/quality/assess.py`) on full-resolution rows: missing (absent samples per observation window above 2 %, plus null values), duplicate timestamps, out-of-order delivery (from storage order, `arrival_seq`), jitter (robust interval spread above 5 % of the expected interval), gaps (pauses longer than 4x the typical pause, 6x for event-based signals, at least 1 h), median sampling interval, out-of-range and unit plausibility. Each finding carries flagged time spans. Golden-case spans for S13 (missing, duplicate), S14 (jitter, out-of-order), S16 and S20 (gaps) are asserted in `test_golden_cases.py`. Checks a signal cannot support are listed in `not_evaluated`, never reported as clean.
2. S16: the unit mismatch window is reported as UNIT_SUSPECT and OUT_OF_RANGE, and the torque bias as BIAS_SUSPECT (standstill torque compared with the 168 h reference period). The test confirms the source values stay unchanged (still x1000); nothing is corrected.
3. Speed/torque alignment (`app/monitoring/alignment/pairs.py`): nearest-timestamp pairing within a tolerance that is returned in the report (default half the expected interval), paired/unpaired counts, median offset, per-window agreement with `min_agreement` 0.8. S15 windows are flagged MISALIGNED with their spans; clean scenarios (S01, S04, S17, S19) stay aligned.
4. `POST /api/quality/report` reads every row through the bounded read-only adapters (200k rows per signal, 168 h window) and never uses the visualization series; `test_quality_api.py` checks that counts match the full-resolution rows, not the downsampled chart.

The Studio quality step now calls the backend report (speed/torque findings shown on the torque row), so the S14 out-of-order risk from T011 is closed. Decision recorded: D-012 (thresholds, observation windows, reference period).

### Scope notes

Outside the literal Allowed Scope, needed for AC1 (out-of-order needs storage order) and kept minimal:
- `RawTelemetryRow.arrival_seq` and `SqlTableLayout.arrival_column` (optional; when absent, OUT_OF_ORDER is reported as not evaluated). The simulated adapter uses file line order.
- `QualityFlag.BIAS_SUSPECT` added to the signal schemas.
- Studio frontend: `studioHttp.quality()`, store and StepQuality use the backend report.

### Risks

- Thresholds are tuned on simulated data only. They must be reviewed on the real IoT schema and data, which is still unverified (needed at G2).
- Bias detection needs at least 3 motion windows in the reference period; in shorter windows it is reported as not evaluated (the S16 bias is found in its golden window but not in every 48 h sweep chunk).
- Real SQL sources expose out-of-order only when an arrival/ingest column is configured.
