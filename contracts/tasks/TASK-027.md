# TASK-027 — Ollama-only LLM, local RAG, and feedback

- **ID:** T027
- **Status:** IN_PROGRESS
- **Phase:** 6 — Optimization and Local LLM
- **Gate:** None

## Goal

Implement the local Ollama gateway, RAG with citations, diagnostic assistant, and feedback.

## Dependencies

T020, T024

## Allowed Scope

- backend/app/llm, app/feedback
- Ollama config and assistant views

Anything outside this list requires Principal Agent approval.

## Related Requirements

STK-04, LLM-01, LLM-02, LLM-03, LLM-04, LLM-05, LLM-06, SEC-04, SEC-05, FB-01, UI-12, GEN-04

## Acceptance Criteria

1. Remote/cloud endpoints and cloud-routed models rejected (tests).
2. Streaming, timeout, cancellation, structured validation against mocked Ollama.
3. RAG answers cite approved documents; authorization enforced.
4. Platform monitoring and alarms work with Ollama down (test).
5. Live tests opt-in only.

Global Definition of Done in ACCEPTANCE.md §1 also applies.

## Required Verification

- `pytest tests/llm (mocked)`
- opt-in live test log

## Deliverables

- LLM gateway, RAG, assistant

## Failure Recovery

Revert the task branch to the last green commit; record the failure and cause in the task Evidence section; set status FAILED and notify the Principal Agent if the fix needs changes outside Allowed Scope.

## Evidence

_Filled in by the executing agent with actual commands and results._
