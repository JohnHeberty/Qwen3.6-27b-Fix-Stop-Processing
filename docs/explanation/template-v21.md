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

### Error escalation in tool chains

Two-level system with a `consecutive_failures` counter for agentic workflows — prevents infinite loops on consecutive tool call failures.

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
