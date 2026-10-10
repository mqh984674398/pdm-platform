# Post-deploy round 2 (2026-10-10): theme, scrollbars, TDengine, simulation database naming

Request: Mira, 2026-10-10T13:34Z (D-035, D-036).

Verification run in the cloud container (Linux, Python 3.12):
- `backend: ruff check . && ruff format --check . && pytest` → all passed (new: tests/query_service/test_tdengine.py, 8 tests against a faked TDengine REST server).
- `tools/check_schema_drift.sh` → schema drift check OK
- `python3 tools/check_contracts.py` → OK
- `frontend: npm run lint && npm run typecheck && npx vitest run` → 48 tests passed (new: tests/unit/theme.spec.ts)
- `frontend: npm run build && npm run test:e2e` → 18 passed (studio e2e now runs as administrator; ordinary users see the TDengine notice)

Not verified: a real TDengine server; real Windows browsers for scrollbar appearance.
