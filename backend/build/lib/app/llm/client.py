"""Ollama HTTP client: health, installed models, chat (streaming, timeout, cancellation), embeddings.

The endpoint is validated on construction (local/LAN only). The HTTP transport can be injected, so CI
runs against a mocked Ollama (LLM-06). Errors are typed so callers can degrade instead of failing.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Collection, Iterator
from typing import Any

import httpx

from app.llm.endpoint import validate_endpoint


class LlmError(RuntimeError):
    pass


class LlmUnavailable(LlmError):
    """Ollama cannot be reached or answered with an error."""


class LlmTimeout(LlmError):
    pass


class LlmCancelled(LlmError):
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        allowed_hosts: Collection[str] = (),
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = validate_endpoint(base_url, allowed_hosts)
        self.timeout_s = timeout_s
        self.http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_s, connect=5.0),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self.http.request(method, path, **kw)
        except httpx.TimeoutException as e:
            raise LlmTimeout(f"Ollama did not answer within {self.timeout_s:g} s") from e
        except httpx.HTTPError as e:
            raise LlmUnavailable(f"Ollama is not reachable at {self.base_url}") from e
        if r.status_code >= 300:
            raise LlmUnavailable(f"Ollama answered {r.status_code} for {path}")
        return r

    def version(self) -> str:
        return str(self._req("GET", "/api/version").json().get("version", "unknown"))

    def models(self) -> list[str]:
        return sorted(m["name"] for m in self._req("GET", "/api/tags").json().get("models", []))

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema: dict | None = None,
        options: dict | None = None,
    ) -> str:
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if schema is not None:
            body["format"] = schema
        if options:
            body["options"] = options
        return self._req("POST", "/api/chat", json=body).json()["message"]["content"]

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        cancel: threading.Event | None = None,
        schema: dict | None = None,
    ) -> Iterator[str]:
        """Yield content pieces as they arrive; stop when ``cancel`` is set (raises LlmCancelled)."""
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if schema is not None:
            body["format"] = schema
        try:
            with self.http.stream("POST", "/api/chat", json=body) as r:
                if r.status_code >= 300:
                    raise LlmUnavailable(f"Ollama answered {r.status_code} for /api/chat")
                for line in r.iter_lines():
                    if cancel is not None and cancel.is_set():
                        raise LlmCancelled("cancelled by the user")
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    piece = msg.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if msg.get("done"):
                        return
        except httpx.TimeoutException as e:
            raise LlmTimeout(f"Ollama did not answer within {self.timeout_s:g} s") from e
        except httpx.HTTPError as e:
            raise LlmUnavailable(f"Ollama is not reachable at {self.base_url}") from e

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        out = self._req("POST", "/api/embed", json={"model": model, "input": texts}).json()
        vecs = out.get("embeddings")
        if not isinstance(vecs, list) or len(vecs) != len(texts):
            raise LlmUnavailable("Ollama returned no embeddings")
        return vecs

    def close(self) -> None:
        self.http.close()
