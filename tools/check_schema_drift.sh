#!/usr/bin/env bash
# Fail if contracts/schemas/openapi.json or frontend/src/api/generated.ts is out of date.
# Usage: tools/check_schema_drift.sh [python]   (python must have backend deps; default: python3)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${1:-python3}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
(cd "$ROOT/backend" && "$PY" scripts/export_openapi.py "$TMP/openapi.json" >/dev/null)
diff -u "$ROOT/contracts/schemas/openapi.json" "$TMP/openapi.json" || { echo "openapi.json drift: run backend/scripts/export_openapi.py"; exit 1; }
(cd "$ROOT/frontend" && npx openapi-typescript "$TMP/openapi.json" -o "$TMP/generated.ts" >/dev/null 2>&1 \
  && npx prettier --stdin-filepath src/api/generated.ts < "$TMP/generated.ts" > "$TMP/generated.fmt.ts")
diff -u "$ROOT/frontend/src/api/generated.ts" "$TMP/generated.fmt.ts" || { echo "generated.ts drift: run npm run gen:types"; exit 1; }
echo "schema drift check OK"
