# Post-deployment fixes (0.1.1)

Requested by Mira on 2026-10-10 after the first Windows deployment: (1) Studio step 4 had no approved query template, (2) Signal setup showed the T008 placeholder, (3) user and role administration, (4) fixed footer. Decisions D-032, D-033, D-034.

## Verification (2026-10-10, Linux build machine)

- Backend `pytest` (Python 3.12): 524 passed, 4 skipped (PostgreSQL adapter tests skipped: no `PDM_TEST_PG_URL`). New: `tests/auth/test_user_admin.py`, `tests/query_service/test_default_templates.py`; `tests/test_migrations.py` now covers `users` and `role_modules`.
- `ruff check` / `ruff format --check`: clean. `tools/check_contracts.py`: OK. OpenAPI and `generated.ts` regenerated.
- Frontend: vue-tsc, eslint, prettier clean; Vitest 47 passed; Playwright 18 passed (new `tests/e2e/admin.spec.ts`: register/change/delete account, admin-only navigation, signal setup page).
- Production-mode run of `deploy/serve.py` (`PDM_AUTH_MODE=local`, SQLite, `deploy/datasources.simulated.json`, no `--simulated-fleet`): start-up printed `Registered built-in read-only query templates: telemetry-by-key-range, telemetry-incremental`; after sign-in `/api/query-templates` listed both; Studio reached step 4 with two templates (`studio-step4-templates-zh.png`). A maintenance account restricted to overview and alarms got `modules: ["overview","alarms"]` from `/api/auth/me` and 403 on `/api/query-templates`; after deletion its session got 401.
- Screenshots: `studio-step4-templates-zh.png`, `signals-zh.png`, `signals-en.png`, `users-en.png` (all SIMULATED data).

Not verified: installation on the real Windows server (Mira to confirm after upgrading).
