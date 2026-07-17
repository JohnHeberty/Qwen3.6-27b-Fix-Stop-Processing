#!/usr/bin/env python3
"""Force-min-tokens proxy with Responses API ↔ Chat Completions bridge.

Handles OpenClaw (Responses API /responses) → LiteLLM (Chat Completions /v1/chat/completions).
Ensures max_tokens >= MIN_TOKENS. Supports streaming. Logs all traffic."""

import http.server
import json
import sys
import time
import threading
import os
import urllib.request
import socketserver
import uuid

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


def unwrap_content(content):
    """Convert Responses API content format to plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "input_text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "output_text":
                    parts.append(item.get("text", ""))
                elif "text" in item:
                    parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts) if parts else ""
    return str(content) if content else ""


def sanitize_patterns(obj):
    """Wrap unanchored regex patterns with ^ and $ for llama.cpp Jinja parser."""
    if isinstance(obj, dict):
        if "pattern" in obj and isinstance(obj["pattern"], str):
            p = obj["pattern"]
            if not (p.startswith("^") and p.endswith("$")):
                log(f"SANITIZE pattern: {p} -> ^{p}$")
                obj["pattern"] = f"^{p}$"
        for v in obj.values():
            sanitize_patterns(v)
    elif isinstance(obj, list):
        for v in obj:
            sanitize_patterns(v)


def _schema_depth(obj, current=0):
    """Calculate max nesting depth of a JSON Schema."""
    if not isinstance(obj, dict):
        return current
    max_d = current
    for v in obj.values():
        if isinstance(v, dict):
            max_d = max(max_d, _schema_depth(v, current + 1))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    max_d = max(max_d, _schema_depth(item, current + 1))
    return max_d


def sanitize_tool_schemas(tools):
    """Remove unsupported JSON Schema features for llama.cpp grammar parser.
    Strips: additionalProperties, anyOf, oneOf, allOf, not, if/then/else, dependentSchemas.
    Simplifies oversized tools to plain JSON string input."""
    if not tools:
        return
    for t in tools:
        func = t.get("function", t)
        params = func.get("parameters")
        if not params or not isinstance(params, dict):
            continue
        # If schema is too complex (many properties or deep nesting), simplify
        props = params.get("properties", {})
        if len(props) > 8 or _schema_depth(params) > 3:
            name = func.get("name", "?")
            log(f"SIMPLIFY tool schema: {name} ({len(props)} props, depth={_schema_depth(params)})")
            func["parameters"] = {
                "type": "object",
                "properties": {
                    "json_args": {
                        "type": "string",
                        "description": f"JSON string with arguments for {name}. See description for schema.",
                    }
                },
                "required": ["json_args"],
            }
        else:
            _strip_unsupported(params)


def _strip_unsupported(obj):
    """Recursively strip unsupported JSON Schema constructs."""
    if not isinstance(obj, dict):
        return
    # Remove features that llama.cpp grammar builder can't handle
    UNSUPPORTED_KEYS = (
        "additionalProperties", "not", "if", "then", "else",
        "dependentSchemas", "unevaluatedProperties", "minContains", "maxContains", "contains",
        "patternProperties", "minItems", "maxItems", "uniqueItems",
        "minProperties", "maxProperties",
    )
    for key in UNSUPPORTED_KEYS:
        if key in obj:
            del obj[key]
    # Flatten anyOf/oneOf/allOf to just the first variant
    for combo_key in ("anyOf", "oneOf", "allOf"):
        if combo_key in obj and isinstance(obj[combo_key], list):
            variants = obj[combo_key]
            if variants and isinstance(variants[0], dict):
                # Use first variant as the schema
                first = variants[0]
                del obj[combo_key]
                # Merge first variant into parent
                for k, v in first.items():
                    if k not in obj:
                        obj[k] = v
            elif not variants:
                del obj[combo_key]
    # Recurse
    for k, v in list(obj.items()):
        if isinstance(v, dict):
            _strip_unsupported(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _strip_unsupported(item)


def responses_tools_to_chat(tools):
    """Convert Responses API tools to Chat Completions tool format."""
    if not tools:
        return []
    result = []
    for t in tools:
        if t.get("type") == "function":
            func = {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {}),
            }
            result.append({"type": "function", "function": func})
    return result


def chat_tools_to_responses(tools):
    """Convert Chat Completions tools to Responses API tool format."""
    if not tools:
        return []
    result = []
    for t in tools:
        func = t.get("function", t)
        result.append({
            "type": "function",
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "parameters": func.get("parameters", {}),
        })
    return result


def responses_to_chat(req_json):
    """Convert Responses API request to Chat Completions format."""
    out = {}

    # Model
    out["model"] = req_json.get("model", "qwen")

    # Input → messages
    input_items = req_json.get("input", [])
    messages = []
    for item in input_items:
        if isinstance(item, dict):
            item_type = item.get("type", "")

            # function_call items (assistant's previous tool calls)
            if item_type == "function_call":
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": item.get("call_id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": item.get("name", ""),
                            "arguments": item.get("arguments", "{}"),
                        },
                    }],
                })
                continue

            # function_call_output items (tool results)
            if item_type == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": unwrap_content(item.get("output", "")),
                })
                continue

            # reasoning item — skip (will be regenerated)
            if item_type == "reasoning":
                continue

            # message items (user/assistant/system)
            role = item.get("role", "user")
            content = item.get("content", "")
            text = unwrap_content(content)
            if text:
                messages.append({"role": role, "content": text})
            # Handle tool_calls on assistant messages
            tool_calls = item.get("tool_calls")
            if tool_calls and role == "assistant":
                tc_list = []
                for tc in tool_calls:
                    fn = tc.get("function", tc)
                    tc_list.append({
                        "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", "{}") if isinstance(fn.get("arguments"), str) else json.dumps(fn.get("arguments", {})),
                        },
                    })
                messages[-1]["tool_calls"] = tc_list
        elif isinstance(item, str):
            messages.append({"role": "user", "content": item})
    out["messages"] = messages

    # Tools
    tools = req_json.get("tools", [])
    if tools:
        out["tools"] = responses_tools_to_chat(tools)

    # max_output_tokens → max_tokens
    max_out = req_json.get("max_output_tokens") or req_json.get("max_tokens")
    if max_out is not None:
        if max_out < MIN_TOKENS:
            log(f"FORCE max_tokens: {max_out} -> {MIN_TOKENS}")
            max_out = MIN_TOKENS
        out["max_tokens"] = max_out
    else:
        out["max_tokens"] = MIN_TOKENS
        log(f"NO max_tokens → set {MIN_TOKENS}")

    # Stream
    out["stream"] = req_json.get("stream", False)

    # Temperature / top_p
    for k in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "stop", "seed"):
        if k in req_json:
            out[k] = req_json[k]

    return out


def chat_to_responses_nonstream(resp_json, resp_id):
    """Convert Chat Completions non-streaming response to Responses API format."""
    choices = resp_json.get("choices", [])
    if not choices:
        return resp_json

    choice = choices[0]
    msg = choice.get("message", {})
    finish = choice.get("finish_reason", "stop")
    usage = resp_json.get("usage", {})

    output = []

    # Tool calls
    tool_calls = msg.get("tool_calls", [])
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except Exception:
            args = {"raw": fn.get("arguments", "")}
        output.append({
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:12]}",
            "call_id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "name": fn.get("name", ""),
            "arguments": json.dumps(args) if isinstance(args, dict) else str(args),
        })

    # Text content
    content = msg.get("content", "")
    if content:
        output.append({
            "type": "message",
            "id": f"msg_{uuid.uuid4().hex[:12]}",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": content}],
        })

    # Reasoning
    reasoning = msg.get("reasoning_content", "")
    if reasoning:
        output.insert(0, {
            "type": "reasoning",
            "id": f"reason_{uuid.uuid4().hex[:12]}",
            "summary": [{"type": "summary_text", "text": reasoning}],
        })

    status_map = {"stop": "completed", "length": "incomplete", "tool_calls": "completed"}
    status = status_map.get(finish, "completed")

    return {
        "id": resp_id,
        "object": "response",
        "status": status,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        try:
            req_json = json.loads(body)
        except Exception:
            req_json = {}

        is_responses_api = self.path.rstrip("/") == "/responses"
        stream = req_json.get("stream", False)
        model = req_json.get("model", "?")

        if is_responses_api:
            tools_raw = req_json.get("tools", [])
            input_items = req_json.get("input", [])
            max_tok = req_json.get("max_output_tokens") or req_json.get("max_tokens")
            log(f"POST /responses (→ /chat/completions) stream={stream} model={model} tools={len(tools_raw)} input={len(input_items)} max_output_tokens={max_tok}")

            # Convert to chat completions
            chat_req = responses_to_chat(req_json)
            # Sanitize tool patterns for Jinja parser
            sanitize_patterns(chat_req.get("tools", []))
            sanitize_tool_schemas(chat_req.get("tools", []))
            upstream_path = "/v1/chat/completions"
            body = json.dumps(chat_req).encode()
            log(f"CONVERTED: messages={len(chat_req.get('messages', []))} tools={len(chat_req.get('tools', []))} max_tokens={chat_req.get('max_tokens')} stream={chat_req.get('stream')}")
        else:
            # Direct chat completions — just force min_tokens
            max_tok = req_json.get("max_tokens")
            tools = req_json.get("tools", [])
            msgs = len(req_json.get("messages", []))
            log(f"POST {self.path} stream={stream} model={model} tools={len(tools)} msgs={msgs} max_tokens={max_tok}")

            if max_tok is not None and max_tok < MIN_TOKENS:
                req_json["max_tokens"] = MIN_TOKENS
                log(f"FORCE max_tokens: {max_tok} -> {MIN_TOKENS}")
            elif max_tok is None:
                req_json["max_tokens"] = MIN_TOKENS
                log(f"NO max_tokens → set {MIN_TOKENS}")
            # Sanitize tool patterns for Jinja parser
            sanitize_patterns(req_json.get("tools", []))
            sanitize_tool_schemas(req_json.get("tools", []))
            body = json.dumps(req_json).encode()
            upstream_path = self.path

        # Debug: dump the sanitized request body on error
        upstream_body = body

        upstream_url = UPSTREAM + upstream_path
        req = urllib.request.Request(
            upstream_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": self.headers.get("Authorization", ""),
            },
        )

        resp_id = f"resp_{uuid.uuid4().hex[:16]}"

        try:
            resp = urllib.request.urlopen(req, timeout=600)

            if stream:
                if is_responses_api:
                    self._stream_as_responses_api(resp, resp_id)
                else:
                    self._stream_passthrough(resp)
            else:
                resp_body = resp.read()
                resp.close()

                if is_responses_api:
                    try:
                        chat_resp = json.loads(resp_body)
                        responses_resp = chat_to_responses_nonstream(chat_resp, resp_id)
                        resp_body = json.dumps(responses_resp).encode()
                        # Log
                        out_items = responses_resp.get("output", [])
                        for item in out_items:
                            if item.get("type") == "message":
                                text = item.get("content", [{}])[0].get("text", "")
                                log(f"RESPONSE (non-stream): {repr(text[:200])}")
                            elif item.get("type") == "function_call":
                                log(f"RESPONSE (tool_call): {item.get('name')}({item.get('arguments', '')[:200]})")
                    except Exception as e:
                        log(f"RESPONSE CONVERSION ERROR: {e}")
                else:
                    try:
                        rj = json.loads(resp_body)
                        c = rj.get("choices", [{}])[0]
                        msg = c.get("message", {})
                        fr = c.get("finish_reason")
                        parts = [f"finish={fr}"]
                        if msg.get("content"):
                            parts.append(f"content={repr(msg['content'][:150])}")
                        if msg.get("reasoning_content"):
                            parts.append(f"reasoning={repr(msg['reasoning_content'][:150])}")
                        if msg.get("tool_calls"):
                            for t in msg["tool_calls"]:
                                fn = t.get("function", {})
                                parts.append(f"tool_call={fn.get('name')}({fn.get('arguments', '')[:200]})")
                        usage = rj.get("usage", {})
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
            log(f"UPSTREAM ERROR {e.code}: {err_body[:500]}")
            if e.code == 400:
                dump_path = "/root/qwen3/data/logs/last-400-request.json"
                try:
                    with open(dump_path, "w") as f:
                        json.dump(json.loads(body.decode("utf-8", errors="replace")), f, indent=2)
                    log(f"DUMPED 400 request to {dump_path}")
                except Exception as ex:
                    log(f"DUMP FAILED: {ex}")
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

    def _stream_passthrough(self, resp):
        """Forward SSE stream as-is (chat completions format)."""
        self.send_response(resp.status)
        for key, val in resp.getheaders():
            if key.lower() not in ("transfer-encoding", "connection"):
                self.send_header(key, val)
        self.end_headers()
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            self.wfile.write(chunk)
            self.wfile.flush()
        resp.close()

    def _stream_as_responses_api(self, resp, resp_id):
        """Convert chat completions SSE stream to Responses API SSE stream."""
        self.send_response(resp.status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        # Send response.created
        self._send_sse({"type": "response.created", "response": {"id": resp_id, "object": "response", "status": "in_progress"}})
        # Send output_item.added
        self._send_sse({"type": "response.output_item.added", "output_index": 0, "item": {"type": "message", "role": "assistant", "status": "in_progress"}})
        # Send content_part.added
        self._send_sse({"type": "response.content_part.added", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": ""}})

        text_buf = ""
        tool_calls_buf = {}  # index -> {id, name, arguments}
        finish_reason = None

        buf = b""
        while True:
            chunk = resp.read(1)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b"\n\n") or buf.endswith(b"\r\n\r\n"):
                for line in buf.decode("utf-8", errors="replace").split("\n"):
                    line = line.rstrip("\r")
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            continue
                        try:
                            d = json.loads(data_str)
                        except Exception:
                            continue

                        choices = d.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            finish_reason = choices[0].get("finish_reason")

                            content = delta.get("content", "")
                            if content:
                                text_buf += content
                                self._send_sse({"type": "response.output_text.delta", "item_id": f"msg_{uuid.uuid4().hex[:12]}", "output_index": 0, "content_index": 0, "delta": content})

                            # Accumulate tool calls
                            tc_deltas = delta.get("tool_calls", [])
                            for tc in tc_deltas:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_buf:
                                    tool_calls_buf[idx] = {
                                        "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                                        "name": "",
                                        "arguments": "",
                                    }
                                if tc.get("id"):
                                    tool_calls_buf[idx]["id"] = tc["id"]
                                fn = tc.get("function", {})
                                if fn.get("name"):
                                    tool_calls_buf[idx]["name"] = fn["name"]
                                if fn.get("arguments"):
                                    tool_calls_buf[idx]["arguments"] += fn["arguments"]

                            reasoning = delta.get("reasoning_content", "")
                            if reasoning:
                                self._send_sse({"type": "response.reasoning_summary_text.delta", "output_index": 0, "content_index": 0, "delta": reasoning})

                buf = b""

        # Finish text content
        self._send_sse({"type": "response.output_text.done", "output_index": 0, "content_index": 0, "text": text_buf})
        self._send_sse({"type": "response.content_part.done", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": text_buf}})

        # Emit tool calls as function_call items
        for idx in sorted(tool_calls_buf.keys()):
            tc = tool_calls_buf[idx]
            try:
                args_obj = json.loads(tc["arguments"])
                args_str = json.dumps(args_obj)
            except Exception:
                args_str = tc["arguments"]
            self._send_sse({
                "type": "response.output_item.added",
                "output_index": idx + 1,
                "item": {
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex[:12]}",
                    "call_id": tc["id"],
                    "name": tc["name"],
                    "arguments": args_str,
                },
            })
            self._send_sse({
                "type": "response.output_item.done",
                "output_index": idx + 1,
                "item": {
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex[:12]}",
                    "call_id": tc["id"],
                    "name": tc["name"],
                    "arguments": args_str,
                },
            })

        # Output item done for the message
        self._send_sse({"type": "response.output_item.done", "output_index": 0, "item": {"type": "message", "role": "assistant", "status": "completed"}})

        # Response completed
        status_map = {"stop": "completed", "length": "incomplete", "tool_calls": "completed"}
        self._send_sse({
            "type": "response.completed",
            "response": {
                "id": resp_id,
                "object": "response",
                "status": status_map.get(finish_reason, "completed"),
            },
        })

        resp.close()
        log(f"STREAM done: text={len(text_buf)} chars, tools={len(tool_calls_buf)}, finish={finish_reason}")

    def _send_sse(self, data):
        """Send a single SSE event."""
        line = f"data: {json.dumps(data)}\n\n"
        try:
            self.wfile.write(line.encode())
            self.wfile.flush()
        except Exception:
            pass

    def do_GET(self):
        log(f"GET {self.path}")
        if self.path == "/health" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "min_tokens": MIN_TOKENS, "upstream": UPSTREAM, "features": ["force_min_tokens", "responses_api_bridge"]}).encode())
            return
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


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT
    server = ThreadedHTTPServer(("0.0.0.0", port), ProxyHandler)
    log(f"Force-min-tokens proxy started on port {port} -> {UPSTREAM} (min_tokens={MIN_TOKENS}, responses_api_bridge=yes)")
    server.serve_forever()
