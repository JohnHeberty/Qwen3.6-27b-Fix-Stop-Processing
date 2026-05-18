# Architecture

---

## What this project is

A local inference server for **Qwen3.6 27B** with an OpenAI-compatible API. Any client that speaks OpenAI (Python SDK, LiteLLM, OpenCode, curl) works without modification — just change the `base_url` to `http://localhost:8000/v1`.

---

## Technical decisions

### Why llama-server instead of vLLM?

| Aspect | vLLM (previous) | llama-server (current) |
|---|---|---|
| Model format | AWQ (safetensors, ~20 GB) | GGUF Q4_K_M (~16 GB) |
| Context on RTX 3090 | 6,272 tokens | 63,488 tokens |
| Customizable template | no (limited) | yes (binary patch directly in GGUF) |
| Compilation required | no | yes (with CUDA) |

The AWQ safetensors model with the Qwen3_5 DeltaNet+Mamba architecture left only ~6,272 tokens of context available on the RTX 3090. The GGUF Q4_K_M uses 16 GB of VRAM for weights, leaving ~8 GB for KV cache — enough for 63,488 tokens.

### Why GGUF Q4_K_M?

- High-quality quantization with iMatrix — good quality/size tradeoff
- 16 GB VRAM for weights, ~8 GB remaining for KV cache on RTX 3090 (24,576 MB)
- No Python dependency for inference (llama-server is C++)
- Jinja2 template patchable directly in the binary

### Why froggeric's template v18?

The official Qwen3.6 template has critical bugs in KV cache, tool calling and thinking mode. The v18 fixes all of them. The patch is applied directly into the GGUF binary via `src/fix_template.py` to ensure the correct template is used regardless of how the server is started.

See details in [explanation/template-v18.md](template-v18.md).

### Why compile llama.cpp from source?

The pip package (`llama-cpp-python`) uses a generic pre-compiled binary. Compiling from source with `-DGGML_CUDA=ON` ensures:
- Full GPU usage (all layers offloaded)
- Source patches applied (disable fused GDN — required for the Qwen3_5 hybrid architecture on SM 8.6)
- Optimizations specific to the target card

---

## Qwen3_5 architecture

Qwen3.6 27B uses the **hybrid Qwen3_5 architecture**: 64 layers total, with 48 linear attention layers (DeltaNet/GDN) and 16 full attention layers. The **Fused Gated Delta Net** CUDA kernel has a bug on SM 8.6 GPUs (RTX 3090) that produces invalid output. The Makefile applies a source patch to llama.cpp to disable this kernel before compiling.

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
│   ├── models/             GGUF model (~16 GB, gitignored)
│   ├── templates/          froggeric Jinja2 templates (v8–v18)
│   ├── logs/               runtime logs (gitignored)
│   └── backups/            backups of the original GGUF template (gitignored)
│
├── scripts/
│   ├── setup.sh            installation script (called by Makefile)
│   └── start-server.sh     server startup script
│
├── src/
│   └── fix_template.py     binary GGUF patcher with v18 template
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
data/models/Qwen3.6-27B-Q4_K_M.gguf   ← v18 template patched inside the file
    │  offloads
    ▼
GPU (RTX 3090, 24,576 MB VRAM)
    │  generates tokens
    ▼
llama-server → streaming/complete response → Client
```
