# DECISIONS — Architecture and Process Decision Log

Append-only. Each entry: ID, date, status (PROPOSED / APPROVED / SUPERSEDED), decision, rationale, approver. Supersede rather than edit.

## D-001 — Adopt V5.2 contract as project baseline
- **Date:** 2026-10-09 · **Status:** APPROVED · **Approver:** User (Mira), by posting the V5.2 prompt as the project's operating contract.
- **Decision:** The V5.2 Contract-Driven Development prompt defines requirements, stack, seven-layer architecture, 28-task plan, and gates G1–G4. Captured in REQUIREMENTS.md, ARCHITECTURE.md, TASKS.md, ACCEPTANCE.md.

## D-002 — Ollama is the only LLM backend
- **Date:** 2026-10-09 · **Status:** APPROVED (part of D-001)
- **Decision:** Local Ollama only; no vLLM, no cloud inference, no automatic fallback. Platform must run fully without it.

## D-003 — Modular monolith with four managed processes
- **Date:** 2026-10-09 · **Status:** PROPOSED (T001)
- **Decision:** One Python code base with `api`, `worker`, `trainer`, `llm` processes (ARCHITECTURE §1).
- **Rationale:** Satisfies "separately managed online inference, offline training, and LLM processes" without microservices.

## D-004 — TypeScript types generated from OpenAPI
- **Date:** 2026-10-09 · **Status:** PROPOSED (T001)
- **Decision:** Pydantic schemas are the single contract source; frontend types are generated and drift-checked in CI.
- **Rationale:** Prevents competing hand-maintained contracts and unverified frontend-only schemas.

## D-005 — Task contract format
- **Date:** 2026-10-09 · **Status:** PROPOSED (T001)
- **Decision:** TASKS.md is the only status registry; each task file carries Goal, Dependencies, Allowed Scope, Related Requirements, Acceptance Criteria, Required Verification, Deliverables, Failure Recovery, Evidence. `tools/check_contracts.py` enforces structure.

## D-006 — Visualization downsampling server-side
- **Date:** 2026-10-09 · **Status:** PROPOSED (T001)
- **Decision:** Downsampling (e.g. LTTB) happens in the API on request; results are never persisted as algorithm inputs (L2-06).

## D-007 — Local CI-equivalent verification until a GitHub remote exists
- **Date:** 2026-10-09 · **Status:** PROPOSED (T002) · Needs user awareness, not a gate.
- **Decision:** No GitHub repository is connected yet. Until one is, `tools/ci_local.sh` (same commands as `.github/workflows/ci.yml`) is the CI verification of record. Its log is stored per task in `contracts/evidence/TXXX/ci_local.log`. The first real CI run after the first push is recorded retroactively in T002 evidence; any failure there reopens T002.
- **Rationale:** Avoids blocking the dependency chain on repository access while keeping verification real.

## D-008 — Simulator lives outside the runtime layers
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification within T004)
- **Decision:** The generator is `backend/app/simulation/` (composition-level, like `app/api`), because it builds L1–L3 objects (raw rows, topology, maintenance events) and placing it in `app/datasource` would break the layer import rule. Only the simulated adapter, which reads raw rows, lives in L1 (`app/datasource/simulated.py`). Layers must not import `app.simulation` (enforced by `tests/test_layering.py`).

## D-009 — Gate G1 approved
- **Date:** 2026-10-09 · **Status:** APPROVED by user (Mira, decision card, 2026-10-09T13:53Z)
- **Decision:** The G1 frontend demonstration is approved with all four recommended UX choices in `contracts/evidence/G1/README.md` §2: light industrial look with dark mode and ISO 3864 health colors (UNKNOWN as hatch); schematic station-plate machine map; 12-step linear studio wizard (administrator one-page editor deferred); machine state = worst known component state, UNKNOWN only when nothing is known.

## D-010 — Development authentication provider until T028
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T010; no user gate)
- **Decision:** Role checks (SEC-01 roles viewer / maintenance / engineer / admin) and audit attribution are enforced from T010 on, using a `dev` provider that trusts `X-PDM-User` / `X-PDM-Role` headers when `PDM_AUTH_MODE=dev`. Any other mode refuses requests until a real provider exists. Real authentication is delivered in T028 and is part of G4.
- **Rationale:** Lets admin-only template management and audit logging be built and tested now without inventing an identity system ahead of the deployment decisions.

## D-011 — Signal configuration is versioned as whole snapshots; the Studio saves per device
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T011; no user gate)
- **Decision:** The signal configuration (signals, mappings, groups, chart templates) is stored as immutable whole-content versions with a SHA-256 content hash; every item change and every Studio save writes the next version plus an audit row. The Studio saves one device at a time, replacing only that device's signals and the groups and charts made solely of them; group and chart ids are scoped by device. A signal id may be mapped from only one device; a clash is refused (409) rather than overwritten. The Studio previews data from the backend at full resolution and applies unsaved unit choices on screen; once saved, backend normalization is authoritative. The offline mock stays for unit tests and the static G1 demo build (`VITE_STUDIO_API=mock`).
- **Rationale:** Whole snapshots make any earlier version inspectable and restorable without replaying changes (L2-05), and per-device saves let several devices be configured from the Studio without one save silently dropping another device's mappings.

