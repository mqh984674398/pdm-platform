# ACCEPTANCE — Definition of Done and Gate Criteria

Task-level acceptance criteria live in each `contracts/tasks/TASK-XXX.md`. This file holds what applies to every task and to each milestone gate.

## 1. Definition of Done (every task)

A task is DONE only when all of the following hold, with evidence recorded in the task file's Evidence section:

1. The approved Allowed Scope is implemented, and nothing outside it changed without approval.
2. Relevant tests pass (actual command output recorded; never fabricated).
3. All task acceptance criteria are satisfied.
4. No known critical regression remains (full existing suite still green).
5. Simulated and real data are clearly distinguished in code, data, UI, and reports.
6. Required zh/en user-facing language support is maintained.
7. Relevant documentation is updated.
8. Contract status is updated in both the task file and TASKS.md.

Reminders: a functional UI is not production readiness; a trained model is not predictive validity; a synthetic demo is not real-world maintenance performance.

## 2. Evidence rules

- Record exact commands and their real results (pass/fail counts, exit codes).
- Store screenshots, reports, and logs under `contracts/evidence/TXXX/`.
- Simulated-data metrics are labeled "simulated" wherever they appear.
- Never claim a Skill, Plugin, or tool was used unless it was.

## 3. Gate criteria

Each gate produces a bilingual (zh/en) demonstration package in `contracts/evidence/GX/` and an approval request to the user. Silence is never approval. Approval is recorded in DECISIONS.md with date and approver.

### G1 — Frontend demonstration (after T008)
- [ ] High-fidelity multi-machine overview.
- [ ] Interactive SVG component health diagram covering all health states.
- [ ] SQL Data Source Studio guided workflow (no SQL needed by ordinary users).
- [ ] Meaningful simulated data from Data/ scenarios, visibly labeled.
- [ ] zh/en switching without reload.
- [ ] User decision on major UX and workflow choices.

### G2 — Data and domain validation (after T014)
- [ ] Source-to-signal mapping on the simulated adapter (and real schema findings if access exists, read-only).
- [ ] Operating-regime interpretation.
- [ ] Component lifecycle behavior incl. replacement and lubrication.
- [ ] Maintenance intervention workflow.
- [ ] Data quality reporting.
- [ ] User approval of industrial data semantics.

### G3 — Health monitoring validation (after T020)
- [ ] Long-term aging vs frozen healthy reference.
- [ ] Statistical drift detection.
- [ ] Frozen and adaptive baselines side by side.
- [ ] Maintenance improvement and deterioration.
- [ ] Component health evidence trail.
- [ ] Alarm and maintenance interfaces.
- [ ] User approval of health interpretation and workflow behavior.

### G4 — Production release acceptance (T028)
- [ ] Historical replay results.
- [ ] ML evaluation (labeled simulated unless real labels exist).
- [ ] Controlled optimization with champion–challenger and rollback.
- [ ] Ollama local operation and local RAG with citations.
- [ ] LLM failure fallback (platform continues without Ollama).
- [ ] Security checks.
- [ ] Windows/LAN deployment results.
- [ ] End-to-end acceptance evidence.
- [ ] Explicit user approval before enabling a production data connection or official alerting workflow.

## 4. Exceptional approvals (outside gates)

Required for: major architecture changes, breaking data-contract changes, destructive data operations, significant security/safety changes, fundamental redesign of approved UX, critical regressions needing cross-task restructuring.
