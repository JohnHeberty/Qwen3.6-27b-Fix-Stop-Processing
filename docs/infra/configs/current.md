# Current Production Configuration

**Status:** Active (commit `9d16c1e`, latest)

## Model

| Parameter | Value |
|---|---|
| `MODEL_FILE` | `Qwen3.6-27B-Q5_K_M.gguf` |
| Quantization | Q5_K_M (~19.8 GB) |
| Source | [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF) |
| MTP heads (embedded) | 3 (`qwen35.next_n_predict_layers = 3`) |

## Server

| Parameter | Value |
|---|---|
| Engine | `llama-server` (`e8f19cc` + grammar patches) |
| GPU | RTX 3090 (24,576 MiB) |
| `N_CTX` | 65,536 |
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

## Draft Model Experiments

Testamos draft externo com 3 modelos como alternativa ao MTP interno. Nenhum superou o MTP n=2:

| Draft model | tok/s | Veredito |
|---|---|---|
| Qwen3-0.6B-Q4_K_M | 36 | Overhead do draft anula ganho |
| Qwen3.5-0.8B-Q4_K_M | 33-34 | Todos n_max=1..7 dão mesmo resultado |
| Qwen3.5-2B-Q4_K_M | 19 | Muito pesado para RTX 3090 |

MTP interno é superior porque as MTP heads são camadas extras no mesmo forward pass, sem carregar modelo separado.

## Build** `e8f19cc` (llama.cpp)
- **Patches:** `llama-cpp-grammar-patches.patch` (MAX_REPETITION_THRESHOLD=100000, auto-anchor, regex shorthands)
- **CMake flags:** `GGML_CUDA=ON`, `GGML_CUDA_FA=ON`, `GGML_CUDA_FA_ALL_QUANTS=ON`, `GGML_CUDA_GRAPHS=ON`, `CMAKE_CUDA_ARCHITECTURES=86`, `CMAKE_BUILD_TYPE=Release`
- **Note:** Build otimizado para RTX 3090 (sm_86) com FA_ALL_QUANTS para suporte a KV cache q5_1/q4_0.
