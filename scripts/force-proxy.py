#!/usr/bin/env python3
"""Force-min-tokens proxy with Responses API ↔ Chat Completions bridge.

OpenClaw (Responses API /responses) → LiteLLM (Chat Completions /v1/chat/completions).
- Ensures max_tokens >= MIN_TOKENS
- Filters heartbeat polls (returns HEARTBEAT_OK without hitting model)
- Sanitizes tool schemas for llama.cpp grammar parser
- Unsimplifies json_args back to original params on output
- Thread-safe: all mutable state is per-request
"""

import http.server
import json
import re
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from copy import deepcopy

# ── Config ──────────────────────────────────────────────────────────────────
UPSTREAM = "http://100.91.54.69:4000"
LISTEN_PORT = 4002
MIN_TOKENS = 512
MAX_HISTORY = 25
LOG_FILE = "/root/qwen3/data/logs/force-proxy.log"
DUMP_DIR = "/root/qwen3/data/logs"
HEARTBEAT_TOKEN = "[OpenClaw heartbeat poll]"

os_import = __import__("os")
os_import.makedirs(os_import.path.dirname(LOG_FILE), exist_ok=True)

_log_lock = threading.Lock()


def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with _log_lock:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")


# ── Helpers ─────────────────────────────────────────────────────────────────

