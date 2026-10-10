# TASK-005 — Golden Cases and scenario fixtures

- **ID:** T005
- **Status:** DONE
- **Phase:** 1 — Contracts and Simulation
- **Gate:** None

## Goal

Produce the 20 required scenarios and the Golden Case suite used for regression and replay.

## Dependencies

T004

## Allowed Scope

- Data/scenarios/, Data/fixtures/, Data/golden_cases/
- Scenario configs and generation script
- Golden-case loader for tests

Anything outside this list requires Principal Agent approval.

## Related Requirements

SIM-03, SIM-04, TST-02, GEN-07

## Acceptance Criteria

1. All 20 scenarios S01–S20 exist with seed, metadata, expected observable behavior, ground truth, expected health response, and required abstention/fallback cases.
2. Raw and normalized representations are provided per scenario.
3. Golden cases include explicit UNKNOWN/abstention expectations (S13–S18, S20).
4. Scenario regeneration is reproducible and verified against stored checksums.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/scenarios`
- checksum verification script

## Deliverables

- 20 scenario packages
- Golden case index

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

2026-10-09:

- `tools/ci_local.sh` → exit 0 (log `contracts/evidence/T005/ci_local.log`): pytest 60 passed on Python 3.11 and 3.12 (19 in `tests/test_scenarios.py`).
- `python -m app.simulation.scenarios --verify` → `scenario verification: OK` (log `verify.log`), regenerating all 20 scenarios in a temp dir and comparing 204 checksummed files.
- AC1: `test_twenty_scenarios_with_required_metadata` (S01–S20, bilingual metadata with seed, observable behavior, ground truth, expected health response, abstention cases).
- AC2: raw and normalized `.csv.gz` per scenario with equal row counts (`test_raw_and_normalized_have_same_rows`).
- AC3: 35 Golden Cases / 77 expectations in `Data/golden_cases/index.json`; UNKNOWN/abstention expectations in S13–S18 and S20, hard abstention reasons in S12, S15, S16, S17, S20 (`test_abstention_expectations_present_where_required`).
- AC4: `test_reproducible_against_stored_checksums`; checksums cover uncompressed content so they do not depend on the zlib build.
- Ground-truth sanity tests per scenario story: S03, S04, S07/S08, S09/S10, S12, S17, S18, S19, S20.
- Size: scenarios 3.6 MB (gzip). Fixtures in `Data/fixtures/`.
- Correction during the task: initial aging rates were 10× too high for "normal aging" (friction +170% in 120 days); fixed to 0.06/1000h and covered by `test_s03_aging_is_monotonic_and_slow`.
