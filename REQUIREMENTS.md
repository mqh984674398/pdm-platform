# REQUIREMENTS — Industrial Predictive Maintenance Platform (V5.2)

Source: V5.2 Contract-Driven Development prompt (approved by the user, 2026-10-09).
Requirement IDs are stable. Tasks cite them; never renumber. Add new IDs at the end of a section.

Keywords: **MUST** = mandatory, **SHOULD** = expected unless justified in DECISIONS.md, **MAY** = optional.

## 1. General (GEN)

| ID | Requirement |
|---|---|
| GEN-01 | The repository is the single source of truth for tasks, contracts, and evidence. |
| GEN-02 | Test results, approvals, production data, model accuracy, and completion MUST NOT be fabricated. |
| GEN-03 | Simulated data MUST be explicitly labeled and MUST NOT be presented as real industrial results. |
| GEN-04 | Core monitoring, prediction, alarms, and safety logic MUST function without the LLM. |
| GEN-05 | User-facing UI and approval material MUST support Chinese and English. Internal agent docs are English. |
| GEN-06 | Prediction evidence MUST preserve model version, feature version, config version, and timestamps. |
| GEN-07 | When evidence is insufficient, outputs MUST be UNKNOWN or an explicit unsupported-prediction result. |

## 2. Technology stack (STK)

| ID | Requirement |
|---|---|
| STK-01 | Frontend: Vue 3, Vite, TypeScript, Vue Router, ECharts, SVG diagrams; Pinia only where shared state is justified. |
| STK-02 | Backend: Python 3.11/3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL (application DB). |
| STK-03 | Analytics: NumPy, SciPy, statsmodels, scikit-learn, XGBoost. PyTorch / Optuna / survival libs only when justified (DECISIONS.md). |
| STK-04 | LLM: Ollama only, local execution. No vLLM, no second backend, no cloud fallback. |
| STK-05 | Deployment: Windows application server, LAN, browser clients, no client-side runtime install. |
| STK-06 | Modular monolith backend; online inference, offline training, and LLM run as separately managed processes. No microservices/Kubernetes. |

## 3. L1 Time-series data access (L1)

| ID | Requirement |
|---|---|
| L1-01 | Connect to the existing IoT time-series SQL database through a database adapter abstraction. |
| L1-02 | Access MUST be read-only (read-only credentials plus server-side enforcement). |
| L1-03 | Support historical range queries and incremental (since-watermark) queries. |
| L1-04 | Read-only metadata discovery (schemas, tables, columns, distinct device/key names). |
| L1-05 | Only authorized, parameterized query templates execute; no arbitrary SQL from untrusted users. |
| L1-06 | Bounded execution: row limits, time-range limits, statement timeouts, concurrency limits. |
| L1-07 | A simulated data adapter implements the same interface as the SQL adapter. |
| L1-08 | Actual DB engine, schema, identifiers, timestamp and value fields MUST be verified, not assumed from the example query (`iotsharp.telemetrydata`). |

## 4. L2 Signal registry and semantic mapping (L2)

| ID | Requirement |
|---|---|
| L2-01 | Map device ID + KeyName to logical signals. |
| L2-02 | Time/value field mapping, units, and engineering conversions per signal. |
| L2-03 | Signal groups and component association. |
| L2-04 | Visualization configuration per signal (templates). |
| L2-05 | Signal configuration is versioned. |
| L2-06 | Raw telemetry, normalized signals, features, and visualization data are separate layers; downsampled data MUST NOT replace full-resolution algorithm inputs. |

## 5. L3 Equipment state and component lifecycle (L3)