## D-012 — Quality findings are flags, storage order is part of the raw contract
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T012; no user gate)
- **Decision:** Data quality problems are reported as flags on the report (and per observation window), never corrected in the data. To detect out-of-order delivery while rows are served in time order, `RawTelemetryRow` gains an optional `arrival_seq` (simulator file order; SQL sources set `SqlTableLayout.arrival_column`, e.g. an identity id); without it OUT_OF_ORDER is reported as not evaluated. `QualityFlag` gains `BIAS_SUSPECT` for a shifted standstill torque (S16). `DataQualityReport` gains flags, spans, thresholds used, and `not_evaluated`, all optional with defaults.
- **Rationale:** AC2 of T012 requires bias and unit mismatch to be flagged, not silently corrected; and a check that cannot run must not look like a clean result.

## D-013 — Regimes are decided by speeds and cycle interval only; STOPPED/FAULT are not guessed
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T013; no user gate). To be confirmed with real data at G2.
- **Decision:** Operating regimes are learned from a user-confirmed reference period and matched on cruise speeds (one-sided: a sampled peak may fall up to 30 % short, never exceed) and the interval between actuator operations. Torque and actuator durations never define a regime; they are normalized against the matched regime's reference levels (L4-03). Running windows that fit no known regime are UNSUPPORTED and predictions must abstain. Operating state STOPPED and FAULT need a status or alarm signal and are not derived; periods without data are UNKNOWN. Actuator values equal to the controller timeout are incomplete operations without a duration; other far-off values are implausible; both are excluded from duration statistics.
- **Rationale:** If a health-bearing signal defined the regime, degradation would be absorbed as a new regime; if missing data implied STOPPED, a data outage would look like a planned stop. The sources have no recipe signal, so regimes come from observable conditions as L3-03 allows.

## D-014 — Lifecycles change only by replacement; workflows are per event and manual until T018
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T014; no user gate). Part of the G2 review.
- **Decision:** A component's first lifecycle is installed explicitly; every later lifecycle comes from a REPLACEMENT event, which retires the current one at the event time. Maintenance events are append-only and recorded in time order. Accumulated operation is added per period with a `usage_counted_until` watermark, so no period is counted twice; the simulator does not track this field and its stored datasets are unchanged. Each non-inspection event gets its own workflow; a new event supersedes the open one. Leaving REVIEW_REQUIRED needs an engineer and a review comment. Workflow steps are manual until T018 adds the stabilization and validation checks; the workflow sends no alerts.
- **Rationale:** Keeps every installation's history intact (L3-06) and makes aging impossible to reset without a replacement (L3-08), while not enabling any maintenance-alerting workflow before G4.

## D-015 — Gate G2 approved
- **Date:** 2026-10-09 · **Status:** APPROVED by user (Mira, decision card, 2026-10-09T15:32Z)
- **Decision:** G2 data and domain validation approved with assumptions A1–A5 in `contracts/evidence/G2/README.md` §2 accepted as stated. T015–T018 proceed on these semantics; A1–A3 are rechecked when real IoT data becomes available.

## D-016 — Features are per closed observation window, versioned and immutable
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T015; no user gate). Part of the G3 review.
- **Decision:** A feature vector covers one component over one closed observation window of a running machine and is computed from that window's rows only. A window still open at the extraction time is not emitted. The regime catalog used for residuals must be learned from a period ending before the extraction window. Residuals (torque at cruise, actuator duration medians) are robust distances from the matched regime's reference level and are empty without a known regime. A feature set version is immutable once registered. Stored vectors are deterministic per version and window, so saving different values for an existing window is refused. Windows overlapping maintenance or spanning a lifecycle change get no vector.
- **Rationale:** Prevents leakage of future data into features and baselines (L4-04), keeps recipe changes from looking like degradation (L4-03), and lets every later result name the exact feature version it used (GEN-06).

## D-017 — Verified healthy reference only by explicit verification; history keeps maintenance continuous
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T016; no user gate). Part of the G3 review.
- **Decision:** A VERIFIED_HEALTHY baseline is created only by an audited verification. It needs the engineer role, a comment, and a named period with at least 5 stored feature windows. It is frozen and replaced only by a later verification, and both are kept. The adaptive baseline (EWMA, alpha 0.1, restarted per lifecycle) and degradation snapshots can never become a verified reference. Degradation history is continuous across maintenance that keeps the lifecycle, and each such event is reported as a before/after step. A replacement starts a new segment, measured only against that lifecycle's own reference. A small API (`POST /api/baselines/verified`, `GET /api/components/{id}/baselines`, `GET /api/components/{id}/degradation`) exposes this for T019/T020.
- **Rationale:** L4-06 and OPT-05: drifting online data must never become "healthy" silently. Per-lifecycle references keep a new part from being judged against the worn part's history.

