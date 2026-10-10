# ARCHITECTURE — Industrial Predictive Maintenance Platform (V5.2)

Approved baseline. Changes to layers, process model, or data contracts require an entry in DECISIONS.md and Principal Agent approval (major changes also need user approval).

## 1. Process model (Windows server, LAN)

```text
Browser (Vue 3 SPA, zh/en)
   │ HTTPS (LAN)
   ▼
api        FastAPI app: REST, auth, config, read-only query service, decisions, UI APIs
worker     Online inference: scheduled incremental reads → features → monitoring → routing → fusion
trainer    Offline training / replay / optimization jobs (manually or schedule triggered)
llm        LLM gateway: Ollama client, RAG index, local embeddings (optional; platform runs without it)
   │
   ├── PostgreSQL (application DB: config, registry, lifecycle, features, results, audit)
   ├── IoT time-series DB (external, READ-ONLY)
   └── Ollama (127.0.0.1 or approved LAN host, local models only)
```

All four Python processes share one code base (`backend/app`) and are started as separate Windows services (decided in T028). No microservices, no Kubernetes.

## 2. Repository layout (target)

```text
AGENTS.md  REQUIREMENTS.md  ARCHITECTURE.md  TASKS.md  ACCEPTANCE.md  DECISIONS.md
contracts/  CURRENT_TASK.md, tasks/TASK-001..028.md, audit/, evidence/
backend/    app/ (layers below), alembic/, tests/, pyproject.toml
frontend/   src/ (views, components, charts, diagrams, i18n, api), tests/, package.json
Data/       README.md, manifest.json, config/, simulated/, scenarios/, fixtures/, golden_cases/
tools/      repository scripts (contract checks, simulator CLI wrappers)
deploy/     Windows service and LAN deployment assets (T028)
```

## 3. Seven logical layers → backend packages

| Layer | Package | Responsibility |
|---|---|---|
| L1 | `app/datasource` | Adapter interface; SQL adapter (read-only); simulated adapter; metadata discovery; query templates; bounds and timeouts |
| L2 | `app/signals` | Signal registry, KeyName mapping, units/conversions, groups, viz templates, config versions |
| L3 | `app/equipment` | Topology, operating state, regimes, movement cycles, maintenance events, lifecycles, maintenance workflow state machine |
| L4 | `app/monitoring` | Data quality, alignment, normalization, features (versioned), three baselines, EWMA/CUSUM/change detection, rules |
| L5 | `app/prediction` | Operator/model contracts, component templates, routing, tree/XGBoost, optional DL, optional survival |
| L6 | `app/decision` | Eligibility, fusion, uncertainty, safety constraints, health state, recommendations |
| L7 | `app/llm`, `app/feedback`, frontend | Ollama gateway, RAG, feedback, all UI |
| X | `app/core` | Auth, RBAC, audit, settings, model registry, replay, optimization, rollback |

Dependency rule: a layer may import only from lower layers and `app/core`. L7 LLM code may read L6 outputs but nothing in L1–L6 imports `app/llm`.

## 4. Data layers (never conflated)

1. **Raw telemetry**: rows as returned by the source (or simulated raw IoT-style rows).
2. **Normalized signals**: logical signal, UTC timestamp, value in SI/engineering unit, quality flags, source reference.
3. **Features**: per window/cycle, versioned (`feature_set@version`), with regime and lifecycle IDs.
4. **Results**: typed outputs (anomaly score, class probability, degradation indicator, failure probability, health state) with evidence references and versions.
5. **Visualization data**: downsampled series (e.g. LTTB) produced on demand; never written back as algorithm input.

## 5. Core domain contracts (defined in T003)

- `Machine`, `ComponentType`, `ComponentInstance`, `ComponentLifecycle`
- `SignalDefinition`, `SignalMapping`, `SignalGroup`, `UnitConversion`, `SignalConfigVersion`
- `OperatingState` (RUNNING/IDLE/STOPPED/MAINTENANCE/FAULT/UNKNOWN)
- `OperatingRegime`, `MovementCycle`
- `HealthState` (NORMAL/WATCH/WARNING/CRITICAL/UNKNOWN)
- `MaintenanceEvent`, `MaintenanceWorkflowState` (MAINTENANCE_EVENT/STABILIZATION/POST_MAINTENANCE_VALIDATION/NORMAL_MONITORING/REVIEW_REQUIRED)
- `Baseline` (kind: VERIFIED_HEALTHY / ADAPTIVE / DEGRADATION_HISTORY)
- `OperatorSpec` (inputs, regimes, sampling, feature schema, output schema, version, timeout, fallback, eligibility)
- `PredictionResult` (discriminated union by output kind) and `UnsupportedPrediction`
- `Evidence`, `Decision`, `Recommendation`, `Alarm`, `Feedback`
- Every result carries `model_version`, `feature_version`, `config_version`, `computed_at`, `data_window`, `is_simulated`.

Pydantic models are the source; TypeScript types are generated from the OpenAPI schema (no hand-maintained duplicates).

## 6. Data source security

- Read-only DB user; adapter additionally rejects non-SELECT statements and multi-statements.
- Users choose from approved templates; parameters are bound, identifiers allowlisted from discovered metadata.
- Limits: max rows, max time range, statement timeout, per-user concurrency.
- Template creation/edit is admin-only and audited.

## 7. LLM boundary

- Single provider: Ollama. Endpoint allowlist (loopback / approved LAN host), model allowlist from installed `ollama list`, reject cloud-routed model names.
- LLM receives verified evidence objects, never raw credentials; outputs are validated against schemas and labeled as explanations.
- No tool or path lets LLM output change safety rules, models, configs, or equipment.

## 8. Frontend

- Vue 3 + Vite + TS; Vue Router; ECharts for time series (large-mode, dataZoom, server-side downsampling); SVG for machine/component diagrams.
- Design tokens (health colors, spacing, typography) in one theme module; light/dark capable.
- vue-i18n with zh-CN and en-US; switching at runtime without reload.
- Simulated data is visibly badged in every view that shows it.
