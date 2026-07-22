# Architecture

---

## What this project is

A local inference server for **Qwen3.6 27B** with an OpenAI-compatible API. Any client that speaks OpenAI (Python SDK, LiteLLM, OpenCode, curl) works without modification — just change the `base_url` to `http://localhost:8000/v1`.

---

## Technical decisions

### Why llama-server instead of vLLM?

| Aspect | vLLM (previous) | llama-server (current) |
|---|---|---|
| Model format | AWQ (safetensors, ~20 GB) | GGUF Q4_K_M (~17.1 GB) |
| Context on RTX 3090 | 6,272 tokens | 98,304 tokens |
| Customizable template | no (limited) | yes (--chat-template-file at runtime) |
| Compilation required | no | yes (with CUDA) |

The AWQ safetensors model with the Qwen3_5 DeltaNet+Mamba architecture left only ~6,272 tokens of context available on the RTX 3090. The GGUF Q4_K_M uses ~17.1 GB of VRAM for weights, leaving ~5.5 GB for KV cache — enough for 80k tokens at good speed with MTP enabled (benchmarked).

### Why GGUF Q4_K_M?

- Good quality/size tradeoff — default quantization for local inference
- ~17.1 GB VRAM for weights, ~5.5 GB remaining for KV cache on RTX 3090 (24,576 MB) at 80k context
- No Python dependency for inference (llama-server is C++)
- Jinja2 template patchable directly in the binary

### Why MTP (Multi-Token Prediction)?

The model embeds MTP prediction heads that draft multiple tokens per step. With `--spec-type draft-mtp --spec-draft-n-max 3`, the server generates up to 3 candidate tokens per forward pass and validates them against the main model. On Qwen3.6-27B with Q4_K_M at 80k context, this achieves **68-72 tok/s** (vs 25-30 without MTP) with 60-69% acceptance rate. No separate draft model is needed.

### Why froggeric's template v21?

The official Qwen3.6 template has critical bugs in KV cache, tool calling and thinking mode. The v21 fixes all of them. The template is loaded at runtime via `--chat-template-file` in `start-server.sh`, overriding the GGUF-embedded template without modifying the model file.

See details in [explanation/template-v21.md](template-v21.md).

### Why compile llama.cpp from source?

The pip package (`llama-cpp-python`) uses a generic pre-compiled binary. Compiling from source with `-DGGML_CUDA=ON` ensures:
- Full GPU usage (all layers offloaded)
- Optimizations specific to the target card

---

## Qwen3_5 architecture

Qwen3.6 27B uses the **hybrid Qwen3_5 architecture**: 64 layers total, with 48 linear attention layers (DeltaNet/GDN) and 16 full attention layers.

---

## Folder structure

```
qwen3/
├── .env                    local configuration (not versioned)
├── .env.example            configuration template (versioned)
├── Makefile                full setup and operations pipeline
├── requirements.txt        Python dependencies
│
├── data/
│   ├── models/             GGUF model (~17 GB, gitignored)
│   ├── templates/          froggeric Jinja2 templates (v21 = default)
│   ├── logs/               runtime logs (gitignored)
│   └── backups/            backups of the original GGUF template (gitignored)
│
├── scripts/
│   ├── setup.sh            installation script (called by Makefile)
│   └── start-server.sh     server startup script
│
├── src/
│
├── tests/
│   └── test_api.py         API integration tests (6 endpoints)
│
├── infra/
│   ├── litellm/
│   │   ├── docker-compose.yaml  LiteLLM + Postgres via Docker
│   │   └── config.yaml          LiteLLM proxy config
│   ├── opencode/
│   │   ├── config.json          OpenCode terminal assistant config
│   │   └── install-plugins.md   Plugin installation guide
│   ├── llama-server/
│   │   └── qwen-server.service  systemd unit for autostart
│   └── repomix/
│       └── repomix.config.json  Repomix codebase packing config
│
└── docs/                   documentation (Diátaxis)
    ├── index.md
    ├── tutorials/
    ├── how-to/
    ├── reference/
    └── explanation/
```

---

## Data flow

```
Client (Python SDK / curl / OpenCode)
    │
    ▼  HTTP POST /v1/chat/completions
llama-server (port 8000)
    │  reads
    ▼
data/models/Qwen3.6-27B-Q4_K_M.gguf   ← template loaded at runtime via --chat-template-file
    │  offloads
    ▼
GPU (RTX 3090, 24,576 MB VRAM)
    │  offloads weights (~17.1 GB)
    │  MTP drafts 3 tokens per step, validates with main model
    ▼
llama-server → streaming/complete response → Client (~70 tok/s with MTP)
```
