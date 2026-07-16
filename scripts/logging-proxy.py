#!/usr/bin/env python3
"""Transparent logging proxy: OpenCode -> this proxy -> LiteLLM -> llama-server
Logs full request/response payloads to /root/qwen3/data/logs/proxy-debug.log"""

import http.server
import urllib.request
import json
import sys
import time
import threading
import os

UPSTREAM = "http://100.91.54.69:4000"
LISTEN_PORT = 4001
LOG_FILE = "/root/qwen3/data/logs/proxy-debug.log"

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

        # Parse request
        stream = False
        try:
            req_json = json.loads(body)
            model = req_json.get("model", "?")
            messages = req_json.get("messages", [])
            tools = req_json.get("tools", [])
            max_tokens = req_json.get("max_tokens", "?")
            stream = req_json.get("stream", False)
            temperature = req_json.get("temperature", "?")

            log(f"--- REQUEST {self.path} ---")
            log(f"  model={model} max_tokens={max_tokens} stream={stream} temp={temperature}")
            log(f"  tools_count={len(tools)} messages_count={len(messages)}")

            # Log each message
            for i, msg in enumerate(messages):
                role = msg.get("role", "?")
                content = msg.get("content", "")
                tc = msg.get("tool_calls")
                tid = msg.get("tool_call_id")
                rc = msg.get("reasoning_content")

                if tc:
                    for t in tc:
                        fn = t.get("function", {})
                        log(f"  msg[{i}] role={role} tool_call: {fn.get('name')} args={fn.get('arguments', '')[:300]}")
                elif tid:
                    c = str(content)[:200]
                    log(f"  msg[{i}] role={role} tool_call_id={tid} content={c}")
                elif rc:
                    log(f"  msg[{i}] role={role} content={repr(str(content)[:100])} reasoning={repr(str(rc)[:200])}")
                else:
                    log(f"  msg[{i}] role={role} content={repr(str(content)[:300])}")

            # Log tools
            if tools:
                for t in tools:
                    fn = t.get("function", {})
                    log(f"  tool_def: {fn.get('name')} params={json.dumps(fn.get('parameters', {}))[:200]}")

        except Exception as e:
            log(f"  PARSE ERROR: {e}")

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
            resp = urllib.request.urlopen(req, timeout=300)
            resp_body = resp.read()

            # Log response
            try:
                resp_json = json.loads(resp_body)
                if stream:
                    # For streaming, count chunks and log final
                    chunks = resp_body.decode("utf-8", errors="replace").strip().split("\n\n")
                    log(f"--- RESPONSE (streaming, {len(chunks)} chunks) ---")
                    # Parse last data chunk for final message
                    for chunk in reversed(chunks):
                        if chunk.startswith("data: ") and chunk != "data: [DONE]":
                            try:
                                cd = json.loads(chunk[6:])
                                delta = cd.get("choices", [{}])[0].get("delta", {})
                                fr = cd.get("choices", [{}])[0].get("finish_reason")
                                if delta.get("tool_calls"):
                                    for tc in delta["tool_calls"]:
                                        fn = tc.get("function", {})
                                        log(f"  stream tool_call: {fn.get('name')} args={fn.get('arguments', '')[:300]}")
                                if delta.get("content"):
                                    log(f"  stream content: {repr(delta['content'][:200])}")
                                if fr:
                                    log(f"  stream finish_reason: {fr}")
                                break
                            except:
                                pass
                else:
                    msg = resp_json.get("choices", [{}])[0].get("message", {})
                    fr = resp_json.get("choices", [{}])[0].get("finish_reason")
                    usage = resp_json.get("usage", {})
                    timings = resp_json.get("timings", {})

                    log(f"--- RESPONSE ---")
                    log(f"  finish_reason={fr}")
                    log(f"  content={repr(str(msg.get('content', ''))[:300])}")
                    if msg.get("reasoning_content"):
                        log(f"  reasoning_content={repr(str(msg['reasoning_content'])[:300])}")
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            log(f"  tool_call: {fn.get('name')} args={fn.get('arguments', '')[:300]}")
                    log(f"  usage={json.dumps(usage)}")
                    log(f"  timings={json.dumps(timings)}")
            except Exception as e:
                log(f"  RESPONSE PARSE ERROR: {e}")

            self.send_response(resp.status)
            for key, val in resp.getheaders():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(resp_body)

        except urllib.error.HTTPError as e:
            err_body = e.read()
            log(f"--- UPSTREAM ERROR {e.code} ---")
            log(f"  {err_body[:500]}")
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
        except Exception as e:
            log(f"--- UPSTREAM EXCEPTION: {e} ---")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "logging-proxy", "upstream": UPSTREAM}).encode())
            return

        upstream_url = UPSTREAM + self.path
        req = urllib.request.Request(
            upstream_url,
            method="GET",
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
        pass  # Suppress default HTTP logging


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT
    server = http.server.HTTPServer(("0.0.0.0", port), ProxyHandler)
    log(f"Logging proxy started on port {port} -> {UPSTREAM}")
    log(f"Log file: {LOG_FILE}")
    server.serve_forever()
