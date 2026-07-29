# Qwen3.6 — Local GGUF Server · OpenAI-compatible API

**This project fixes the bugs that make Qwen3.6 unusable out of the box on a local RTX 3090.**

- **Broken tool calling and thinking mode** — official GGUF ships with a buggy Jinja2 template. Fixed with froggeric's corrected template (v21.3) loaded at runtime.
- **KV cache split across concurrent connections** — `--parallel N` divides context, causing "Context size exceeded" errors. Fixed by forcing `--parallel 1`.

**Default model is now Qwen3.6-35B-A3B** (MoE, ~3B active params/token) — **~2.5x faster decode** than the 27B dense model at equal settings, since single-user decode is memory-bandwidth-bound by *active* params, not total params. Result: **106,496 token context with MTP + q4_0 KV cache** (~111 tok/s on RTX 3090, Q4_K_M), functional tool calling, stable thinking mode. See [why](docs/explanation/architecture.md#why-the-35b-a3b-moe-model-instead-of-the-27b-dense-model) and the [benchmark](docs/infra/reports/35b-a3b/q4_0/README-a3b.md). The original 27B dense model remains fully supported — see the benchmarks table below.

---

## Quick Start

```bash
git clone https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing.git qwen3
cd qwen3 && cp env-examples/qwen3.6-35b-a3b/.env.example .env
# Edit .env → set HUGGINGFACE_TOKEN
make setup    # install everything (20-40 min)
make start    # wait for "llama server listening"
```

**API:** `http://localhost:8000/v1` · Model: `qwen3` · API Key: any string

---

## Benchmarks

| Model | Status | Details |
|---|---|---|
| **Q4_K_M UD** (~22.6 GB, 35B-A3B MoE) ← **default** | ✓ | 104k context @ 111 tok/s (q4_0 cache) — [full table](docs/infra/reports/35b-a3b/q4_0/README-a3b.md) |
| **Q5_K_M** (~19 GB, 27B dense) | ✓ | 80k context @ 68 tok/s — [full table](docs/infra/reports/27b-dense/q8_0/README-q5.md) |
| **Q4_K_M** (~17.1 GB, 27B dense) | ✓ | 120k context @ 40 tok/s — [full table](docs/infra/reports/27b-dense/q8_0/README-q4.md) |
| **Q6_K** (~22.9 GB, 27B dense) | ✓ | 40k context @ 27 tok/s — [full table](docs/infra/reports/27b-dense/q8_0/README-q6.md) |

> _Full benchmark index: [docs/infra/index.md](docs/infra/index.md)_

---

## Documentation

| | |
|---|---|
| **[Getting Started](docs/tutorials/getting-started.md)** | Requirements, step-by-step install, verification |
| **[API Usage](docs/how-to/api-usage.md)** | Chat, streaming, thinking mode, tool calling |
| **[LiteLLM](docs/how-to/litellm.md)** | Proxy setup, fix "context size exceeded" |
| **[OpenCode](docs/how-to/opencode.md)** | Terminal AI assistant integration |
| **[Production](docs/how-to/production.md)** | systemd, Ollama coexistence, troubleshooting |
| **[Make Commands](docs/reference/make-commands.md)** | All targets |
| **[Configuration](docs/reference/configuration.md)** | All .env variables |
| **[Architecture](docs/explanation/architecture.md)** | GGUF vs vLLM, design decisions |
| **[Template](docs/explanation/template-v21.md)** | froggeric v21 — what the template fixes |

---

## Quick Reference

| Command | Description |
|---|---|
| `make setup` | Full pipeline: install from scratch |
| `make start` / `make stop` | Start / stop server |
| `make start-bg` | Background mode (`make logs` to follow) |
| `make restart` | Stop and restart |
| `make status` | State + VRAM usage |
| `make test` | 13 integration tests (incl. tool calling + reasoning contract) |
| `make litellm-start` | LiteLLM proxy on port 4000 |

---

## Acknowledgements

Template by [**froggeric**](https://huggingface.co/froggeric) — fixes KV cache, tool calling and thinking mode:  
**[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

---

*Default model: [Qwen/Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) (MoE, Apache 2.0) · GGUF: [unsloth/Qwen3.6-35B-A3B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF)*
*Also supported: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) (dense) · GGUF: [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)*
