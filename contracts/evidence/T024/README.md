# T024 evidence: evidence fusion and maintenance decisions

All data is simulated.

- Engine: `backend/app/decision/fusion.py` (interpretation table, preconditions, safety floor, model conflict rules, `guard`, recommendations) and `backend/app/decision/aging.py` (D-022 aging grading). The dashboard and `GET /api/components/{id}/health` now use it; the report carries `recommendations`.
- Tests: `pytest tests/decision` passes 35 tests, covering AC1–AC4 and golden cases on the replayed pipeline (S01, S03, S04, S07, S11, S19).
- CI (`ci_local.log`): backend 466 passed on Python 3.11 and 3.12, schema drift OK, frontend 41 unit and 12 E2E passed.
- Golden Case comparison (`golden_fused.json`, from `backend/scripts/g3_data.py`): **1199/1310** graded windows are within the allowed levels after fusion. Rules alone gave 1048/1310 (G3).
  - S03 second 60 days: A03-BS1 has 101/102 windows at WATCH and 1 CRITICAL (a short abrupt step above the trend); A03-CY1 has 107/107 at WATCH. Rules alone gave 59 WARNING and 4 CRITICAL on BS1, and 82 WARNING on CY1.
  - S11 after partial repair: 67/67 windows at WATCH, where rules alone gave 7 WARNING.
  - Unchanged and still deviating: S03 first 60 days (CUSUM gives WATCH where NORMAL is expected; D-022 allows WATCH), S12 slow detection (14 windows at WATCH), S10 (22 CRITICAL), S09 (1 NORMAL early, 4 WATCH after).