## D-018 — Deterministic rules on reference deviations; alarms are review records
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T017; no user gate). Part of the G3 review.
- **Decision:**
  - Statistical rules use a feature's deviation from the lifecycle's verified healthy reference (per regime where available) and fire on the median of 3 windows, so one odd window raises nothing. A sustained shift also raises WATCH through the CUSUM.
  - Safety rules check raw values against fixed limits and need no reference.
  - The rule set is versioned in code. Only enabling and disabling are configurable, and disabling a safety rule needs admin.
  - Levels rise immediately and drop only after 3 windows.
  - Alarms are raised, escalated and cleared by evaluation, and acknowledged and resolved only by people with audit. They send no notifications.
  - Machines without speed signals get regimes from operation intervals (G2 A2). Axis feature sets moved to 1.1.0 with `speed_ripple`.
- **Rationale:** Meets L4-07 and L6-03 with results that are explainable and reproducible. It keeps official alerting off until the user approves it (contract constraint).

## D-019 — Maintenance impact decides the workflow except for reviews
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T018; no user gate). Part of the G3 review.
- **Decision:** After a maintenance event, the system moves the workflow through stabilization (4 h) and validation (36 h, extended up to 120 h while comparable data is missing). It compares condition-normalized torque and actuator-duration residuals before and after, only within regimes seen on both sides. IMPROVED or NO_CHANGE closes to NORMAL_MONITORING. PARTIAL, DETERIORATED, or still UNKNOWN at the maximum goes to REVIEW_REQUIRED. Leaving REVIEW_REQUIRED remains a human step (engineer and comment, D-014). Analyses are audited and stored; no alert is sent.
- **Rationale:** L3-07 and L3-08: an effect is judged only under comparable conditions, and a doubtful outcome is always seen by a person.


## D-020 — Charts downsample on the server; bench signal for performance checks
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T019; no user gate). Part of the G3 review.
- **Decision:** The browser never receives more than 2000 points per request. `GET /api/timeseries/{signal}` returns a min/max-per-bucket downsample of the mapped signal over the requested range, keeps spikes, and turns pauses into gaps. Zooming fetches the visible range again and splices it into the overview. Every chart states whether it shows a downsample, and CSV export streams the full-resolution range (audited, file name marked `_SIMULATED` for simulated sources). Outside T019's listed scope, the datasource adapter gained `query_arrays` (array reads, with a fast simulated override) and the demo server seeds a SIMULATED 1.1M-point bench signal (`SIM-BENCH`) used only for the performance test.
- **Rationale:** L2-06 and T019 AC1/AC3: interaction stays fast on millions of rows without hiding extremes, and nobody mistakes a downsampled line for raw data.

## D-021 — Dashboard health computed on request; SIMULATED demo fleet pipeline
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T020; no user gate). Part of the G3 review.
- **Decision:**
  - `GET /api/fleet` and `GET /api/components/{id}/health` compute each component's health on request: the rules run on stored features against each lifecycle's verified reference, and the newest evaluated window of the active lifecycle decides. Health is UNKNOWN without features, without a verified reference for the current installation, while a post-maintenance validation runs, when no window could be evaluated, or when the newest evaluated window is more than 24 h older than the machine's newest window. No health value is stored.
  - The health report lists its evidence: rule hits of that window, the verified reference, open alarms and maintenance impact results, each with versions and data window.
  - The demo server replays 11 SIMULATED demo machines (A01–A08 as in T007, plus A09–A11 for S09–S11) through the real services. References are verified through the audited path by the labeled account `demo-engineer (SIMULATED)`, whose comment says it is not a real verification. Catalog and reference periods scale with the scenario's window density (S03 has 2 windows a day).
  - Alarm review in the UI: acknowledge, and resolve with a required outcome; both audited; no notifications.
  - Outside the listed scope: rule hits carry `basis` (persistent, cusum or raw) and CUSUM hits report `cusum_h` as threshold, so the reason text is truthful; the rule engine now updates its sequential statistics incrementally (same values, about 8× faster).
- **Rationale:** UI-01/02/03/09 and L6-04 on live backend results, keeping health an output (AGENTS.md) and every claim traceable to evidence.

## D-022 — G3 approved; normal aging graded in T024
- **Date:** 2026-10-09 · **Status:** APPROVED by Mira at gate G3 (decision card, 2026-10-09T22:56Z, option "批准，T024 加老化分级").
- **Decision:** G3 health interpretation and workflow behavior B1–B5 (contracts/evidence/G3/README.md §2) are accepted. T024 must grade a slow, steady drift consistent with the component's age at WATCH at most, while safety rules and abrupt or accelerating drift still escalate.
- **Rationale:** Matches the Golden Cases while the verified reference stays frozen.

