"""Local Ollama assistant, RAG documents and feedback (T027, UI-12, FB-01).

Settings: read needs viewer, change needs admin. Asking needs viewer. Documents: add needs engineer,
approve (which embeds them locally) needs admin, reading follows each document's minimum role.
Feedback: submit needs maintenance, review needs engineer. When Ollama is off or unreachable the
assistant answers 503; nothing else in the platform depends on it (GEN-04).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.schemas import ContractModel
from app.core.security import Principal, Role, require
from app.feedback.service import FeedbackIn, FeedbackItem, FeedbackService
from app.llm.assistant import Assistant, AssistantRequest, AssistantResponse
from app.llm.client import LlmUnavailable, OllamaClient
from app.llm.rag import Document, DocumentIn, DocumentStore
from app.llm.settings import LlmConfig, LlmConfigState, LlmSettings

router = APIRouter(tags=["assistant"])
DB = Annotated[Session, Depends(get_session)]
Viewer = Annotated[Principal, Depends(require(Role.VIEWER))]
Maintainer = Annotated[Principal, Depends(require(Role.MAINTENANCE))]
Engineer = Annotated[Principal, Depends(require(Role.ENGINEER))]
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]  # SEC-03: endpoint and model settings
_CANCEL: dict[str, threading.Event] = {}


class LlmHealth(ContractModel):
    enabled: bool
    reachable: bool
    endpoint: str
    version: str | None
    models: list[str]
    chat_model_installed: bool
    embed_model_installed: bool
    detail: str = ""


class Review(ContractModel):
    note: str = Field(default="", max_length=2000)


def _client(cfg: LlmConfig) -> OllamaClient:
    return OllamaClient(cfg.endpoint, cfg.allowed_hosts, cfg.timeout_s)


@router.get("/llm/settings", response_model=LlmConfigState)
def get_settings_(_: Admin, db: DB) -> LlmConfigState:
    return LlmSettings(db).current()


@router.put("/llm/settings", response_model=LlmConfigState)
def put_settings(body: LlmConfig, who: Admin, db: DB) -> LlmConfigState:
    return LlmSettings(db).update(body, who)


@router.get("/llm/health", response_model=LlmHealth)
def health(_: Admin, db: DB) -> LlmHealth:
    cfg = LlmSettings(db).current().config
    client = _client(cfg)
    try:
        version, models = client.version(), client.models()
    except LlmUnavailable as e:
        return LlmHealth(
            enabled=cfg.enabled,
            reachable=False,
            endpoint=cfg.endpoint,
            version=None,
            models=[],
            chat_model_installed=False,
            embed_model_installed=False,
            detail=str(e),
        )
    finally:
        client.close()
    return LlmHealth(
        enabled=cfg.enabled,
        reachable=True,
        endpoint=cfg.endpoint,
        version=version,
        models=models,
        chat_model_installed=cfg.chat_model in models,
        embed_model_installed=cfg.embed_model in models,
    )


@router.post("/llm/ask", response_model=AssistantResponse)
def ask(body: AssistantRequest, who: Viewer, db: DB) -> AssistantResponse:
    cfg = LlmSettings(db).current().config
    client = _client(cfg)
    try:
        return Assistant(db, cfg, client).ask(body, who)
    finally:
        client.close()


@router.post("/llm/ask/stream")
def ask_stream(body: AssistantRequest, who: Viewer, db: DB) -> StreamingResponse:
    """Newline-delimited JSON events; cancel with POST /llm/ask/{request_id}/cancel or by disconnecting."""
    cfg = LlmSettings(db).current().config
    client = _client(cfg)
    assistant = Assistant(db, cfg, client)
    cancel = threading.Event()
    if body.request_id:
        _CANCEL[body.request_id] = cancel

    def events() -> Iterator[bytes]:
        try:
            for ev in assistant.stream(body, who, cancel):
                yield (json.dumps(ev, ensure_ascii=False) + "\n").encode()
        finally:
            client.close()
            if body.request_id:
                _CANCEL.pop(body.request_id, None)

    return StreamingResponse(events(), media_type="application/x-ndjson")


@router.post("/llm/ask/{request_id}/cancel", status_code=204)
def cancel(request_id: str, _: Viewer) -> None:
    ev = _CANCEL.get(request_id)
    if ev is not None:
        ev.set()


@router.get("/llm/documents", response_model=list[Document])
def documents(who: Viewer, db: DB) -> list[Document]:
    return DocumentStore(db).documents(who)


@router.post("/llm/documents", response_model=Document)
def add_document(body: DocumentIn, who: Engineer, db: DB) -> Document:
    return DocumentStore(db).add(body, who)


@router.post("/llm/documents/{doc_id}/approve", response_model=Document)
def approve_document(doc_id: str, who: Engineer, db: DB) -> Document:
    cfg = LlmSettings(db).current().config
    client = _client(cfg)
    try:
        return DocumentStore(db).approve(doc_id, who, client, cfg.embed_model)
    finally:
        client.close()


@router.post("/feedback", response_model=FeedbackItem)
def submit_feedback(body: FeedbackIn, who: Maintainer, db: DB) -> FeedbackItem:
    return FeedbackService(db).submit(body, who)


@router.get("/feedback", response_model=list[FeedbackItem])
def list_feedback(
    _: Viewer, db: DB, status: str | None = None, alarm_id: str | None = None
) -> list[FeedbackItem]:
    return FeedbackService(db).items(status, alarm_id)


@router.post("/feedback/{feedback_id}/review", response_model=FeedbackItem)
def review_feedback(feedback_id: str, body: Review, who: Engineer, db: DB) -> FeedbackItem:
    return FeedbackService(db).review(feedback_id, body.note, who)