| ID | Requirement |
|---|---|
| L3-01 | Equipment/component topology (machine → component instances). |
| L3-02 | Operating State enum: RUNNING / IDLE / STOPPED / MAINTENANCE / FAULT / UNKNOWN. |
| L3-03 | Operating Regime from observable conditions (speed, direction, acceleration phase, load class, recipe). |
| L3-04 | Movement phases / cycles for actuators (extend/retract, vacuum release, motion segments). |
| L3-05 | Maintenance events (lubrication, partial repair, replacement, inspection) as intervention events. |
| L3-06 | Component lifecycle: installation, accumulated operation, maintenance, replacement, retirement. Replacement preserves history and creates a new lifecycle. |
| L3-07 | Maintenance workflow: MAINTENANCE_EVENT → STABILIZATION → POST_MAINTENANCE_VALIDATION → NORMAL_MONITORING or REVIEW_REQUIRED. |
| L3-08 | Lubrication MUST NOT automatically reset component aging. |

## 6. L4 Features and statistical monitoring (L4)

| ID | Requirement |
|---|---|
| L4-01 | Data quality metrics: missing, duplicates, out-of-order, jitter, gaps, sampling interval, unit plausibility. |
| L4-02 | Timestamp alignment of related signals (e.g. speed/torque). |
| L4-03 | Operating-regime normalization (condition-normalized residuals). |
| L4-04 | Versioned feature extraction with declared feature schemas. |
| L4-05 | Three independent baselines: Verified Healthy Reference, Adaptive Operating Baseline, Long-Term Degradation History. |
| L4-06 | Normal aging MUST NOT be absorbed into the Verified Healthy Reference. |
| L4-07 | Statistical monitoring: descriptive stats, quantiles, EWMA, CUSUM, change detection, deterministic rules. |

## 7. L5 Prediction engine (L5)

| ID | Requirement |
|---|---|
| L5-01 | Component-specific model routing (not compulsory sequential execution). |
| L5-02 | Each model/operator declares: input signals, supported regimes, sampling requirements, feature schema, output schema, model version, timeout/fallback, eligibility conditions. |
| L5-03 | Decision trees and XGBoost supported. |
| L5-04 | CNN/LSTM only if sampling quality, resolution, and tests justify (feasibility recorded). |
| L5-05 | Survival/RUL only with genuine failure/lifecycle evidence and censoring handling; otherwise unsupported. |
| L5-06 | Output semantics are typed and not interchangeable: anomaly score, class probability, degradation indicator, failure probability. |

## 8. L6 Evidence fusion and decisions (L6)

| ID | Requirement |
|---|---|
| L6-01 | Prediction eligibility checks before use of any model output. |
| L6-02 | Conflict and uncertainty handling across evidence sources. |
| L6-03 | Deterministic safety constraints that no model or LLM can override. |
| L6-04 | Health State enum: NORMAL / WATCH / WARNING / CRITICAL / UNKNOWN. Health state is an output, never a self-generated training label. |
| L6-05 | Maintenance recommendations with traceable evidence. |

## 9. L7 Visualization, LLM, feedback (L7 / UI / LLM)

| ID | Requirement |
|---|---|
| UI-01 | Multi-machine health overview. |
| UI-02 | Interactive per-machine component status map (SVG). |
| UI-03 | Component history and health details. |
| UI-04 | SQL Data Source Studio (connection, schema inspection, device/signal selection, templates, field mapping, units, grouping, preview, sampling/quality, component association, viz templates, config versioning). Ordinary users need no SQL. |
| UI-05 | Signal configuration and preview. |
| UI-06 | Time-series analysis dashboard (high-performance charts). |
| UI-07 | Healthy reference vs adaptive baseline comparison. |
| UI-08 | Maintenance timeline. |
| UI-09 | Alarm review and feedback. |
| UI-10 | Parameter optimization comparison. |
| UI-11 | Model version and validation interface. |
| UI-12 | Local Ollama configuration and diagnostic assistant. |
| UI-13 | Design: professional industrial visual language, macOS-inspired interaction quality, consistent health colors, subtle animation, responsive, zh/en switch without reload. |
| LLM-01 | Configurable local Ollama endpoint, admin-selectable installed model, health checks. |
| LLM-02 | Chat completion, streaming where supported, timeout and cancellation, structured response validation. |
| LLM-03 | Local embeddings and local RAG over approved documents with citations. |
| LLM-04 | Reject remote/cloud endpoints and cloud-routed Ollama models; endpoint and model allowlists. |
| LLM-05 | LLM MUST NOT invent probabilities/RUL, modify safety settings, control PLC/servo, override rules, publish models, or turn retrieved text into privileged commands. Retrieved documents are untrusted. |
| LLM-06 | Mocked Ollama in CI; live tests opt-in only. Ollama not required for unrelated development. |
| FB-01 | User feedback on alarms and maintenance records feeds review, never directly into verified healthy training data. |