## D-023 — Operator routing: role-based specs, eligibility before use, declared fallbacks
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T021; no user gate).
- **Decision:** Operators live in `app/prediction/routing`. Spec signals name roles (`torque`, `extend_time`) so one spec serves every instance of a type. The registry refuses specs whose sampling does not cover exactly the input signals, whose feature schema is unknown or belongs to another type, or that name an unknown eligibility code. Templates map each component type to independent operators; cam and gear have none (COMPONENT_TEMPLATE_ONLY). Eligibility runs before an operator; a timeout or crash applies the declared fallback (unsupported, previous version, or the statistical `deviation` operator), and the fallback's own id is kept on the result. Built-in operators: `deviation-<type>@1.0.0` (degradation indicator) and `zscore-anomaly-<type>@1.0.0` (anomaly score).
- **Rationale:** L5-01/L5-02, L6-01, GEN-07: no model output is used without its preconditions, and failures degrade to an explicit result.

## D-024 — Component models: grouped validation decides registration; all performance is simulated
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T022; no user gate).
- **Decision:** `app/prediction/models` trains a decision tree and XGBoost per component type on SIMULATED feature windows labeled from the simulator's truth (`labels.py`; health state is never a label). Lifecycle-grouped 5-fold CV is the primary measure; a time split (train < 360 h, test ≥ 384 h, 24 h embargo) is reported as optimistic. Both splits must pass `assert_no_leakage`. A model is registered only if grouped CV tested every degraded installation and produced a ROC AUC; types with fewer than 2 degraded installations (linear motor, vacuum cup) are skipped. Registry: immutable `family@version`, feature schema reference and order, SHA-256 checked before unpickling; artifacts in gitignored `backend/var/models`, report in `contracts/evidence/T022`. `TrainedModelOperator` returns uncalibrated class probabilities with the statistical fallback. Models are not added to the default templates; the cylinder models' grouped-CV recall (0.21/0.39) is too weak to rely on.
- **Rationale:** TST-03/04, L5-06; no accuracy claim beyond simulated data.

## D-025 — No CNN/LSTM: simulated data does not justify deep models
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (T023 feasibility; no user gate).
- **Decision:** CNN/LSTM is not integrated and PyTorch is not added. Telemetry is 2–6 s per-operation bursts (77–249 samples per signal per day) with no high-rate waveforms; each type has about a dozen installations with only a few degraded; T022 XGBoost already reaches grouped-CV AUC 0.966 on the ball screw and the cylinder gap is data, not capacity. Revisit with real ≥1 kHz waveforms, dozens of documented degraded installations per type and G2 A1–A3 verified. Report: `contracts/evidence/T023/feasibility.md`.
- **Rationale:** L5-04, STK-03.

## D-026 — Evidence fusion order, aging grading policy and override guard
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (implements D-022 in T024; no user gate).
- **Decision:** `app/decision/fusion.py` decides in this fixed order. (1) Preconditions: no evaluable window, no verified reference, validation running or stale data give UNKNOWN. (2) The highest SAFETY level is a floor. (3) STATISTICAL hits keep their level unless `aging.assess` grades the rule history as normal aging, which caps that hit at WATCH. Aging means: installation at least 30 days old; Theil-Sen slope of the daily median deviation at most 0.2/day over the lifetime and 0.35/day over the last 21 days; recent slope at most 2× lifetime + 0.1; the last 3 days not all more than 2.5 above the trend; deviation within 0.2/day × age + 2.5. (4) Model results are read only through `INTERPRETATION` (degradation ≥3 / <1, anomaly ≥ threshold / < half, class score ≥0.8 / ≤0.2). Failure probability and unsupported results never set a level. Models alone raise at most to WATCH; conflicts give WATCH with `conflicting_evidence`. (5) Final = max(floor, statistical). `guard` never lowers a level, ignores LLM proposals and lets a model raise NORMAL only to WATCH. Recommendation priority by level: CRITICAL→IMMEDIATE, WARNING→SOON, WATCH→PLAN (aging: next planned service), UNKNOWN→INFO; each cites evidence ids and versions (`evidence-fusion@1.0.0`, `aging-grading@1.0.0`, rules version).
- **Rationale:** L6-01..05, GEN-04, D-022. Golden match goes from 1048/1310 to 1199/1310 windows; fault scenarios S04, S07 and S19 still match every window.

## D-027 — Replay and optimization live in `app/optimization`; runs only recommend
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (scope clarification in T025; no user gate).
- **Decision:** The task scope names `core/replay`, but `core` (layer 0) may not import monitoring or decision. Replay and optimization therefore live in `app/optimization`, outside the layer ranks like `api` and `simulation`. The champion is `DEFAULT_RULES` plus `DEFAULT_POLICY`. Candidates come from bounded grids: Path A covers rule parameters and statistical thresholds; Path B covers aging grading. Safety rules are invariant (`SafetyChangeError`). Scoring uses the Golden Case suite of the SIMULATED demo fleet; a plant without Golden Cases cannot run optimization. The latest run is kept in memory and audited. A run recommends at most one challenger (more windows within, no more under) and never changes the live configuration.
- **Rationale:** OPT-01/02/04/05, TST-02, UI-10.

