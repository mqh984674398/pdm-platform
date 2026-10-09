# TASK-017 — Statistical rules and alarm-event engine

- **ID:** T017
- **Status:** DONE
- **Phase:** 4 — Statistical Monitoring
- **Gate:** None

## Goal

Implement EWMA, CUSUM, change detection, deterministic rules, hysteresis, and alarm events.

## Dependencies

T016

## Allowed Scope

- backend/app/monitoring/rules, alarms
- alarm APIs

Anything outside this list requires Principal Agent approval.

## Related Requirements

L4-07, L6-03, UI-09

## Acceptance Criteria

1. Detects S04–S08 and S19 with expected responses from golden cases; no alarms on S01.
2. Safety rules are deterministic, versioned, and cannot be disabled by non-admins.
3. Alarm lifecycle (raised, acknowledged, resolved) with audit.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/rules (golden cases)`

## Deliverables

- Rule and alarm engine

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

Executed 2026-10-09 by the executing agent. All data is simulated; thresholds were set on the simulated scenarios and are not validated on real equipment.

### Commands and results

- `pytest -v tests/rules`: **38 passed** (golden cases of S01–S08 and S19). Log: `contracts/evidence/T017/pytest_rules.log`.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 375 passed on Python 3.11 and 3.12 (ruff clean; rule, alarm and audit tables on PostgreSQL 16), frontend 33 unit and 5 end-to-end tests, schema drift OK. Log: `contracts/evidence/T017/ci_local.log`.

### Acceptance criteria

1. Golden cases. For each scenario, a regime catalog is learned from 0–96 h and a verified reference is created for 96–168 h through the audited verification. Rules are evaluated from 168 h; no level exists before that, which those spans' NORMAL expectations allow. Every evaluated window in every expectation span has an allowed level:
   - S04, S05, S06, S07, S08 and S19 (both shared-chain screws) reach the expected rule at WARNING or above.
   - Their control components stay NORMAL.
   - S01 raises no alarm over 0–336 h.
   - S02 (recipe changes) and S03 (normal aging; NORMAL required until 1440 h) also pass.
   Tests: `test_golden.py` (22).
2. Safety rules:
   - The rule set `pdm-rules@1.0.0` is code-defined and its models are frozen, so thresholds change only with a new version.
   - `SF-INCOMPLETE` (timeouts ≥ 10 % WATCH, ≥ 50 % WARNING) and `SF-TORQUE-LIMIT` (p95 torque ≥ 90 % of the configured limit WARNING, ≥ 100 % CRITICAL) need no reference.
   - Disabling a safety rule returns 403 for engineer and maintenance and needs admin plus a comment. Statistical rules need engineer.
   - Every change is audited and bumps the configuration version (`pdm-rules@1.0.0+N`) carried by evaluations and alarms.
   - Evaluation is deterministic.
   - S18: timeouts give WATCH during 72–168 h (allowed) and NORMAL after 180 h.
   Tests: `test_safety.py` (5), `test_engine.py` (5).
3. Alarm lifecycle:
   - S04 through the API: one `ST-TORQUE` alarm is raised and escalated to CRITICAL. Re-running is idempotent (a watermark per component).
   - Acknowledge needs maintenance (403 for viewer) and is refused twice (409). Resolve needs a comment and is refused after resolution.
   - A rule that stops firing marks the condition cleared. After resolution, a rule that fires again raises a new alarm.
   - Raise, escalate, clear, acknowledge and resolve each write an audit row.
   Tests: `test_alarms.py` (2).

Decision recorded: D-018.

### Scope notes (Principal Agent clarification)

- New:
  - `app/monitoring/rules/` (`statistics.py`, `definitions.py`, `engine.py`, `settings.py`) and `app/monitoring/alarms/service.py`.
  - `app/api/alarms.py` (`GET /api/rules`, `PUT /api/rules/{id}`, `POST /api/alarms/evaluate`, `GET /api/alarms`, `POST /api/alarms/{id}/acknowledge`, `POST /api/alarms/{id}/resolve`).
  - Alembic `0006_rules_and_alarms`.
- Alarm contracts moved from `app/decision/schemas.py` to `app/monitoring/schemas.py`, because layer 4 may not import layer 6. They are re-exported from `app.decision.schemas` under the same names, with fields added (acknowledged_by, resolved_by, resolution_comment, condition_active, last_window_end, rules_version).
- Outside the literal scope:
  - Features: `ball_screw` and `linear_motor` moved to version 1.1.0, adding `speed_ripple` (robust spread of cruise-phase speed). Without it, the S05 ripple fault could not be seen. Version 1.0.0 vectors stay valid under their registered schema.
  - Regimes: a machine without speed signals now gets regimes from operation intervals, as G2 assumption A2 states ("from cruise speeds and the operation interval"). The T013 test that asserted "no regime without speed" was replaced by a test of the A2 behavior on S18, plus a test that speed or interval evidence is required. S06, S07 and S08 now get condition-normalized residuals.

### Risks

- Thresholds (persistence 3 windows, WATCH 4 / WARNING 8 / CRITICAL 25 reference spreads, CUSUM k=2 h=12, hold 3 windows) are tuned on simulated data only.
- `SF-TORQUE-LIMIT` needs a per-component torque limit. None is configured yet, so the API reports it as not evaluated.
- A window the rule cannot evaluate (for example an unsupported regime) keeps the current level instead of clearing it.
- Alarms are review records only. No notification or official maintenance-alerting workflow is enabled, which needs the user's explicit approval.
