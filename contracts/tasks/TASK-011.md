# TASK-011 — Signal mapping and preview APIs

- **ID:** T011
- **Status:** DONE
- **Phase:** 3 — Backend and Industrial Domain
- **Gate:** None

## Goal

Implement signal registry, mapping, grouping, viz templates, versioning, and preview APIs; connect Studio to them.

## Dependencies

T010

## Allowed Scope

- backend/app/signals
- API endpoints
- frontend Studio switched from mocks to API

Anything outside this list requires Principal Agent approval.

## Related Requirements

L2-01, L2-02, L2-03, L2-04, L2-05, UI-04, UI-05

## Acceptance Criteria

1. CRUD for signal definitions, mappings, groups; every change creates a config version.
2. Preview returns normalized and downsampled series separately.
3. Studio E2E works against the real backend with the simulated adapter.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/signals`
- Playwright E2E

## Deliverables

- Signal registry and APIs

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

Executed 2026-10-09 by the executing agent.

### Commands and results

- `PDM_TEST_PG_URL=… pytest -v tests/signals`: **29 passed** (application database on PostgreSQL 16.15; the same suite also passes on SQLite). Log: `contracts/evidence/T011/pytest_signals.log`.
- Playwright E2E (`npm run test:e2e`): **5 passed**. The two Studio tests now run against the real backend (`backend/scripts/demo_server.py`: fresh SQLite demo database, simulated source `sim-iot` from `Data/fixtures/studio_sources.json`, the two query templates registered through the audited template registry). The workflow test finishes by reading `/api/signal-config` and confirming the four SIM-S13 signals, mappings, and the chosen HISTOGRAM chart were stored as version 1.
- Alembic on PostgreSQL: upgrade head → downgrade 0001 → upgrade head → downgrade base, all clean.
- `tools/ci_local.sh` with PostgreSQL enabled: rc=0. Backend 220 passed on Python 3.11 and 3.12 (ruff clean), frontend 32 unit and 5 end-to-end tests, typecheck/lint/build clean, schema drift OK. Log: `contracts/evidence/T011/ci_local.log`.

### Acceptance criteria

1. CRUD with a version per change: `PUT`/`DELETE /api/signal-config/{signals|mappings|groups|visualizations}/{id}` and the Studio's per-device save `PUT /api/signal-config/sources/{src}/devices/{device}` each write a new immutable version (content + SHA-256 hash) and an audit row. Invariants (defined signals, unique ids and device keys, conversion target = signal unit), stale `base_version`, and no-op changes are refused with 409 and nothing is saved. Tests: `test_config_api.py` (10).
2. Preview separates the two series: `POST /api/signals/preview` (drafts) and `GET /api/signals/{id}/preview` (saved) return `normalized` (every source row, converted, OUT_OF_RANGE/MISSING flags, `truncated` when the bounded read hit its limit) and `visualization` (LTTB, gap-aware, `downsampled`, `source_point_count`). Tests: `test_preview.py` (8), `test_downsample.py` (3), on the simulated source and on a SQL source.
3. Studio E2E against the real backend: the Studio uses `src/api/studioHttp.ts` by default (connection checks, layout, devices, suggestions, templates, preview, versions, save). The offline mock remains only for unit tests and the static G1 demo (`VITE_STUDIO_API=mock`). Tests: `tests/e2e/studio.spec.ts`, `tests/unit/studioHttp.spec.ts`; Studio support endpoints in `test_studio_api.py` (8).

Decision recorded: D-011 (whole-snapshot versions, per-device Studio saves, device-scoped group ids).

### Scope notes

Outside the literal Allowed Scope, needed for AC3 and kept minimal:
- `app/datasource/simulated.py`: one simulated source can span several datasets (device ids must not overlap); `row_counts()`.
- `app/datasource/query_service/sources.py`: `simulated_datasets` entries with optional preview windows; `SimulatedDataset` descriptors (scenario title, topology) for Studio suggestions.
- `app/api/query.py`, `query_service/service.py`: templates may be registered for simulated sources (table allowlist from any adapter); they still run only on SQL sources.
- `app/simulation/studio_fixture.py`: also writes `Data/fixtures/studio_sources.json`; template SQL now names the simulated table `raw_telemetry`. Fixture checksums regenerated (only these two files changed).
- Alembic migration `0002_signal_config_versions`; `backend/scripts/demo_server.py`; Playwright starts the demo backend; CI frontend job installs the backend.

### Risks

- The Studio's quality step still uses the UI-side summary over the backend's time-ordered rows, so arrival-order faults (S14 out-of-order) are not visible there; the L4 quality service in T012 replaces it.
- Signal ids from the simulator topology repeat across scenario devices (all machines are "M01"); after one device is saved, the same topology ids are not suggested for another device and those keys start unnamed. Real deployments name signals per machine.
- Dev authentication (D-010) still applies; the Studio sends engineer/admin headers.
