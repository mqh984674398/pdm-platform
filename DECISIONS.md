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
