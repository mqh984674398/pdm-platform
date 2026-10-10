# T026 evidence: model registry, evaluation and rollback

All data is simulated.

- Registry: `backend/app/core/registry.py` with table `deployment_versions` (migration 0008). It keeps versions per kind (`decision-config`, `component-model:<TYPE>`) with the statuses CANDIDATE, CHAMPION, RETIRED and REJECTED. Nothing is deleted.
- AC1, promotion: needs an administrator, a comment, and an evaluation with `gate_passed` measured against the current champion (`baseline_version`). Each step is audited (`registry.seed/propose/promote/reject/rollback`).
  - Decision-config gate (`app/optimization/deployment.py`): the candidate and the champion are replayed and scored on the Golden Case suite. The gate needs at least as many windows within, no more windows below, and identical safety rules.
  - Model gate (Path C): lifecycle-grouped validation must exist, ROC AUC ≥ 0.8, and F1 must not be below the champion's. Path C retraining is `backend/scripts/train_models.py --version X` (T022); its registered models are proposed through `POST /api/registry/models/candidates`.
- AC2, rollback: `POST /api/registry/rollback` restores the champion's predecessor as a new CHAMPION version with the same payload (rule set, thresholds and aging policy, or model), in one audited action.
- AC3, training data: a model is refused unless its labels are recorded truth (`SIMULATED truth…` or `Recorded failure…`). Labels mentioning health states, adaptive baselines or online windows are refused. A verified healthy reference can only be created by an engineer's verification (`save_snapshot` refuses VERIFIED_HEALTHY, from T016).
- In force: `app/decision/config.py` reads the decision-config champion. The dashboard, health reports, alarm evaluation and optimization runs all use it. The rules version reads e.g. `pdm-rules@1.0.0+OPT-…-A05+0` after a promotion.
- UI: `/models` (ModelsView) shows the version in use, candidates with the champion-versus-candidate replay counts, gate status and reasons, promote and reject with a required comment, one-step restore, and history. `/optimization` can submit the recommended challenger. During development the role is chosen from a "development login" selector (D-010 dev headers until T028).
- Tests: `pytest tests/registry` (10 passed); E2E `tests/e2e/models.spec.ts` (submit, engineer refused, admin promotes, rollback). It runs as a separate Playwright project after the others because a promotion changes health for every component.
- CI (`ci_local.log`): backend 485 passed on Python 3.11 and 3.12, schema drift OK, frontend 42 unit and 14 E2E passed.
