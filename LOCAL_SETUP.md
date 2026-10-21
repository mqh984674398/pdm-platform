# 本地开发与交接 / Local development and hand-over

本项目从云端会话移到本机继续开发（2026-10-21，Mira 的要求）。内部文档与协作沿用 `AGENTS.md`。
The project moved from the cloud session to this computer. Working rules stay in `AGENTS.md`.

## 当前状态 / State at hand-over
- 分支 / branch: `claude/project-thread-q93o73`（GitHub PR #4，尚未合并到 `main`）。T001–T028 全部 DONE；之后的改动记在 `DECISIONS.md` 的 D-040 … D-054。
- 最新升级包 / latest package: `release/v0.1.5/`（代码包，约 4.6 MB，SHA-256 见 `SHA256SUMS.txt`；迁移到 0017）。完整安装包（含 Python，0.1.2 / 0.1.3）太大，没有放进仓库，仍在项目文件夹里。
- 分析文档 / analysis notes: `docs/analysis/`（算法审查、配置工作台重做计划）。
- 从未验证过 / never verified: 对真实涛思服务器、在真实 Windows 上运行升级脚本、真实 Ollama、真实触屏。

## 环境 / Prerequisites
Python 3.12（或 3.11）、Node 20+、git。Python 3.12 or 3.11, Node 20+, git.

## 后端 / Backend (PowerShell)
```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q -W ignore
.venv\Scripts\ruff check . ; .venv\Scripts\ruff format --check .
```
演示服务器（仿真数据，端口 8765）/ demo server (simulated data):
```powershell
.venv\Scripts\python scripts\demo_server.py --db var\demo.db --port 8765
```
默认运行模式是“仿真演示”；管理员在“数据源”页切换到“正式运行”（D-053）。The default run mode is the simulation demo; administrators switch to production on the Data sources page.

## 前端 / Frontend
```powershell
cd frontend
npm ci
npm run dev                 # http://localhost:5173，/api 代理到 :8000（可用 PDM_API_URL 改）
npx vue-tsc --noEmit ; npx eslint . ; npx vitest run
npm run build ; npx playwright test      # 端到端会自己启动演示后端（端口 8765）
```
Playwright 用 `PW_CHROMIUM_PATH` 指定已安装的 Chromium；先 `npm run build`，预览服务器使用构建结果。

## 一键演示 / One-click demo
`tools\run_demo.cmd`（仿真数据；在 Windows 上未完整验证 / not fully verified on Windows）。

## 契约检查 / Contract checks
```powershell
python tools\check_contracts.py
# 接口定义改动后 / after API changes:
backend\.venv\Scripts\python backend\scripts\export_openapi.py contracts\schemas\openapi.json
cd frontend ; npm run gen:types
```
`tools/check_schema_drift.sh` 是 CI 用的一致性检查（bash）。

## 打升级包 / Build an upgrade package
```powershell
cd frontend ; npm run build ; cd ..
backend\.venv\Scripts\python deploy\build_upgrade.py --out dist
```
只在 Mira 明确要求时打包；版本号在 `backend/app/__init__.py`、`backend/pyproject.toml`、`frontend/package.json`。Build only when asked.

## 不在仓库里的东西 / Not in the repository
- `backend/var/models`（决策树 / XGBoost 演示模型，已 gitignore）：`python scripts\train_models.py --models var\models --report ..\contracts\evidence\T022` 重新生成。
- 涛思账号：写在服务器的 `backend\.env`（`PDM_SECRET_<源编号>=用户:密码`），不进仓库。
- 完整离线安装包（含 Python 运行时）。

## Git
`origin` 指向 `https://github.com/mqh984674398/pdm-platform`。提交信息以 `T028:` 开头并按 `AGENTS.md` 的流程记录决策与证据。
