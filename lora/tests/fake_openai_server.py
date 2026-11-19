#!/usr/bin/env python3
"""Servidor OpenAI-compatível FALSO, só CPU, para validar configs de cliente sem GPU.

Registra o corpo JSON de cada POST em /v1/chat/completions (um JSON por linha em --log)
e responde "ok" (streaming SSE ou JSON), para ver exatamente quais campos o cliente
(OpenCode 2.x, por exemplo) manda: temperature, top_p, top_k, chat_template_kwargs...

Uso:
  python3 -I lora/tests/fake_openai_server.py --port 18099 --log /tmp/bodies.jsonl
  # em outro shell, aponte o cliente para http://127.0.0.1:18099/v1

Nunca use a porta 18020 (produção) nem 18021 (instância LoRA).
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=18099)
ap.add_argument("--log", required=True)
ap.add_argument("--models", default="qwen3.8-27b,opencode-adapted")
args = ap.parse_args()
if args.port in (18020, 18021):
    raise SystemExit("porta reservada (18020 produção / 18021 LoRA)")
MODELS = [m for m in args.models.split(",") if m]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            return self._json({"object": "list", "data": [
                {"id": m, "object": "model", "owned_by": "fake", "max_model_len": 142080} for m in MODELS]})
        if self.path == "/health":
            return self._json({})
        self._json({"detail": "Not Found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            body = {"_raw": raw.decode(errors="replace")}
        with open(args.log, "a") as f:
            f.write(json.dumps({"path": self.path, "body": body}) + "\n")
        if not self.path.rstrip("/").endswith("chat/completions"):
            return self._json({"detail": "Not Found"}, 404)
        model = body.get("model", MODELS[0])
        now = int(time.time())
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            base = {"id": "fake-1", "object": "chat.completion.chunk", "created": now, "model": model}
            chunks = [
                {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": None}]},
                {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                {**base, "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}},
            ]
            for c in chunks:
                self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        self._json({"id": "fake-1", "object": "chat.completion", "created": now, "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}})


ThreadingHTTPServer(("127.0.0.1", args.port), H).serve_forever()