## D-028 — Deployment registry: admin promotion behind replay gates, engineer rollback, dev role selector
- **Date:** 2026-10-09 · **Status:** APPROVED by Principal Agent (T026; no user gate).
- **Decision:** `app/core/registry.py` stores opaque payloads per kind. The first `decision-config` champion is seeded from the configuration in use, by `system:registry`. Proposing and rejecting need engineer; promoting needs admin plus a comment plus a passed gate measured against the current champion; rolling back needs engineer (it restores an already-approved version). The decision configuration in force comes from the registry champion, falling back to the shipped defaults. Enable/disable rule settings stay keyed to the base rule set, so an admin's safety-rule decisions survive promotions. Trained models can be registered and promoted per type, but they are not yet routed into health decisions (D-024: not wired into the default templates). The UI's development role selector only changes the dev headers, until real login (T028).
- **Rationale:** OPT-03/04/06, SEC-02, UI-11.

## D-029 — Local LLM boundaries: LAN-only endpoints, no host-name resolution, advisory assistant
- **Date:** 2026-10-10 · **Status:** APPROVED by Principal Agent (T027; no user gate).
- **Decision:** Ollama is the only LLM backend. Accepted endpoints are loopback, RFC 1918 / unique-local IPs, `localhost`, and admin-listed LAN host names; names are not resolved, so a public name cannot pass through DNS. Cloud-routed model tags and registry-qualified names are refused. Settings, RAG documents and feedback are stored in tables `llm_settings`, `rag_documents`, `rag_chunks` and `feedback` (migration 0009). Settings changes and document approval need admin; adding a document needs engineer. The assistant gets the deterministic decision as read-only context, must answer in validated JSON, and is post-filtered (LLM-05). It has no tools and cannot change any state; its only output is text. A fake Ollama (simulated infrastructure) serves CI and E2E; live tests are opt-in.
- **Rationale:** STK-04, LLM-01..06, SEC-04/05, FB-01, UI-12, GEN-04.

## D-030 — LAN deployment: local accounts replace dev headers; production data stays off by configuration
- **Date:** 2026-10-10 · **Status:** APPROVED by Principal Agent (T028 security review; user acceptance at G4).
- **Decision:** `PDM_AUTH_MODE=local` is the deployment mode: accounts in `users` (migration 0010, scrypt), HMAC-signed 12 h HttpOnly SameSite=Strict cookie, account re-read per request, `X-PDM-CSRF: 1` on state-changing requests, lockout after 5 failures for 5 minutes, all audited. `dev` header auth (D-010) remains for development and tests only; `deploy/serve.py` refuses to start in any mode but `local`. LLM settings and health become admin-only (SEC-03). Non-simulated data sources are skipped unless `PDM_PRODUCTION_DATA_APPROVED=true`, which the installer never sets; no official alerting channel exists. The package is one port (API plus built client) started by a SYSTEM scheduled task, firewall limited to the local subnet. Auth code sits in `app/core` and `app/api` (outside the literal `deploy/` scope) because the security review (SR-01) could not be resolved otherwise.
- **Rationale:** STK-05, SEC-01/03/04/06, TST-01; `contracts/evidence/T028/security_review.md`.

## D-031 — G4 approved: release accepted; production data and official alerting remain off
- **Date:** 2026-10-10 · **Status:** APPROVED by user (Mira, G4 decision card, 2026-10-10T00:32:48Z, option "批准 Approve").
- **Decision:** Release 0.1.0 accepted for LAN Windows deployment with local sign-in and simulated data, including residual risks SR-07, SR-10, SR-14, SR-15. This approval does not enable a production data connection (`PDM_PRODUCTION_DATA_APPROVED` stays false) or official alerting; each still needs separate explicit approval.
- **Rationale:** ACCEPTANCE.md §G4, SEC-06.

## D-032 — Built-in read-only query templates are registered at service start
- **Date:** 2026-10-10 · **Status:** APPROVED by Principal Agent (post-deployment fix requested by Mira; no user gate).
- **Decision:** A fresh install had an empty template registry (only the e2e demo server seeded templates), so the Studio stopped at step 4. `deploy/serve.py` now calls `ensure_standard_templates`, which registers two bounded SELECT templates (key over a time range, incremental watermark read) for every loaded source that has never had a template, as `system:install`. The SQL is generated from the source's table layout and passes the same `sql_guard` checks as an administrator's template; creation is audited. Sources with any template history, including retired templates, are left alone. Production sources still load only after explicit approval (D-031).
- **Rationale:** L1-05, SEC-02, UI-04.

