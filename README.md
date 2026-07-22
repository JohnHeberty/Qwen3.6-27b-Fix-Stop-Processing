# Qwen3.6 27B — Local GGUF Server · OpenAI-compatible API

**This project fixes the bugs that make Qwen3.6 27B unusable out of the box on a local RTX 3090.**

- **Broken tool calling and thinking mode** — official GGUF ships with a buggy Jinja2 template. Fixed with froggeric's corrected template (v21.3) loaded at runtime.
- **KV cache split across concurrent connections** — `--parallel N` divides context, causing "Context size exceeded" errors. Fixed by forcing `--parallel 1`.

Result: **81,920 token context with MTP** (~68 tok/s on RTX 3090, Q5_K_M), functional tool calling, stable thinking mode.

---

## Quick Start

```bash
git clone https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing.git qwen3
cd qwen3 && cp .env.example .env
# Edit .env → set HUGGINGFACE_TOKEN
make setup    # install everything (20-40 min)
make start    # wait for "llama server listening"
```

**API:** `http://localhost:8000/v1` · Model: `qwen3` · API Key: any string

---

## Benchmarks

| Model | Status | Details |
|---|---|---|
| **Q5_K_M** (~19 GB) | ✓ | 80k context @ 68 tok/s — [full table](docs/infra/README-q5.md) |
| **Q4_K_M** (~17.1 GB) | ✓ | 120k context @ 40 tok/s — [full table](docs/infra/README-q4.md) |
| **Q6_K** (~22.9 GB) | ✓ | 40k context @ 27 tok/s — [full table](docs/infra/README-q6.md) |

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
| `make test` | 6 integration tests |
| `make litellm-start` | LiteLLM proxy on port 4000 |

---

## Acknowledgements

Template by [**froggeric**](https://huggingface.co/froggeric) — fixes KV cache, tool calling and thinking mode:  
**[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

---

*Model: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) (Apache 2.0) · GGUF: [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)*
