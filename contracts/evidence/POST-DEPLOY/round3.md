# Post-deploy round 3 (2026-10-10): plant structure, shared drive chain, rename

Request: Mira, 2026-10-10T14:25Z (D-037, D-038, D-039).

Verification in the cloud container (Linux, Python 3.12, Chromium):
- backend `ruff check`, `ruff format --check`, `pytest` → all passed (new: tests/equipment/test_plant.py 4 tests, tests/decision/test_common_cause.py 3 tests incl. S19 replay; migration 0012 matches models)
- `tools/check_schema_drift.sh` → OK; `tools/check_contracts.py` → OK
- frontend lint, typecheck, `vitest` → 48 passed
- frontend `test:e2e` → 19 passed (new: plant.spec.ts builds a workshop/process/machine with two chained components and picks it in Algorithm configuration)

Not verified: a real TDengine device list bound through the tree; real Windows browsers.
