# TASK-006 — UI design system and bilingual switching

- **ID:** T006
- **Status:** TODO
- **Phase:** 2 — High-Fidelity Frontend
- **Gate:** None

## Goal

Build the industrial design system (tokens, layout, core components) and runtime zh/en switching.

## Dependencies

T002

## Allowed Scope

- frontend/src/theme, frontend/src/components/base, frontend/src/i18n, app shell and navigation

Anything outside this list requires Principal Agent approval.

## Related Requirements

UI-13, GEN-05, STK-01

## Acceptance Criteria

1. Design tokens for health colors (NORMAL/WATCH/WARNING/CRITICAL/UNKNOWN), typography, spacing, motion.
2. App shell with navigation for all 12 interfaces (placeholder routes allowed).
3. zh-CN/en-US switch without reload; no hard-coded user-facing strings (lint/test check).
4. Simulated-data badge component.
5. Responsive at desktop and tablet widths; keyboard focus visible.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- vitest (i18n completeness, components)
- Playwright screenshot zh and en

## Deliverables

- Design system
- i18n setup
- Screenshots in contracts/evidence/T006/

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