## 10. Simulation workspace (SIM)

| ID | Requirement |
|---|---|
| SIM-01 | Repository directory `Data/` with README.md, manifest.json, config/, simulated/, scenarios/, fixtures/, golden_cases/. |
| SIM-02 | Deterministic, seeded, configurable generator: multiple machines, component instances, regimes, timestamps, units, maintenance events, lifecycle IDs. |
| SIM-03 | The 20 required scenarios (see §14 below). |
| SIM-04 | Each scenario: seed, metadata, expected observable behavior, ground truth, expected health response, required abstention/fallback cases. |
| SIM-05 | Both raw IoT-style and normalized representations. |

## 11. Optimization and model governance (OPT)

| ID | Requirement |
|---|---|
| OPT-01 | Path A fast configuration optimization (windows, non-safety thresholds, hysteresis, regime mapping, baseline config). |
| OPT-02 | Path B calibration (decision thresholds, score calibration, alert post-processing). |
| OPT-03 | Path C retraining (features, bounded hyperparameter search, candidates, independent validation). |
| OPT-04 | Champion–Challenger lifecycle evaluated by historical replay and Golden Cases. |
| OPT-05 | Never silently weaken safety rules; never treat drifting online observations as verified healthy data. |
| OPT-06 | Preserve previous models/configs for rollback. |

## 12. Security (SEC)

| ID | Requirement |
|---|---|
| SEC-01 | Authentication and role-based authorization (at least viewer / maintenance / engineer / admin). |
| SEC-02 | Audit log for configuration changes, model promotions, approvals, and query template changes. |
| SEC-03 | Credentials and LLM configuration kept server-side; never sent to the browser. |
| SEC-04 | LAN access restrictions for inference services. |
| SEC-05 | RAG documents protected by authorization rules. |
| SEC-06 | Production data connection and official alerting require explicit user approval (G4). |

## 13. Testing (TST)

| ID | Requirement |
|---|---|
| TST-01 | Pytest (backend/algorithms), Vitest (frontend), TypeScript type check, API integration, browser E2E. |
| TST-02 | Historical replay and Golden Cases as regression suites. |
| TST-03 | Prevent future-data leakage; no random splits of overlapping sequences from one lifecycle. |
| TST-04 | Simulated fault detection is not reported as real-world accuracy. |

## 14. Component scope and required scenarios

Components: ball screw drive (servo speed, torque), linear motor (real-time speed), vacuum cup/chamber (release duration), pneumatic cylinder (extension and retraction durations), cam and gear mechanisms (future servo telemetry; extensible templates only).

Constraints: no assumed extra sensors; servo torque alone does not prove ball-screw wear; release duration alone does not give leakage rate; no reliable RUL without failure/lifecycle evidence.

Scenarios S01–S20: healthy; multi-regime; normal aging; torque drift; linear-motor speed instability; vacuum release increase; cylinder extension slowdown; cylinder retraction slowdown; lubrication improvement; lubrication deterioration; partial repair; complete replacement; missing/duplicate telemetry; timestamp jitter/out-of-order; speed/torque sync errors; sensor bias/unit mismatch; unknown regime; incomplete actuator operation; shared drive-chain abnormality; data-source interruption and recovery.