def unwrap_content(content):
    """Convert Responses API content (list of dicts or string) to plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in ("input_text", "output_text"):
                    parts.append(item.get("text", ""))
                elif "text" in item:
                    parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts) if parts else ""
    return str(content) if content else ""


def make_call_id():
    return f"call_{uuid.uuid4().hex[:12]}"


def make_fc_id():
    return f"fc_{uuid.uuid4().hex[:12]}"


def make_msg_id():
    return f"msg_{uuid.uuid4().hex[:12]}"


def make_resp_id():
    return f"resp_{uuid.uuid4().hex[:16]}"


# ── Tool Schema Sanitization ───────────────────────────────────────────────

UNSUPPORTED_SCHEMA_KEYS = (
    "additionalProperties", "not", "if", "then", "else",
    "dependentSchemas", "unevaluatedProperties", "minContains", "maxContains",
    "contains", "patternProperties", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties",
)


def _schema_depth(obj, current=0):
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


def strip_unsupported(obj):
    """Recursively strip unsupported JSON Schema constructs (returns new dict)."""
    if not isinstance(obj, dict):
        return obj
    result = {}
    for k, v in obj.items():
        if k in UNSUPPORTED_SCHEMA_KEYS:
            continue
        if isinstance(v, dict):
            result[k] = strip_unsupported(v)
        elif isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    new_list.append(strip_unsupported(item))
                else:
                    new_list.append(item)
            result[k] = new_list
        else:
            result[k] = v
    return result


def flatten_combo(obj):
    """Flatten anyOf/oneOf/allOf to first variant. Returns new dict."""
    if not isinstance(obj, dict):
        return obj
    result = {}
    for k, v in obj.items():
        if k in ("anyOf", "oneOf", "allOf") and isinstance(v, list) and v:
            if isinstance(v[0], dict):
                first = flatten_combo(v[0])
                for fk, fv in first.items():
                    if fk not in result:
                        result[fk] = fv
        elif isinstance(v, dict):
            result[k] = flatten_combo(v)
        elif isinstance(v, list):
            result[k] = [flatten_combo(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


def sanitize_patterns(obj):
    """Wrap unanchored regex patterns with ^ and $ for llama.cpp Jinja parser."""
    if isinstance(obj, dict):
        if "pattern" in obj and isinstance(obj["pattern"], str):
            p = obj["pattern"]
            if not (p.startswith("^") and p.endswith("$")):
                obj["pattern"] = f"^{p}$"
        for v in obj.values():
            sanitize_patterns(v)
    elif isinstance(obj, list):
        for v in obj:
            sanitize_patterns(v)


def sanitize_tools(tools):
    """Sanitize tool schemas for llama.cpp. Returns (sanitized_tools, simplified_map).

    simplified_map: {tool_name: original_parameters} for tools simplified to json_args.
    NEVER mutates the input list.
    """
    if not tools:
        return [], {}
    simplified = {}
    result = []
    for t in tools:
        t = deepcopy(t)
        func = t.get("function", t)
        params = func.get("parameters")
        if not params or not isinstance(params, dict):
            result.append(t)
            continue
        name = func.get("name", "?")
        n_props = len(params.get("properties", {}))
        depth = _schema_depth(params)
        if n_props > 8 or depth >= 3:
            log(f"SIMPLIFY {name} ({n_props} props, depth={depth})")
            simplified[name] = deepcopy(params)
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
            clean = flatten_combo(strip_unsupported(params))
            func["parameters"] = clean
            sanitize_patterns(func.get("parameters", {}))
        result.append(t)
    return result, simplified


def unsimplify_args(name, arguments_str, simplified_map):
    """If tool was simplified to json_args, parse and restore original params."""
    if name not in simplified_map:
        return arguments_str
    try:
        args = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
    except Exception:
        return arguments_str
    if isinstance(args, dict) and "json_args" in args:
        json_val = args["json_args"]
        if isinstance(json_val, str):
            try:
                real_args = json.loads(json_val)
                log(f"UNSIMPLIFY {name}: {json.dumps(real_args, ensure_ascii=False)[:200]}")
                return json.dumps(real_args, ensure_ascii=False)
            except Exception:
                return json_val
    return json.dumps(args) if isinstance(args, dict) else arguments_str


# ── Heartbeat Detection ────────────────────────────────────────────────────

def is_heartbeat_poll(input_items):
    """Check if this is a heartbeat poll (last user item contains heartbeat text)."""
    for item in reversed(input_items):
        if isinstance(item, dict) and item.get("type") == "message" and item.get("role") == "user":
            content = unwrap_content(item.get("content", ""))
            if HEARTBEAT_TOKEN in content:
                return True
            break
    return False


def make_heartbeat_response(resp_id):
    """Generate a Responses API HEARTBEAT_OK response without hitting the model."""
    return {
        "id": resp_id,
        "object": "response",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": make_msg_id(),
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "HEARTBEAT_OK"}],
            }
        ],
        "usage": {"input_tokens": 0, "output_tokens": 2, "total_tokens": 2},
    }


# ── Responses API ↔ Chat Completions Conversion ───────────────────────────

def responses_to_chat(req_json):
    """Convert Responses API request to Chat Completions format.

    Returns (chat_request, simplified_map).
    """
    input_items = req_json.get("input", [])
    messages = []

    for item in input_items:
        if not isinstance(item, dict):
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
            continue

        item_type = item.get("type", "")

        if item_type == "function_call":
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": item.get("call_id", make_call_id()),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                }],
            })
            continue

        if item_type == "function_call_output":
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": unwrap_content(item.get("output", "")),
            })
            continue

        if item_type == "reasoning":
            continue

        role = item.get("role", "user")
        content = unwrap_content(item.get("content", ""))
        if not content:
            continue

        msg = {"role": role, "content": content}

        if role == "assistant":
            tool_calls = item.get("tool_calls")
            if tool_calls:
                tc_list = []
                for tc in tool_calls:
                    fn = tc.get("function", tc)
                    args = fn.get("arguments", "{}")
                    if not isinstance(args, str):
                        args = json.dumps(args)
                    tc_list.append({
                        "id": tc.get("id", make_call_id()),
                        "type": "function",
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": args,
                        },
                    })
                msg["tool_calls"] = tc_list

        messages.append(msg)

    messages = clean_conversation(messages)

    out = {
        "model": req_json.get("model", "qwen"),
        "messages": messages,
        "stream": req_json.get("stream", False),
    }

    # Tools: Responses API format → Chat Completions format, then sanitize
    tools = req_json.get("tools", [])
    if tools:
        chat_tools = []
        for t in tools:
            if t.get("type") == "function":
                chat_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                })
        out["tools"], simplified_map = sanitize_tools(chat_tools)
    else:
        simplified_map = {}

    # max_tokens
    max_out = req_json.get("max_output_tokens") or req_json.get("max_tokens")
    if max_out is not None:
        if max_out < MIN_TOKENS:
            log(f"FORCE max_tokens: {max_out} -> {MIN_TOKENS}")
            max_out = MIN_TOKENS
        out["max_tokens"] = max_out
    else:
        out["max_tokens"] = MIN_TOKENS

    # Pass through other params
    for k in ("temperature", "top_p", "frequency_penalty", "presence_penalty", "stop", "seed"):
        if k in req_json:
            out[k] = req_json[k]

    return out, simplified_map


def _strip_context_blocks(text):
    """Remove OpenClaw internal context blocks from text. Returns cleaned text."""
    # First remove the entire context structure (preamble + blocks)
    text = re.sub(
        r'OpenClaw runtime context for the immediately preceding.*?<<<END_OPENCLAW_INTERNAL_CONTEXT>>>',
        '', text, flags=re.DOTALL
    ).strip()
    # Then remove any remaining standalone context blocks
    text = re.sub(
        r'<<<[A-Z_]+_CONTEXT>>>.*?<<<END_[A-Z_]+_CONTEXT>>>',
        '', text, flags=re.DOTALL
    ).strip()
    return text


def clean_conversation(messages):
    """Clean conversation history to prevent model from learning bad patterns.

    Key behavior: identifies the REAL last user message (not a context-only block)
    and ensures it survives all cleaning.
    """
    if not messages:
        return messages

    # Pre-clean: strip context blocks from ALL user messages, track which ones have real content
    real_user_indices = []
    for idx, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "") or ""
        if not isinstance(content, str):
            continue
        stripped = _strip_context_blocks(content)
        if stripped:
            # Has real content — update in place
            messages[idx] = {**msg, "content": stripped}
            real_user_indices.append(idx)
        # context-only user messages will be removed later

    # The real last user message is the last one with actual content
    real_last_user_idx = real_user_indices[-1] if real_user_indices else -1
    # The absolute last user (may be context-only) — used for "last user" protection
    abs_last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            abs_last_user_idx = i
            break

    cleaned = []
    for idx, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        is_real_last_user = (idx == real_last_user_idx)
        is_abs_last_user = (idx == abs_last_user_idx)
        is_any_last_user = is_real_last_user or is_abs_last_user

        # Remove context-only user messages (no real content after stripping)
        if role == "user" and isinstance(content, str):
            stripped = _strip_context_blocks(content)
            if not stripped:
                if is_real_last_user:
                    # This IS the real user message but it was only context — keep as placeholder
                    log(f"CLEAN: last real user is context-only, keeping placeholder")
                    msg = {**msg, "content": "(empty message)"}
                else:
                    continue
            else:
                msg = {**msg, "content": stripped}

        # Remove failed turns
        if isinstance(content, str) and "[assistant turn failed" in content.lower() and not is_any_last_user:
            continue

        # Remove heartbeat polls (but not the last user message)
        if isinstance(content, str) and HEARTBEAT_TOKEN in content and not is_any_last_user:
            continue

        # Remove MoltBot errors
        if isinstance(content, str) and "Something went wrong while processing" in content and not is_any_last_user:
            continue

        # Remove empty/tiny assistant messages without tool_calls
        if role == "assistant" and not msg.get("tool_calls"):
            text = (content or "").strip()
            if not text or text == "..." or len(text) < 3:
                continue

        # Remove noise user messages (?, ??, Eai?, etc.) but NOT the real last user
        if role == "user" and not is_real_last_user:
            text = re.sub(r'^\[.*?\]\s*', '', content.strip())
            if re.match(r'^[\?\!\.]+$', text):
                continue
            if re.match(r'^(?:Eai|Eai\?+|Tá on\?*|Continue.*|Diga.*)\s*$', text, re.IGNORECASE):
                continue

        cleaned.append(msg)

    # Remove failed tool_call + error pairs (assistant generated bad args, tool rejected)
    # This prevents model from learning "tool calls always fail" pattern
    if len(cleaned) >= 2:
        filtered = []
        skip_next = False
        for i, msg in enumerate(cleaned):
            if skip_next:
                skip_next = False
                continue
            role = msg.get("role", "")
            content = str(msg.get("content", "") or "")
            # If this is a tool response with validation error, skip it AND the preceding assistant
            if role == "tool" and (
                "Validation failed" in content
                or "must have required properties" in content
                or "additional properties not allowed" in content
                or "Failed to parse" in content
            ):
                if filtered and filtered[-1].get("role") == "assistant":
                    filtered.pop()
                    log(f"CLEAN: removed failed tool_call pair (assistant + error)")
                continue
            filtered.append(msg)
        cleaned = filtered

    # Collapse consecutive text-only assistant messages into just the last one
    # Model sees "I'll do X" repeated → learns to output text instead of tool calls
    if len(cleaned) >= 2:
        collapsed = []
        assistant_run = []
        for msg in cleaned:
            role = msg.get("role", "")
            if role == "assistant" and not msg.get("tool_calls"):
                assistant_run.append(msg)
            else:
                if assistant_run:
                    collapsed.append(assistant_run[-1])
                    assistant_run = []
                collapsed.append(msg)
        if assistant_run:
            collapsed.append(assistant_run[-1])
        if len(collapsed) < len(cleaned):
            log(f"CLEAN: collapsed {len(cleaned)} -> {len(collapsed)} messages (removed {len(cleaned)-len(collapsed)} text-only assistant)")
        cleaned = collapsed

    # Collapse consecutive user messages into last per block
    if len(cleaned) >= 2:
        collapsed = []
        user_run = []
        for msg in cleaned:
            if msg.get("role") == "user":
                user_run.append(msg)
            else:
                if user_run:
                    collapsed.append(user_run[-1])
                    user_run = []
                collapsed.append(msg)
        if user_run:
            collapsed.append(user_run[-1])
        cleaned = collapsed

    # Truncate to MAX_HISTORY
    if len(cleaned) > MAX_HISTORY:
        system_msg = cleaned[0] if cleaned[0].get("role") == "system" else None
        rest = cleaned[1:] if system_msg else cleaned
        keep = MAX_HISTORY - (1 if system_msg else 0)
        truncated = rest[-keep:]
        # Ensure last is user
        if truncated[-1].get("role") != "user":
            for i in range(len(cleaned) - 1, -1, -1):
                if cleaned[i].get("role") == "user" and cleaned[i] not in truncated:
                    truncated.append(cleaned[i])
                    break
        if system_msg:
            truncated = [system_msg] + truncated
        log(f"CLEAN: {len(messages)} -> {len(truncated)} msgs (truncated to {MAX_HISTORY})")
        cleaned = truncated

    removed = len(messages) - len(cleaned)
    if removed:
        log(f"CLEAN: removed {removed} messages from {len(messages)}")

    return cleaned


# ── Response Conversion ────────────────────────────────────────────────────

def chat_to_responses_nonstream(resp_json, resp_id, simplified_map):
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
    for tc in msg.get("tool_calls", []):
        fn = tc.get("function", {})
        name = fn.get("name", "")
        unsimplified = unsimplify_args(name, fn.get("arguments", "{}"), simplified_map)
        try:
            args = json.loads(unsimplified)
        except Exception:
            args = {"raw": unsimplified}
        output.append({
            "type": "function_call",
            "id": make_fc_id(),
            "call_id": tc.get("id", make_call_id()),
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args),
        })

    # Text content
    content = msg.get("content", "")
    if content:
        output.append({
            "type": "message",
            "id": make_msg_id(),
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
    return {
        "id": resp_id,
        "object": "response",
        "status": status_map.get(finish, "completed"),
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


# ── HTTP Handler ───────────────────────────────────────────────────────────

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
        input_items = req_json.get("input", []) if is_responses_api else []
        tools_raw = req_json.get("tools", [])
        max_tok = req_json.get("max_output_tokens") or req_json.get("max_tokens") or req_json.get("max_tokens")

        log(f"POST {self.path} stream={stream} tools={len(tools_raw)} input={len(input_items)} max_tokens={max_tok}")

        # ── Heartbeat fast path ──
        if is_responses_api and input_items and is_heartbeat_poll(input_items):
            resp_id = make_resp_id()
            log(f"HEARTBEAT detected → returning HEARTBEAT_OK (no upstream)")
            heartbeat_resp = make_heartbeat_response(resp_id)
            resp_body = json.dumps(heartbeat_resp).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp_body)
            return

        # ── Dump input items for debugging ──
        if is_responses_api and input_items:
            try:
                with open(f"{DUMP_DIR}/last-request-body.json", "w") as f:
                    json.dump(req_json, f, indent=2, ensure_ascii=False)
                with open(f"{DUMP_DIR}/last-input-items.json", "w") as f:
                    json.dump(input_items, f, indent=2, ensure_ascii=False)
                for i, item in enumerate(input_items):
                    if isinstance(item, dict):
                        t = item.get("type", "?")
                        role = item.get("role", "")
                        name = item.get("name", "")
                        content = unwrap_content(item.get("content", ""))
                        extra = f" name={name}" if name else ""
                        log(f"INPUT[{i}] type={t} role={role}{extra}: {repr(content[:200])}")
            except Exception:
                pass

        # ── Convert to Chat Completions ──
        if is_responses_api:
            chat_req, simplified_map = responses_to_chat(req_json)
            upstream_path = "/v1/chat/completions"
            body = json.dumps(chat_req).encode()
            log(f"CONVERTED: msgs={len(chat_req.get('messages', []))} tools={len(chat_req.get('tools', []))} max_tokens={chat_req.get('max_tokens')}")
            # Dump converted
            try:
                with open(f"{DUMP_DIR}/last-converted-request.json", "w") as f:
                    json.dump({"messages": chat_req["messages"], "tools": chat_req.get("tools", []), "max_tokens": chat_req.get("max_tokens")}, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        else:
            simplified_map = {}
            upstream_path = self.path
            if max_tok is not None and max_tok < MIN_TOKENS:
                req_json["max_tokens"] = MIN_TOKENS
            elif max_tok is None:
                req_json["max_tokens"] = MIN_TOKENS
            body = json.dumps(req_json).encode()

        # ── Forward to upstream ──
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

        resp_id = make_resp_id()

        try:
            resp = urllib.request.urlopen(req, timeout=600)

            if stream:
                if is_responses_api:
                    self._stream_as_responses_api(resp, resp_id, simplified_map)
                else:
                    self._stream_passthrough(resp)
            else:
                resp_body = resp.read()
                resp.close()

                if is_responses_api:
                    try:
                        chat_resp = json.loads(resp_body)
                        responses_resp = chat_to_responses_nonstream(chat_resp, resp_id, simplified_map)
                        resp_body = json.dumps(responses_resp).encode()
                        for item in responses_resp.get("output", []):
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
                try:
                    with open(f"{DUMP_DIR}/last-400-request.json", "w") as f:
                        json.dump(json.loads(body.decode("utf-8", errors="replace")), f, indent=2)
                except Exception:
                    pass
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

    # ── Streaming: Chat Completions → Responses API ──

    def _stream_as_responses_api(self, resp, resp_id, simplified_map):
        self.send_response(resp.status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        self._send_sse({"type": "response.created", "response": {"id": resp_id, "object": "response", "status": "in_progress"}})
        self._send_sse({"type": "response.output_item.added", "output_index": 0, "item": {"type": "message", "role": "assistant", "status": "in_progress"}})
        self._send_sse({"type": "response.content_part.added", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": ""}})

        text_buf = ""
        tool_calls_buf = {}
        finish_reason = None

        buf = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf or b"\r\n\r\n" in buf:
                sep = b"\n\n" if b"\n\n" in buf else b"\r\n\r\n"
                idx = buf.find(sep)
                if idx < 0:
                    break
                block = buf[:idx]
                buf = buf[idx + len(sep):]

                for line in block.decode("utf-8", errors="replace").split("\n"):
                    line = line.rstrip("\r")
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        continue
                    try:
                        d = json.loads(data_str)
                    except Exception:
                        continue

                    choices = d.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0]["finish_reason"]

                    content = delta.get("content", "")
                    if content:
                        text_buf += content
                        self._send_sse({"type": "response.output_text.delta", "item_id": make_msg_id(), "output_index": 0, "content_index": 0, "delta": content})

                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_buf:
                            tool_calls_buf[idx] = {"id": tc.get("id", make_call_id()), "name": "", "arguments": ""}
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

        # Finish text
        self._send_sse({"type": "response.output_text.done", "output_index": 0, "content_index": 0, "text": text_buf})
        self._send_sse({"type": "response.content_part.done", "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": text_buf}})

        # Emit tool calls
        for idx in sorted(tool_calls_buf.keys()):
            tc = tool_calls_buf[idx]
            unsimplified = unsimplify_args(tc["name"], tc["arguments"], simplified_map)
            try:
                args_obj = json.loads(unsimplified)
                args_str = json.dumps(args_obj, ensure_ascii=False)
            except Exception:
                args_str = unsimplified if isinstance(unsimplified, str) else tc["arguments"]
            fc_id = make_fc_id()
            self._send_sse({"type": "response.output_item.added", "output_index": idx + 1, "item": {"type": "function_call", "id": fc_id, "call_id": tc["id"], "name": tc["name"], "arguments": args_str}})
            self._send_sse({"type": "response.output_item.done", "output_index": idx + 1, "item": {"type": "function_call", "id": fc_id, "call_id": tc["id"], "name": tc["name"], "arguments": args_str}})

        self._send_sse({"type": "response.output_item.done", "output_index": 0, "item": {"type": "message", "role": "assistant", "status": "completed"}})

        status_map = {"stop": "completed", "length": "incomplete", "tool_calls": "completed"}
        self._send_sse({"type": "response.completed", "response": {"id": resp_id, "object": "response", "status": status_map.get(finish_reason or "stop", "completed")}})

        resp.close()
        log(f"STREAM done: text={len(text_buf)} chars, tools={len(tool_calls_buf)}, finish={finish_reason}")
        for idx in sorted(tool_calls_buf.keys()):
            tc = tool_calls_buf[idx]
            log(f"  TOOL CALL [{idx}]: {tc['name']}({tc['arguments'][:300]})")

    def _stream_passthrough(self, resp):
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

    def _send_sse(self, data):
        line = f"data: {json.dumps(data)}\n\n"
        try:
            self.wfile.write(line.encode())
            self.wfile.flush()
        except Exception:
            pass

    def do_GET(self):
        log(f"GET {self.path}")
        if self.path in ("/health", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "min_tokens": MIN_TOKENS,
                "upstream": UPSTREAM,
                "features": ["force_min_tokens", "responses_api_bridge", "heartbeat_filter"],
            }).encode())
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
    log(f"Force-proxy started on port {port} -> {UPSTREAM} (min_tokens={MIN_TOKENS})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down...")
        server.shutdown()
