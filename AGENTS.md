# AGENTS.md — Operating rules for coding agents

Project: Industrial Predictive Maintenance Platform (V5.2). Contract-Driven Development.

## Start of every session
1. Read this file.
2. Read `contracts/CURRENT_TASK.md` and the task file it names.
3. Read only the relevant sections of REQUIREMENTS.md, ARCHITECTURE.md, TASKS.md, ACCEPTANCE.md, DECISIONS.md (the task's Related Requirements tell you which).
4. Inspect related code and tests, then execute within Allowed Scope.

Do not re-ask the user for paths, task IDs, or confirmed requirements. Do not create competing task registries or architecture docs.

## Roles
- **Principal Agent:** owns architecture, requirements, task assignment, gates, and major decisions.
- **Task Agent:** implements, tests, verifies, documents, and hands off one assigned task.

## Hard rules
- Never fabricate test results, approvals, production data, model accuracy, or completion.
- Simulated data is always labeled; never presented as real results.
- Production IoT DB access is read-only, template-based, bounded.
- Ollama is the only LLM backend; core functions work without it; CI uses mocked Ollama.
- LLM never controls equipment, changes safety rules, publishes models, or invents probabilities/RUL.
- Health state is an output, never a training label. Normal aging never enters the verified healthy reference.
- Never weaken safety rules silently. Never skip, disable, or quarantine tests to get green.
- User approvals happen only at gates G1 (after T008), G2 (after T014), G3 (after T020), G4 (T028), plus exceptional approvals in ACCEPTANCE.md §4. Silence is not approval.

## Task workflow
1. Set the task to IN_PROGRESS in its file and in TASKS.md.
2. Implement within Allowed Scope; add focused tests.
3. Run verification; record actual commands and results in the task's Evidence section; put artifacts in `contracts/evidence/TXXX/`.
4. Run `python tools/check_contracts.py`.
5. Set DONE only when ACCEPTANCE.md §1 holds; otherwise FAILED or BLOCKED with the reason.
6. Hand off using the format below; the Principal Agent assigns the next task and updates CURRENT_TASK.md.

## Handoff format
**Task** · **Status** (DONE/FAILED/BLOCKED) · **Implemented** · **Modified Files** · **Verification** (commands and actual results) · **Evidence** · **Tools Used** (only if actually used) · **Risks** · **Next Step**

## Conventions
- Internal docs and agent communication: English. User-facing UI and gate material: zh-CN and en-US.
- Backend: Python 3.11/3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, pytest. Layer import rule in ARCHITECTURE §3.
- Frontend: Vue 3, Vite, TypeScript, Vue Router, ECharts, SVG, vue-i18n, Vitest, Playwright.
- Commits: one task per branch `task/TXXX-short-name`; message prefix `TXXX:`.
