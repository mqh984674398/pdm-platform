# TASK-006 — UI design system and bilingual switching

- **ID:** T006
- **Status:** DONE
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

2026-10-09:

- `tools/ci_local.sh` → exit 0 (log `contracts/evidence/T006/ci_local.log`): Vitest 11 passed, vue-tsc clean, eslint/prettier clean, build OK, Playwright 1 passed; backend 60 passed on 3.11/3.12.
- AC1: tokens in `frontend/src/theme/tokens.css` (health colors per ISO 3864 conventions; UNKNOWN rendered as a hatch meaning "no evidence"), typography (bundled IBM Plex Sans for offline LAN use, CJK via system fonts), spacing, motion with reduced-motion support; light/dark/system themes.
- AC2: app shell with all 12 interfaces in the navigation (`app.spec.ts` checks 12 routes); placeholders name the delivering task.
- AC3: runtime zh-CN/en-US switch (`app.spec.ts` switches without remount; E2E asserts no page reload via a window marker); `i18n.spec.ts` checks identical key sets and scans every `.vue` template for hard-coded text (negative probe confirmed it fails on raw text).
- AC4: `SimBadge` component (dashed violet plate with warning glyph).
- AC5: screenshots at 1280 px and 820 px (tablet; sidebar becomes an overlay), visible `:focus-visible` ring. Evidence: `design-zh-light.png`, `design-en-dark.png`, `datasource-en-light.png`, `tablet-zh-light.png`.
- Design reference page at `/_design` (not in navigation).
- Tools used: frontend-design skill (design direction), Playwright (screenshots/E2E).
