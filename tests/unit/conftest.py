"""
Shared test helpers for the unit tests.

fake_ollama   a tiny HTTP server on a random local port that answers like Ollama:
              GET /api/tags, POST /api/chat and POST /api/embed. The real HTTP
              code is tested without installing Ollama or downloading a model.
              Set its behaviour on the returned server object:
                server.models   installed model names
                server.reply    the chat answer
                server.delay    seconds to wait before answering (timeouts)
                server.requests the JSON bodies received, for checking
"""

import hashlib
import json
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

EMBED_DIM = 64


def fake_embedding(text: str) -> list[float]:
    """A deterministic 'embedding': each word adds 1 to a dimension chosen by its hash.

    Texts sharing words get similar vectors - enough to test search end to end.
    """
    vector = [0.0] * EMBED_DIM
    for word in re.findall(r"[a-z]{3,}", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
    return vector


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the test output quiet
        pass

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": m} for m in self.server.models]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(body)
        if self.server.delay:
            time.sleep(self.server.delay)
        model = body["model"] if ":" in body["model"] else f"{body['model']}:latest"
        if model not in self.server.models:
            self._send(404, {"error": f"model '{body['model']}' not found, try pulling it first"})
        elif self.path == "/api/embed":
            texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
            self._send(200, {"model": body["model"], "embeddings": [fake_embedding(t) for t in texts]})
        else:
            self._send(
                200,
                {
                    "model": body["model"],
                    "message": {"role": "assistant", "content": self.server.reply},
                    "done": True,
                    "prompt_eval_count": 120,
                    "eval_count": 42,
                },
            )


@pytest.fixture
def fake_ollama():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    server.models = ["llama3.2:3b", "nomic-embed-text:latest"]
    server.reply, server.delay, server.requests = "Hello from the fake model.", 0, []
    # poll_interval: how often the server checks for shutdown (default 0.5 s would slow every test down)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    server.shutdown()
    server.server_close()


def closed_port_url() -> str:
    """A local URL where nothing listens (the OS gives a free port, which is closed again)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"
