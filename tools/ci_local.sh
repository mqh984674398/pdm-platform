#!/usr/bin/env bash
# Run the same checks as .github/workflows/ci.yml locally.
# Usage: tools/ci_local.sh   (env: PY311, PY312 = interpreters with backend dev deps; PW_CHROMIUM_PATH optional)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== contracts"; python3 tools/check_contracts.py
for py in "${PY311:-}" "${PY312:-}"; do
  [ -z "$py" ] && continue
  echo "== backend ($("$py" --version))"
  (cd backend && "$py" -m ruff check . && "$py" -m ruff format --check . && "$py" -m pytest)
done
echo "== schema drift"; tools/check_schema_drift.sh "${PY312:-${PY311:-python3}}"
echo "== frontend"
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build && npm run test:e2e)
echo "== ALL CHECKS PASSED"
