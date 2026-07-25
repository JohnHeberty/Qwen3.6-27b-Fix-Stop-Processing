# Template v21 — froggeric

---

## Credits

This project uses the **Jinja2 chat template v21.3** created by [**froggeric**](https://huggingface.co/froggeric):

> **[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

The v21 template is a drop-in replacement for the official Qwen3.6 template that fixes multiple critical bugs present in the template published by Alibaba/Qwen.

---

## What the v21 template fixes

### KV Cache invalidation

The official template invalidates the KV cache on every turn in multi-turn conversations, forcing complete re-processing of the prompt on each response. The v21 normalizes whitespace in a way that maintains 100% KV cache hit rate — significantly reducing latency in long conversations.

### Tool calling loops

Error detection in the original template was substring-based: if the JSON response contained the word `"error"` for any reason, the template interpreted it as a failure and entered a loop. The v21 uses strict structure-based detection, eliminating false positives.

### Legacy engine compatibility

The original template used `loop.previtem` (a modern Jinja2 feature) which caused crashes in older llama.cpp builds and in minijinja. The v21 replaces it with array indexing — compatible with all versions.

### Thinking mode bypass

`enable_thinking=false` was not respected in certain call flows. The v21 fixes the behavior so that thinking mode control is consistent.

### Error escalation in tool chains (opt-in — default OFF)

Two-level system with a `consecutive_failures` counter for agentic workflows — on a tool
response whose first 80 chars match an error pattern (`error:`, `failed to`, `traceback`, …)
it injects a `⚠️ SYSTEM WARNING` into the prompt and, after 2 consecutive failures, forces the
thinking block off.

**This heuristic is gated behind the `error_warnings` template kwarg and is `false` by
default**, because the string match produces false positives (a `grep` that finds the word
"error", a test printing "0 errors", reading a log, `git status`, …). A false positive injects a
hidden "your approach is wrong" warning the app never sees, which can make the model abandon a
correct path — the same kind of silent conversation mutation that motivated removing the proxy.

Enable it only if you want the old behavior:
- per request: `chat_template_kwargs: {"error_warnings": true}`
- server-wide: set `ERROR_WARNINGS=true` in `.env` (start-server.sh forwards it via
  `--chat-template-kwargs`).

The `consecutive_failures` counter still runs when the flag is off, but emits nothing — the
prompt is identical to a run with no error detection at all.

---

## How the template is loaded

The template is loaded **at runtime** via the `--chat-template-file` flag passed to `llama-server` in `scripts/start-server.sh`. This overrides the GGUF-embedded template without modifying the model file.

```bash
llama-server --chat-template-file data/templates/custom/chat_template_v21.jinja ...
```

This approach is safer than binary-patching the GGUF because:
- The model file stays identical to the upstream download (verifiable via checksum)
- Template updates don't require re-downloading the model
- No risk of corrupting the GGUF header or vocabulary tokens

---

## Compatibility

The v21 template is compatible with:
- llama.cpp / llama-server
- LM Studio
- vLLM
- MLX
- Any engine with HuggingFace Jinja2 template support

---

## Template file

The template is located at `data/templates/custom/chat_template_v21.jinja`.
