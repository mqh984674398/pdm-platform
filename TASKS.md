# TASKS — Registry (single source of truth for task status)

Statuses: TODO / IN_PROGRESS / BLOCKED / FAILED / DONE. Details live in `contracts/tasks/TASK-XXX.md`.
Do not add top-level tasks without Principal Agent approval; subtasks go inside the task file.

| Task | Title | Phase | Depends on | Gate | Status |
|---|---|---|---|---|---|
| [T001](contracts/tasks/TASK-001.md) | Repository audit and Contract setup | 1 | — |  | DONE |
| [T002](contracts/tasks/TASK-002.md) | Frontend/backend skeleton and test infrastructure | 1 | T001 |  | DONE |
| [T003](contracts/tasks/TASK-003.md) | Domain, signal, API, and result schemas | 1 | T002 |  | DONE |
| [T004](contracts/tasks/TASK-004.md) | Deterministic Data/ simulator | 1 | T003 |  | DONE |
| [T005](contracts/tasks/TASK-005.md) | Golden Cases and scenario fixtures | 1 | T004 |  | DONE |
| [T006](contracts/tasks/TASK-006.md) | UI design system and bilingual switching | 2 | T002 |  | DONE |
| [T007](contracts/tasks/TASK-007.md) | Machine dashboard and component status map | 2 | T003, T005, T006 |  | DONE |
| [T008](contracts/tasks/TASK-008.md) | SQL Data Source Studio frontend Demo | 2 | T003, T005, T006 | G1 | DONE |
| [T009](contracts/tasks/TASK-009.md) | Time-series database adapter | 3 | T003 |  | DONE |
| [T010](contracts/tasks/TASK-010.md) | Secure read-only SQL query service | 3 | T009 |  | DONE |
| [T011](contracts/tasks/TASK-011.md) | Signal mapping and preview APIs | 3 | T010 |  | DONE |
| [T012](contracts/tasks/TASK-012.md) | Data quality, unit conversion, and time alignment | 3 | T011 |  | DONE |
| [T013](contracts/tasks/TASK-013.md) | Operating-regime and movement-cycle processing | 3 | T012 |  | DONE |
| [T014](contracts/tasks/TASK-014.md) | Component lifecycle and maintenance services | 3 | T013 | G2 | DONE |
| [T015](contracts/tasks/TASK-015.md) | Feature extraction and feature versioning | 4 | T013, T014 |  | DONE |
| [T016](contracts/tasks/TASK-016.md) | Healthy/adaptive baselines and degradation monitoring | 4 | T015, T014 |  | DONE |
| [T017](contracts/tasks/TASK-017.md) | Statistical rules and alarm-event engine | 4 | T016 |  | DONE |
| [T018](contracts/tasks/TASK-018.md) | Maintenance stabilization and impact analysis | 4 | T014, T016, T017 |  | DONE |
| [T019](contracts/tasks/TASK-019.md) | Advanced interactive time-series charting | 4 | T006, T011, T016 |  | IN_PROGRESS |
| [T020](contracts/tasks/TASK-020.md) | Full-stack component health dashboard | 4 | T007, T017, T018, T019 | G3 | TODO |
| [T021](contracts/tasks/TASK-021.md) | Component-specific model routing | 5 | T015, T017 |  | TODO |
| [T022](contracts/tasks/TASK-022.md) | Decision-tree and XGBoost modeling | 5 | T021, T005 |  | TODO |
| [T023](contracts/tasks/TASK-023.md) | CNN/LSTM feasibility and optional integration | 5 | T022 |  | TODO |
| [T024](contracts/tasks/TASK-024.md) | Evidence fusion and maintenance decision engine | 6 | T017, T021, T022 |  | TODO |
| [T025](contracts/tasks/TASK-025.md) | Historical replay and rapid parameter optimization | 6 | T024, T005 |  | TODO |
| [T026](contracts/tasks/TASK-026.md) | Model registry, evaluation, and rollback | 6 | T022, T025 |  | TODO |
| [T027](contracts/tasks/TASK-027.md) | Ollama-only LLM, local RAG, and feedback | 6 | T020, T024 |  | TODO |
| [T028](contracts/tasks/TASK-028.md) | Windows/LAN deployment and final acceptance | 7 | T002–T027 | G4 | TODO |

## Milestone gates

| Gate | After | Blocks |
|---|---|---|
| G1 Frontend demonstration | T008 | Finalizing major UX architecture (T019, T020 UX decisions) |
| G2 Data and domain validation | T014 | T015–T018 semantics |
| G3 Health monitoring validation | T020 | T024 health interpretation, T027 explanations of it |
| G4 Production release acceptance | T028 | Production data connection and official alerting |

While a gate awaits approval, dependency-ready tasks that do not depend on the gated decision continue.
