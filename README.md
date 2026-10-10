# Industrial Predictive Maintenance Platform · 工业预测性维护平台

Contract-driven development (V5.2). Start with [AGENTS.md](AGENTS.md).

| Document | Purpose |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Requirement IDs |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Seven-layer architecture and process model |
| [TASKS.md](TASKS.md) | 28-task registry and status |
| [ACCEPTANCE.md](ACCEPTANCE.md) | Definition of Done and gates G1–G4 |
| [DECISIONS.md](DECISIONS.md) | Decision log |
| [contracts/CURRENT_TASK.md](contracts/CURRENT_TASK.md) | Currently assigned task |

Check contract integrity: `python tools/check_contracts.py`

All demonstration data in this repository is **simulated** unless explicitly stated otherwise. 本仓库中的演示数据均为**模拟数据**，除非另有明确说明。

## Development

Backend (Python 3.11 or 3.12):

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"   # Windows: .venv\Scripts\pip
pytest                       # tests
ruff check . && ruff format --check .
uvicorn app.main:app --port 8000
```

Settings come from `PDM_*` environment variables (e.g. `PDM_DATABASE_URL`). Ollama is not needed for development.

Frontend (Node 20+):

```bash
cd frontend
npm ci
npm run dev                  # http://localhost:5173, proxies /api to :8000
npm test && npm run typecheck && npm run lint && npm run build
npm run test:e2e             # Playwright; set PW_CHROMIUM_PATH to reuse an installed Chromium
```
