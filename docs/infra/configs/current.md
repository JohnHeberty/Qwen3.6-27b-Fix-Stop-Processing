# Current Production Configuration

**Status:** Active (commit `9d16c1e`, latest)

## Model

| Parameter | Value |
|---|---|
| `MODEL_FILE` | `Qwen3.6-27B-Q4_K_M.gguf` |
| Quantization | Q4_K_M (~17.1 GB) |
| Source | [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF) |
| MTP heads (embedded) | 3 (`qwen35.next_n_predict_layers = 3`) |

## Server

| Parameter | Value |
|---|---|
| Engine | `llama-server` (`e8f19cc` + grammar patches) |
| GPU | RTX 3090 (24,576 MiB) |
| `N_CTX` | 131,072 |
| `N_BATCH` | 4096 |
| `N_UBATCH` | 512 |
| `CACHE_TYPE_K` | `q8_0` |
| `CACHE_TYPE_V` | `q8_0` |
| `ENABLE_MTP` | `true` |
| `MTP_TOKENS` | 2 |
| `CTX_CHECKPOINTS` | 8 |
| `CACHE_RAM` | 10240 |
| `BENCHMARK` | `null` (disabled) |
| Threading | `-t 28` (CPU threads for prompt processing) |

## Template

- **File:** `data/templates/custom/chat_template_v21.jinja`
- **Fork:** froggeric v21.3
- **Features:** `<thinking>` reasoning_content, tool_call handling, `requiresStringContent` passthrough

## Proxy Chain

```
OpenClaw → force-proxy (port 4002) → LiteLLM (100.91.54.69:4000) → llama-server (port 8000)
```

force-proxy: `scripts/force-proxy.py`, `UPSTREAM_API_KEY=sk-litellm-master`,
`MIN_TOKENS=512`, `MAX_OUTPUT_TOKENS=8192`, `MAX_HISTORY=25`

## Build

- **Commit:** `e8f19cc` (llama.cpp)
- **Patches:** `llama-cpp-grammar-patches.patch` (MAX_REPETITION_THRESHOLD=100000, auto-anchor, regex shorthands)
- **CMake flags:** `GGML_CUDA=ON`, `GGML_CUDA_FA=ON`, `GGML_CUDA_GRAPHS=ON`, `CMAKE_BUILD_TYPE=Release`
- **Note:** `CMAKE_CUDA_ARCHITECTURES` not set (builds generic CUDA kernels)
