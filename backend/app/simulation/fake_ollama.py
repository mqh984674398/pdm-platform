"""Deterministic stand-in for a local Ollama server (LLM-06): used by CI tests and the E2E demo.

It implements /api/version, /api/tags, /api/chat (streaming and not) and /api/embed. Embeddings are
hashed bags of words, so retrieval is meaningful. Chat answers in the required JSON, citing the first
document in the prompt and repeating the platform's health state. Test triggers in the question:
``probability`` (answer states a failure probability), ``badjson`` (not JSON), ``cite-unknown``
(cites a chunk that was not retrieved), ``slow`` (sleeps ``slow_s`` between stream pieces).
This is simulated infrastructure, not a model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time

import httpx

MODELS = ["qwen2.5:7b-instruct", "nomic-embed-text:latest", "gpt-oss:120b-cloud"]
DIM = 64


def embed_text(text: str) -> list[float]:
    v = [0.0] * DIM
    for tok in re.findall(r"[a-z0-9]+|[一-鿿]", text.lower()):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        v[h % DIM] += 1.0 if (h >> 8) % 2 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def answer_for(messages: list[dict]) -> str:
    user = next((m["content"] for m in messages if m["role"] == "user"), "")
    q = re.search(r"Question: (.*)", user)
    question = q.group(1) if q else ""
    if "badjson" in question:
        return "Sure! Here is my answer without JSON."
    docs = re.findall(r'<document id="([^"]+)" title="([^"]*)">\n(.*?)\n</document>', user, re.S)
    health = re.search(r"Health state \(rules, read-only\): (\w+)", user)
    zh = bool(re.search(r"[一-鿿]", question))
    parts = []
    if health:
        parts.append(
            f"规则给出的健康状态是 {health.group(1)}。"
            if zh
            else f"The rules rate this component {health.group(1)}."
        )
    if docs:
        first = docs[0][2].strip().split("\n")[0][:200]
        parts.append(
            f"文档《{docs[0][1]}》指出：{first}" if zh else f"The document '{docs[0][1]}' says: {first}"
        )
    else:
        parts.append("已批准的文档中没有相关内容。" if zh else "The approved documents do not cover this.")
    if "probability" in question:
        parts.append("The failure probability is 80% within a week.")
    cites = [d[0] for d in docs[:1]] + (["DOC-9999#1"] if "cite-unknown" in question else [])
    checks = ["检查润滑" if zh else "Check lubrication"] if docs else []
    return json.dumps({"answer": " ".join(parts), "citations": cites, "checks": checks}, ensure_ascii=False)


class FakeOllama:
    def __init__(self, slow_s: float = 0.0, down: bool = False):
        self.slow_s, self.down = slow_s, down
        self.requests: list[tuple[str, dict]] = []

    def handle(self, method: str, path: str, body: dict) -> tuple[int, object, bool]:
        """Returns (status, payload, is_stream). A stream payload is a list of NDJSON objects."""
        self.requests.append((path, body))
        if path == "/api/version":
            return 200, {"version": "0.0.0-fake"}, False
        if path == "/api/tags":
            return 200, {"models": [{"name": m} for m in MODELS]}, False
        if path == "/api/embed":
            inp = body.get("input")
            texts = inp if isinstance(inp, list) else [inp]
            return 200, {"model": body.get("model"), "embeddings": [embed_text(t) for t in texts]}, False
        if path == "/api/chat":
            text = answer_for(body.get("messages", []))
            if body.get("stream", True):
                pieces = [text[i : i + 12] for i in range(0, len(text), 12)]
                events = [{"message": {"role": "assistant", "content": p}, "done": False} for p in pieces]
                events.append({"message": {"role": "assistant", "content": ""}, "done": True})
                return 200, events, True
            return 200, {"message": {"role": "assistant", "content": text}, "done": True}, False
        return 404, {"error": "not found"}, False

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            if self.down:
                raise httpx.ConnectError("connection refused", request=request)
            body = json.loads(request.content or b"{}")
            status, payload, stream = self.handle(request.method, request.url.path, body)
            if stream:

                def gen():
                    for obj in payload:
                        if self.slow_s:
                            time.sleep(self.slow_s)
                        yield (json.dumps(obj) + "\n").encode()

                return httpx.Response(status, stream=_Iter(gen()))
            return httpx.Response(status, json=payload)

        return httpx.MockTransport(handler)


class _Iter(httpx.SyncByteStream):
    def __init__(self, it):
        self.it = it

    def __iter__(self):
        yield from self.it
