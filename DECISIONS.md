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