## D-033 — User administration and per-role module visibility
- **Date:** 2026-10-10 · **Status:** APPROVED by user request (Mira, 2026-10-10T06:53Z, item 3); design choices by Principal Agent.
- **Decision:** Administrators register accounts (no self-registration on the LAN), rename, change role, reset password, deactivate and delete them; nobody can delete, deactivate or demote themselves or the last active administrator. Table `role_modules` (migration 0011) stores the visible screens per role; a role without a row sees all twelve screens (previous behavior); the administrator role always has every screen. `/api/auth/me` returns the role's modules; the browser hides other screens and shows a no-access notice on direct links. The API enforces the same setting on module-owned endpoints (`require_module`): Studio, query templates and quality report (datasource), signal configuration writes and previews (datasource or signals), optimization, registry (models or optimization), assistant, alarm actions and feedback (alarms or assistant), maintenance records and workflow transitions. Shared monitoring reads (fleet, machines, components, time series, baselines, alarm lists, current signal configuration) stay governed by role only, because several screens depend on them. All changes are audited.
- **Rationale:** SEC-01, SEC-02.

## D-034 — Signal setup screen delivered; placeholder audit
- **Date:** 2026-10-10 · **Status:** APPROVED by Principal Agent (gap found after deployment; no user gate).
- **Decision:** T008 delivered UI-05 only inside the Studio's preview step; the `/signals` route still rendered the placeholder. `SignalsView` now lists saved signals with their mapping, lets engineers and administrators correct a signal definition (saved as a new configuration version), previews the full history downsampled plus a full-resolution quality summary of the latest stretch of data, and shows version history. A unit test now fails if any route renders the placeholder. The same audit found that the Studio's development role switch was ignored under local sign-in; the Studio now follows the signed-in role. No other screen used the placeholder. Remaining gap: query templates are managed through the admin API only; there is no template editor screen.
- **Rationale:** UI-05, ACCEPTANCE §1.

## D-035 — TDengine as the production source; simulation database for administrators only
- **Date:** 2026-10-10 · **Status:** APPROVED by the user (Mira, 2026-10-10T13:34Z: "本平台管理员权限可以使用模拟IOT采集遥测库,其余权限必须连接涛思数据库(连接生产数据库不需要管理员审批并使用只读账号)").
- **Decision:** A `TDENGINE` data source kind reads TDengine through the taosAdapter REST API with a read-only account (`secret://pdm/...` as `user:password`). TDengine sources load without `PDM_PRODUCTION_DATA_APPROVED`; generic SQL production sources keep that gate. The adapter sends only SELECT/SHOW/DESCRIBE statements it builds from validated identifiers and escaped literals; templates still pass `sql_guard`; the Studio read-only check fails for super users or accounts with write grants. Sources of kind `SIMULATED` (renamed "仿真数据库 / Simulation database") are listed and usable for administrators only; other roles get 403 `source_forbidden` and see only TDengine sources. Monitoring screens built from the labeled simulated demo fleet are unchanged. Wide (column per signal) and narrow (key column) super-table layouts are supported.
- **Risks:** not run against a real TDengine server (faked REST responses in tests); the real layout must be configured and verified.
- **Rationale:** user instruction; REQ data-source read-only rules (L1-02) kept.

## D-036 — Theme: one sun/moon toggle; scrollbars follow the theme
- **Date:** 2026-10-10 · **Status:** APPROVED by the user (same message, items 1–2).
- **Decision:** The three-way System/Light/Dark control is replaced by one button that flips the shown theme (moon on a light page, sun on a dark page); the first visit still follows the operating system. Scrollbars are styled from theme tokens (`scrollbar-color` and `::-webkit-scrollbar`) so they match light and dark pages.

## D-037 — Plant structure: workshop → process → machine, configured by administrators
- **Date:** 2026-10-10 · **Status:** APPROVED by the user (Mira, 2026-10-10T14:25Z, item 1).
- **Decision:** New `plant_nodes` table (WORKSHOP, PROCESS) and two machine columns, `process_id` and `device_id` (migration 0012). Administrators maintain the tree, create machines under a process, bind each machine to its device id in the data source (unique per machine), and maintain its components on the new admin screen "设备结构 / Plant structure"; every change is audited. Machines carry a derived `path` ("workshop / process") shown on the overview tiles, machine map header and component history crumb. In Algorithm configuration the device can be read from the database (as before, now showing the bound machine) or picked through workshop → process → machine; the machine's bound device id is what data is read with. For real sources the Components step offers the bound machine's components. Simulator datasets do not carry plant fields.
- **Rationale:** user instruction; L3-01 topology.

