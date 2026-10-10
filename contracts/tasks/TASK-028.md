# TASK-028 — Windows/LAN deployment and final acceptance

- **ID:** T028
- **Status:** IN_PROGRESS
- **Phase:** 7 — Release
- **Gate:** G4 (approval requested after this task)

## Goal

Package for Windows server LAN deployment, complete security review, and run final acceptance.

## Dependencies

T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021, T022, T023, T024, T025, T026, T027

## Allowed Scope

- deploy/
- security review
- acceptance evidence

Anything outside this list requires Principal Agent approval.

## Related Requirements

STK-05, SEC-01, SEC-03, SEC-04, SEC-06, TST-01

## Acceptance Criteria

1. Services install and start on Windows; browser clients on LAN need no install.
2. Security review completed with findings resolved or accepted.
3. End-to-end acceptance evidence for all G4 items.
4. Production data connection and official alerting remain disabled until explicit user approval.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- Deployment log
- full test suite
- security review report

## Deliverables

- Deployment package
- G4 acceptance package (bilingual)

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
