#!/usr/bin/env bash
# One-click test run of the platform on the SIMULATED demo data (Linux/macOS/Git Bash).
#
#   tools/run_demo.sh            start the demo, run the end-to-end flow check, keep it running for the browser
#   tools/run_demo.sh --check    start, run the flow check, stop (exit code 0 only if every step passed)
#   tools/run_demo.sh --e2e      as --check, then the browser tests (frontend/tests/e2e)
#
# Needs Python 3.11/3.12 (PY=/path/to/python to choose; a backend/.venv is created and filled from
# backend/requirements.lock when missing) and Node 20+ for the browser client (built when frontend/dist is
# missing). The demo uses a fresh SQLite database under $TMPDIR and never touches a configured database.
# Browser: http://127.0.0.1:$PORT  accounts: admin / engineer  password: $PDM_DEMO_PASSWORD
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE=serve
case "${1:-}" in --check) MODE=check ;; --e2e) MODE=e2e ;; "" ) ;; *) echo "usage: $0 [--check|--e2e]"; exit 2 ;; esac
PORT="${PORT:-8765}"
PASSWORD="${PDM_DEMO_PASSWORD:-demo-pdm-2026}"
WORK="${TMPDIR:-/tmp}/pdm-demo"
mkdir -p "$WORK"

say() { printf '\n== %s\n' "$*"; }

say "Python"
if [ -n "${PY:-}" ]; then :
elif [ -x backend/.venv/bin/python ]; then PY=backend/.venv/bin/python
elif [ -x backend/.venv/Scripts/python.exe ]; then PY=backend/.venv/Scripts/python.exe
else
  for c in python3.12 python3.11 python3; do command -v "$c" >/dev/null 2>&1 && { BASE=$c; break; }; done
  [ -n "${BASE:-}" ] || { echo "No Python found; install Python 3.12 or set PY="; exit 1; }
  "$BASE" -m venv backend/.venv
  PY=backend/.venv/bin/python; [ -x "$PY" ] || PY=backend/.venv/Scripts/python.exe
  "$PY" -m pip install -q -r backend/requirements.lock
  "$PY" -m pip install -q --no-deps ./backend
fi
"$PY" --version
"$PY" -c "import fastapi, sqlalchemy, alembic, uvicorn" 2>/dev/null || {
  echo "Backend dependencies missing in $PY; run: $PY -m pip install -r backend/requirements.lock && $PY -m pip install --no-deps ./backend"; exit 1; }

say "Browser client"
if [ ! -f frontend/dist/index.html ]; then
  command -v npm >/dev/null 2>&1 || { echo "frontend/dist is missing and npm is not installed"; exit 1; }
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi
echo "frontend/dist ready"

say "Starting the demo server on port $PORT (simulated data; building the demo fleet takes a minute)"
LOG="$WORK/server.log"
"$PY" backend/scripts/demo_server.py --db "$WORK/demo.db" --port "$PORT" --host 0.0.0.0 \
  --static frontend/dist --local-auth "$PASSWORD" >"$LOG" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 120); do
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  kill -0 $SERVER 2>/dev/null || { echo "Server exited; log:"; tail -30 "$LOG"; exit 1; }
  sleep 3
done
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "Server did not come up; log:"; tail -30 "$LOG"; exit 1; }

say "Flow check: one new component from plant tree to active prediction configuration"
"$PY" tools/verify_workflow.py --base "http://127.0.0.1:$PORT" --password "$PASSWORD"

if [ "$MODE" = e2e ]; then
  say "Browser tests"
  kill $SERVER 2>/dev/null || true; trap - EXIT
  (cd frontend && PDM_PYTHON="$ROOT/$PY" npm run test:e2e)
  exit 0
fi
[ "$MODE" = check ] && exit 0

say "Ready for manual testing"
echo "Open   http://127.0.0.1:$PORT   (SIMULATED data)"
echo "Sign in as admin or engineer, password: $PASSWORD"
echo "Configuration workbench: Administration > Configuration workbench"
echo "Press Ctrl+C to stop."
wait $SERVER
