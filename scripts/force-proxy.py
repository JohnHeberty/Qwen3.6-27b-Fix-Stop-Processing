#!/usr/bin/env python3
"""Force-min-tokens proxy: intercepts OpenClaw/OpenCode requests,
ensures max_tokens >= MIN_TOKENS before forwarding to LiteLLM."""

import http.server
import json
import sys
import time
import threading
import os
import urllib.request

UPSTREAM = "http://100.91.54.69:4000"
LISTEN_PORT = 4002
MIN_TOKENS = 512
LOG_FILE = "/root/qwen3/data/logs/force-proxy.log"

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
log_lock = threading.Lock()


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with log_lock:
        with open(LOG_FILE, "a") as f:
            f.write(line)
        print(line.strip(), flush=True)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        try:
            req_json = json.loads(body)
        except Exception:
            req_json = {}

        stream = req_json.get("stream", False)
        max_tokens_original = req_json.get("max_tokens")
        model = req_json.get("model", "?")
        tools = req_json.get("tools", [])
        messages_count = len(req_json.get("messages", []))

        # Force min_tokens
        if max_tokens_original is not None and max_tokens_original < MIN_TOKENS:
            req_json["max_tokens"] = MIN_TOKENS
            log(f"FORCE max_tokens: {max_tokens_original} -> {MIN_TOKENS} (model={model}, tools={len(tools)}, msgs={messages_count})")
        elif max_tokens_original is None:
            log(f"NO max_tokens in request (model={model}, tools={len(tools)}, msgs={messages_count})")

        body = json.dumps(req_json).encode()

        # Forward upstream
        upstream_url = UPSTREAM + self.path
        req = urllib.request.Request(
            upstream_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": self.headers.get("Content-Type", "application/json"),
                "Authorization": self.headers.get("Authorization", ""),
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=600)
            resp_body = resp.read()

            # Log response summary
            try:
                resp_json = json.loads(resp_body)
                choices = resp_json.get("choices", [{}])
                if choices:
                    c = choices[0]
                    fr = c.get("finish_reason")
                    msg = c.get("message", {})
                    tc = msg.get("tool_calls")
                    content = msg.get("content", "")
                    rc = msg.get("reasoning_content", "")

                    parts = [f"finish={fr}"]
                    if content:
                        parts.append(f"content={repr(content[:150])}")
                    if rc:
                        parts.append(f"reasoning={repr(rc[:150])}")
                    if tc:
                        for t in tc:
                            fn = t.get("function", {})
                            parts.append(f"tool_call={fn.get('name')}({fn.get('arguments', '')[:200]})")
                    usage = resp_json.get("usage", {})
                    parts.append(f"tokens={usage.get('completion_tokens', '?')}")
                    log(f"RESPONSE: {' | '.join(parts)}")
            except Exception:
                pass

            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp_body)

        except urllib.error.HTTPError as e:
            err_body = e.read()
            log(f"UPSTREAM ERROR {e.code}: {err_body[:300]}")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            log(f"UPSTREAM EXCEPTION: {e}")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "min_tokens": MIN_TOKENS, "upstream": UPSTREAM}).encode())
            return
        self._proxy_get()

    def do_PUT(self):
        self._proxy_get()

    def _proxy_get(self):
        upstream_url = UPSTREAM + self.path
        req = urllib.request.Request(
            upstream_url,
            method=self.command,
            headers={"Authorization": self.headers.get("Authorization", "")},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            resp_body = resp.read()
            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT
    server = http.server.HTTPServer(("0.0.0.0", port), ProxyHandler)
    log(f"Force-min-tokens proxy started on port {port} -> {UPSTREAM} (min_tokens={MIN_TOKENS})")
    server.serve_forever()
