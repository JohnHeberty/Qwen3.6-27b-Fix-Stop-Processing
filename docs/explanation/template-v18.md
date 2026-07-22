# Template v18 — froggeric

---

## Credits

This project uses the **Jinja2 chat template v18** created by [**froggeric**](https://huggingface.co/froggeric):

> **[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

The v18 template is a drop-in replacement for the official Qwen3.6 template that fixes multiple critical bugs present in the template published by Alibaba/Qwen.

---

## What the v18 template fixes

### KV Cache invalidation

The official template invalidates the KV cache on every turn in multi-turn conversations, forcing complete re-processing of the prompt on each response. The v18 normalizes whitespace in a way that maintains 100% KV cache hit rate — significantly reducing latency in long conversations.

### Tool calling loops

Error detection in the original template was substring-based: if the JSON response contained the word `"error"` for any reason, the template interpreted it as a failure and entered a loop. The v18 uses strict structure-based detection, eliminating false positives.

### Legacy engine compatibility

The original template used `loop.previtem` (a modern Jinja2 feature) which caused crashes in older llama.cpp builds and in minijinja. The v18 replaces it with array indexing — compatible with all versions.

### Thinking mode bypass

`enable_thinking=false` was not respected in certain call flows. The v18 fixes the behavior so that thinking mode control is consistent.

### Error escalation in tool chains

Two-level system with a `consecutive_failures` counter for agentic workflows — prevents infinite loops on consecutive tool call failures.

---

## How the patch is applied

The template is patched **directly into the GGUF file** via a binary (streaming) patch script. This ensures the correct template is used regardless of the client or server configuration.

The patch is binary (streaming) to avoid corrupting the byte-level vocabulary tokens:

1. Reads the GGUF header with a forward scan to locate `tokenizer.chat_template`
2. Calculates alignment padding (32 bytes) after the substitution
3. Stream-copies the entire file to `/tmp` with the new template and correct padding
4. Atomically replaces the original via `shutil.move`
5. Saves a backup of the original template to `data/backups/gguf_template_backup_<ts>.jinja`

> **Note:** The legacy `make fix-template` target and `src/fix_template.py` script have been removed. The patching logic is now handled elsewhere in the build pipeline.

---

## Compatibility

The v18 template is compatible with:
- llama.cpp / llama-server
- LM Studio
- vLLM
- MLX
- Any engine with HuggingFace Jinja2 template support

---

## Template file

The template is located at `data/templates/custom/chat_template_v21.jinja` after `make setup`.
