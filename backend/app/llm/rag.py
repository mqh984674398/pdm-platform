"""Local RAG over approved documents with citations (LLM-03, SEC-05).

Documents are added by engineers and are not searchable until an administrator approves them; each
document names the lowest role that may read it. Approval chunks the text and embeds the chunks with
the local Ollama embedding model. Retrieval only returns approved chunks the caller may read.
Retrieved text is untrusted: it is quoted to the model as data, never executed or obeyed.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from pydantic import AwareDatetime, Field
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.schemas import ContractModel
from app.core.security import Principal, Role
from app.llm.client import OllamaClient

CHUNK_CHARS = 700


class DocumentError(ValueError):
    pass


class DocumentNotFoundError(KeyError):
    pass


class DocumentPermissionError(PermissionError):
    pass


class DocumentIn(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)
    min_role: Role = Role.VIEWER
    source: str = Field(default="", max_length=500)


class Document(ContractModel):
    doc_id: str
    title: str
    min_role: Role
    source: str
    approved: bool
    added_by: str
    added_at: AwareDatetime
    approved_by: str | None
    chunks: int


class Citation(ContractModel):
    chunk_id: str
    doc_id: str
    title: str
    excerpt: str
    score: float


class DocumentRecord(Base):
    __tablename__ = "rag_documents"

    doc_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    min_role: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    added_by: Mapped[str] = mapped_column(String(64), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ChunkRecord(Base):
    __tablename__ = "rag_chunks"

    chunk_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(JSON, nullable=False)
    embed_model: Mapped[str] = mapped_column(String(120), nullable=False)


def chunk(text: str, size: int = CHUNK_CHARS) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > size:
            out.append(p[:size])
            p = p[size:]
        if cur and len(cur) + len(p) + 2 > size:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def _cos(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb) if na and nb else 0.0


class DocumentStore:
    def __init__(self, session: Session):
        self.session = session

    def _model(self, r: DocumentRecord) -> Document:
        n = len(
            self.session.scalars(select(ChunkRecord.chunk_id).where(ChunkRecord.doc_id == r.doc_id)).all()
        )
        at = r.added_at if r.added_at.tzinfo else r.added_at.replace(tzinfo=UTC)
        return Document(
            doc_id=r.doc_id,
            title=r.title,
            min_role=Role(r.min_role),
            source=r.source,
            approved=r.approved,
            added_by=r.added_by,
            added_at=at,
            approved_by=r.approved_by,
            chunks=n,
        )

    def documents(self, who: Principal) -> list[Document]:
        rows = self.session.scalars(select(DocumentRecord).order_by(DocumentRecord.added_at)).all()
        return [self._model(r) for r in rows if who.at_least(Role(r.min_role))]

    def add(self, doc: DocumentIn, who: Principal) -> Document:
        if not who.at_least(Role.ENGINEER):
            raise DocumentPermissionError("adding a document requires an engineer")
        n = len(self.session.scalars(select(DocumentRecord.doc_id)).all()) + 1
        row = DocumentRecord(
            doc_id=f"DOC-{n:04d}",
            title=doc.title,
            text=doc.text,
            min_role=doc.min_role.value,
            source=doc.source,
            approved=False,
            added_by=who.user_id,
            added_at=datetime.now(UTC),
        )
        self.session.add(row)
        audit(
            self.session,
            who,
            "rag.add",
            "rag_document",
            row.doc_id,
            title=doc.title,
            min_role=doc.min_role.value,
        )
        self.session.commit()
        return self._model(row)

    def approve(self, doc_id: str, who: Principal, client: OllamaClient, embed_model: str) -> Document:
        if not who.at_least(Role.ADMIN):
            raise DocumentPermissionError("approving a document requires an administrator")
        row = self.session.get(DocumentRecord, doc_id)
        if row is None:
            raise DocumentNotFoundError(doc_id)
        if not embed_model:
            raise DocumentError("no embedding model is configured")
        parts = chunk(row.text)
        vecs = client.embed(embed_model, parts)
        for old in self.session.scalars(select(ChunkRecord).where(ChunkRecord.doc_id == doc_id)):
            self.session.delete(old)
        for i, (t, v) in enumerate(zip(parts, vecs, strict=True)):
            self.session.add(
                ChunkRecord(
                    chunk_id=f"{doc_id}#{i + 1}",
                    doc_id=doc_id,
                    seq=i + 1,
                    text=t,
                    embedding=v,
                    embed_model=embed_model,
                )
            )
        row.approved, row.approved_by = True, who.user_id
        audit(
            self.session,
            who,
            "rag.approve",
            "rag_document",
            doc_id,
            chunks=len(parts),
            embed_model=embed_model,
        )
        self.session.commit()
        return self._model(row)

    def search(
        self, query_vec: list[float], who: Principal, k: int = 4, embed_model: str = ""
    ) -> list[Citation]:
        docs = {
            r.doc_id: r
            for r in self.session.scalars(select(DocumentRecord).where(DocumentRecord.approved.is_(True)))
            if who.at_least(Role(r.min_role))
        }
        scored = []
        for c in self.session.scalars(select(ChunkRecord).where(ChunkRecord.doc_id.in_(list(docs)))):
            if embed_model and c.embed_model != embed_model:
                continue
            scored.append((_cos(query_vec, c.embedding), c))
        scored.sort(key=lambda t: -t[0])
        return [
            Citation(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                title=docs[c.doc_id].title,
                excerpt=c.text,
                score=round(s, 4),
            )
            for s, c in scored[:k]
            if s > 0
        ]
