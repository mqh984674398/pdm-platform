"""Opt-in live test against a real local Ollama (LLM-06). Skipped unless PDM_OLLAMA_LIVE_URL is set.

PDM_OLLAMA_LIVE_URL=http://127.0.0.1:11434 PDM_OLLAMA_LIVE_MODEL=qwen2.5:7b-instruct \\
    pytest tests/llm/test_live.py
"""

import os

import pytest

from app.llm.client import OllamaClient
from app.llm.endpoint import validate_model

URL = os.environ.get("PDM_OLLAMA_LIVE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="live Ollama tests are opt-in (set PDM_OLLAMA_LIVE_URL)")


def test_live_local_ollama_answers_in_json():
    c = OllamaClient(URL)
    model = validate_model(os.environ.get("PDM_OLLAMA_LIVE_MODEL", ""), installed=c.models())
    out = c.chat(model, [{"role": "user", "content": 'Reply with {"ok": true}'}], {"type": "object"})
    assert "ok" in out
