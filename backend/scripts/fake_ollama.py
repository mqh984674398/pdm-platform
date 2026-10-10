"""Serve the deterministic fake Ollama on 127.0.0.1 for the E2E demo (never a real model).

python scripts/fake_ollama.py --port 11435
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.simulation.fake_ollama import FakeOllama  # noqa: E402

FAKE = FakeOllama()


class Handler(BaseHTTPRequestHandler):
    def _go(self, method: str) -> None:
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        status, payload, stream = FAKE.handle(method, self.path, body)
        self.send_response(status)
        self.send_header("Content-Type", "application/x-ndjson" if stream else "application/json")
        self.end_headers()
        if stream:
            for obj in payload:
                self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
                self.wfile.flush()
        else:
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode())

    def do_GET(self) -> None:  # noqa: N802
        self._go("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._go("POST")

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11435)
    port = ap.parse_args().port
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
