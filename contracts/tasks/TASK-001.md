# TASK-001 — Repository audit and Contract setup

- **ID:** T001
- **Status:** DONE
- **Phase:** 1 — Contracts and Simulation
- **Gate:** None

## Goal

Audit the repository and establish the contract files that govern all later tasks.

## Dependencies

None

## Allowed Scope

- AGENTS.md, REQUIREMENTS.md, ARCHITECTURE.md, TASKS.md, ACCEPTANCE.md, DECISIONS.md
- contracts/CURRENT_TASK.md, contracts/tasks/TASK-001..028.md, contracts/audit/
- tools/check_contracts.py and README.md, .gitignore

Anything outside this list requires Principal Agent approval.

## Related Requirements

GEN-01, GEN-02

## Acceptance Criteria

1. Repository audit recorded in contracts/audit/T001-repository-audit.md (existing code, tooling, gaps).
2. All six contract documents exist with no competing task registry.
3. Exactly 28 task files exist, each with Goal, Dependencies, Allowed Scope, Related Requirements, Acceptance Criteria, Required Verification, Deliverables, Failure Recovery.
4. Every dependency references an existing task and the dependency graph is acyclic.
5. Every cited requirement ID exists in REQUIREMENTS.md.
6. CURRENT_TASK.md points at the next assigned task after T001 is DONE.
7. Files are committed to the project repository.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `python tools/check_contracts.py (exit 0)`

## Deliverables

- Contract documents
- 28 task files
- Audit report
- Contract checker

## Failure Recovery

If the repository already contains conflicting registries, do not delete them: record them in the audit and escalate.

## Evidence

- 2026-10-09 `python3 tools/check_contracts.py` → `checked 28 tasks, 94 requirement IDs: OK`, exit 0.
- 2026-10-09 negative test on a copy (removed a section, added unknown requirement ID) → 2 errors reported, exit 1.
- Audit: `contracts/audit/T001-repository-audit.md`.
- Criterion 7: committed to the local project git repository (commit "T001: contract setup"). The GitHub remote is not configured yet; push is pending GitHub access. Durable copy: `/mnt/project-files/repo/` plus git bundle `/mnt/project-files/repo-bundle/pdm.bundle`.