## D-038 — Shared drive chain: common-cause check and admin configuration
- **Date:** 2026-10-10 · **Status:** APPROVED by Principal Agent (gap found on the user's request, item 2).
- **Finding:** `drive_chain_id` existed in the topology and the machine map drew the link, but nothing used it: S19 expects evidence fusion to point to the shared drive chain instead of separate ball-screw wear, and only the health levels were checked. There was also no screen to set components or drive chains (API `PUT /components` for engineers only).
- **Decision:** When two or more components on one drive chain are WARNING or CRITICAL at the same time, the fleet overview and component report carry `common_cause` (drive chain, members, bilingual note to check the chain first). Health states are unchanged. Components and drive-chain ids are configured on the Plant structure screen (administrators only), not in the Algorithm configuration flow or Signal setup: drive chains are machine topology, independent of which signals are mapped, and the Algorithm configuration's Components step reads them from there.
- **Verification:** S19 replay: both chained ball screws report the shared cause; no other demo machine does.

## D-039 — "Data Source Studio" renamed "算法配置 / Algorithm configuration"
- **Date:** 2026-10-10 · **Status:** APPROVED by the user (item 3). Route `/datasource` and module key `datasource` are unchanged so saved role-module settings keep working.

## D-040 — Algorithm fixes from the review: aging ceiling and reference quality notes
- **Date:** 2026-10-11 · **Status:** APPROVED by the user (Mira, 2026-10-11T15:40Z, "针对以上缺陷进行优化"; the review is `/mnt/project-files/analysis/algorithm-review/`). Amends D-022 (G3).
- **Finding:** aging grading capped a statistical hit at WATCH whatever its level, so a slow drift far above the CRITICAL threshold (deviation 30 on day 200 against 25) stayed WATCH. A healthy reference chosen while the component was already degrading (S12, S09, S11, S03) hid that degradation, and nothing warned the engineer.
- **Decision:** (1) Aging grading applies to WARNING hits only; CRITICAL is never lowered. (2) Verifying a reference computes notes, stored with it and shown on the Baselines screen: a Theil-Sen drift inside the period of 1.5 spreads or more on the component's main rule feature, and fewer than 10 windows. Notes never block the verification. (3) The Baselines screen can verify a reference (engineer), using `GET /components/{id}/feature-coverage`.
- **Verification:** replay of the SIMULATED demo fleet: 1196/1310 windows within allowed levels (was 1199; 3 S03 windows at the late abrupt step now stay CRITICAL). Drift notes flag the references of A02, A03, A05, A09 and A11 and none of the clean ones.

## D-041 — Torque limit per component enables SF-TORQUE-LIMIT
- **Date:** 2026-10-11 · **Status:** APPROVED by the user (same message).
- **Finding:** `evaluate(limits=...)` was never given limits, so the only torque safety rule never ran.
- **Decision:** `ComponentInstance.torque_limit` (migration 0013; unit of the component's torque signal; set by an administrator on the plant screen) is passed to every evaluation (dashboard, alarms, pipeline). Without a limit the rule stays "not evaluated", as before. No limit is set for demo components, so demo results do not change. The safety thresholds themselves are unchanged.

## D-042 — Online feature pipeline
- **Date:** 2026-10-11 · **Status:** APPROVED by the user (same message).
- **Finding:** regime learning and feature extraction ran only in the demo replay, so a real source never produced features.
- **Decision:** `app/decision/pipeline.py` learns the regime catalog from the first 4 days after the first installation, reads the data after the newest stored window in 24 h steps, stores closed windows, and syncs alarms; a window still open is left for the next run, and a rerun with no new data changes nothing. `POST /api/pipeline/run` (engineer) runs one machine; `deploy/serve.py` runs all machines every `PDM_PIPELINE_INTERVAL_MIN` minutes (default 15, 0 = off). The health reference still needs an engineer's verification, so components without one stay UNKNOWN and are listed in the run result.
- **Risks:** never run against a real TDengine source. The regime catalog is learned once from the first 4 days, so a machine whose first days are not representative needs a longer period (`catalog_days`, not yet configurable in the UI).


## D-043 — Unified evidence object and three-state safety result
- **Date:** 2026-10-14 · **Status:** APPROVED by the user (Mira, 2026-10-14T13:19Z, card "同意P1"; requirements §4.2–§4.4 of her workbench redesign message). Changes the G3-approved fusion semantics for unmeasurable safety checks.
- **Finding:** a safety rule whose measurement was missing or invalid was only listed in `not_evaluated`; with no other hit the component showed NORMAL, so "cannot confirm a violation" read as "confirmed normal".
- **Decision:** (1) `Evidence` gains `component_id`, `evidence_type` (SAFETY, STATISTICAL, ANOMALY, SUPERVISED, CONTEXT), `raw_value`, `threshold`, `calibration`, `proposed_severity`, `quality_status`, `baseline_version`; `applicable`, `reason`, `model_version`, `evaluated_at`, `input_window_id` are derived from stored fields. (2) The rule engine reports each safety check as VIOLATED, NOT_EVALUATED (measurement missing or invalid), CONFIRMED_OK or NOT_CONFIGURED (no limit set, not a failure). (3) A NOT_EVALUATED check adds non-applicable INVALID evidence, a reason, and an open WATCH alarm `DQ:<rule>` ("safety monitoring degraded"); with nothing else abnormal the component is UNKNOWN, never NORMAL; a statistical WARNING or CRITICAL is kept and the gap is still listed. A held violation stays a violation. `Decision.safety_status` and `safety_unevaluated` carry the result.
- **Not yet done (later phases):** admin-configurable evidence eligibility, fusion method and confidence calculation; the screen for these.
- **Risks:** quality is derived from the feature being absent, not from the quality report itself; feature extraction still skips a whole window with no usable signal, which then produces no evaluation and no gap.

## D-044 — Data sources managed in the application; prediction configuration versions
- **Date:** 2026-10-14 · **Status:** APPROVED by the user (Mira, 2026-10-14T13:35Z, "继续 P2"; requirements §2 steps 2 and 7).
- **Decision:** (1) Administrators create, edit, test and delete TDengine sources (`/api/admin/datasources`, table `managed_datasources`, migration 0014). The account (`<user>:<password>`) is write-only: it is written to the server's protected `backend\.env` as `PDM_SECRET_<ID>` (file rewritten in place so its permissions stay) and never returned or stored in the database. A layout counts as verified only after a test against the real database. File-defined sources stay read-only; a source used by signal mappings cannot be deleted. (2) Prediction configuration versions per component (`prediction_configs`, migration 0015): relationships, decision pipeline, criteria and display. Life cycle DRAFT → VALIDATED (data, compile, replay, synthetic-scenario checks all pass) → PUBLISHED (immutable, content hash, comment required), one ACTIVE version per component. An edit voids validation; a published version is cloned, never edited. The safety-first rule cannot be switched off. Every action is audited.
- **Honest limits:** the decision engine does not read the active configuration yet (next phase), so activating a version records the decision but does not change verdicts. The simulation check runs synthetic windows through the decision logic and says nothing about plant data. Algorithms without an implementation (Mahalanobis/T², LSTM, D-RCNN) are listed but never enabled; XGBoost and decision-tree stages stay disabled until a validated model is deployed. Never run against a real TDengine; the tests use a fake server.

## D-045 — The decision engine reads the active prediction configuration; Hotelling T²; relationships
- **Date:** 2026-10-14 · **Status:** APPROVED by the user (Mira, 2026-10-14T13:45Z, "继续 P3"; requirements §3.3, §4.2, §2 step 3). Builds on D-044.
- **Decision:** (1) A component with an ACTIVE configuration is evaluated with it: evidence types not in `allowed_evidence_types` stay in the trail as not applicable and no longer decide (SAFETY can never be excluded; models and unsupervised detectors raise at most WATCH). A component without one behaves as before. (2) `mahalanobis-t2` is implemented: Hotelling T² of the newest windows against the verified healthy reference windows (shrunk covariance, F-based limit at α = 0.001, anomalous only on two consecutive windows, not evaluated with fewer than max(15, 3 × features) reference windows). It needs no fault labels and appears as ANOMALY evidence. It runs only when the active configuration has the stage; replay and optimisation scoring are unchanged. (3) Relationships (shared drivetrain, mechanical dependency, shared signal) with `affects_common_cause` produce a common-cause note when the component and a related one are WARNING or CRITICAL; a drive-chain cause takes precedence. `affects_status_display` returns the related components' health in the report; the report also carries the active version and the display settings.
- **Risks:** T² uses the first feature of each statistical rule and has been checked only on simulated data. Relationship notes cover components in the configuration's member list only.

## D-046 — Algorithm matching, plugins and the deep sequence model interface (LSTM, D-RCNN)
- **Date:** 2026-10-14 · **Status:** APPROVED by the user (Mira, 2026-10-14T13:49Z: integrate the LSTM/D-RCNN interface so users can train, fine-tune and optimise later). Builds on D-044.
- **Decision:** (1) `GET /components/{id}/recommended-config` proposes a pipeline matched to the component type and its mapped signals (requirements §3.1) with the type's constraints, and compiles it. (2) `prediction/models/deep.py`: `DeepModelAdapter` (input contract for window sequences or raw waveforms, `fit` for training and fine-tuning from a stored base model, `predict_degraded`, `search_space`), `train_deep`, `tune`, `DeepModelOperator` for routing. Gates as for the tree models: recorded-truth labels only, installations never split between training and validation, ROC AUC ≥ 0.8, enough labelled samples, immutable hash-checked storage, and the existing deployment gate before a model decides anything. LSTM and D-RCNN are registered as placeholders that report "no backend adapter" and never train or predict; no deep learning framework is bundled. A real backend is added by registering an adapter with `register_adapter(..., replace=True)`. `GET /deep-model-adapters` lists the status. (3) `decision/plugins.py`: standard contract and semantic versions for custom algorithms, immutable versions, a contract self-test at registration, at most WATCH, no safety or context evidence, registered by code on the server only.
- **Not yet done:** the decision engine does not consume plugin evidence or run deep models (a plugin stage compiles as not taking part); the new component types of requirements §3.1 (servo as its own type, suction cup beyond the vacuum cup, vibration components, custom) need feature sets and are later work. Exercised with a numpy test double only; no real LSTM or D-RCNN has been run.
