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

