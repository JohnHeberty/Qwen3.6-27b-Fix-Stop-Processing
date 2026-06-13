# Reference — Configuration (`.env`)

Copy `.env.example` to `.env` and edit as needed.

```bash
cp .env.example .env
```

---

## Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `HUGGINGFACE_TOKEN` | — | **yes** | HuggingFace access token. Get one at https://huggingface.co/settings/tokens |
| `MODEL_HF` | `unsloth/Qwen3.6-27B-MTP-GGUF` | no | HuggingFace repository of the GGUF model |
| `MODEL_FILE` | `Qwen3.6-27B-Q5_K_M.gguf` | no | GGUF file name to download and serve |
| `TEMPLATE_FILE` | `data/templates/archive/qwen3.6/chat_template-v18.jinja` | no | Jinja2 template to patch into the GGUF |
| `LLAMA_CPP_DIR` | `~/llama.cpp` | no | Directory where llama.cpp will be cloned and compiled |
| `LLAMA_SERVER` | `~/llama.cpp/build/bin/llama-server` | no | Path to the compiled binary |
| `CUDA_HOME` | `/usr/local/cuda` | no | CUDA toolkit root |
| `PORT` | `8000` | no | Server listening port |
| `SERVED_NAME` | `qwen3` | no | Model name exposed in the API (`/v1/models`) |
| `N_GPU_LAYERS` | `-1` | no | Layers to offload to GPU. `-1` = all |
| `N_CTX` | `65536` | no | Maximum context size in tokens (64k, balanced performance/space on RTX 3090 with Q5_K_M) |
| `N_BATCH` | `4096` | no | Batch size for prompt processing (larger = faster prompt processing) |
| `N_PARALLEL` | `1` | no | Number of parallel request slots. **Keep at `1`** — with `auto` (-1) the server splits the KV cache across detected connections, reducing tokens per slot |
| `NO_MMAP` | `1` | no | Disable memory-mapped file I/O (recommended for performance) |
| `CACHE_TYPE_K` | `q8_0` | no | KV cache quantization for Key (K). Options: f32, f16, bf16, q8_0, q5_1, q5_0, q4_1, q4_0, iq4_nl. Lower = less VRAM |
| `CACHE_TYPE_V` | `q8_0` | no | KV cache quantization for Value (V). Same options as CACHE_TYPE_K |
| `CTX_CHECKPOINTS` | `8` | no | Number of context checkpoints in RAM (llama.cpp default: 32). Lower values prevent OOM with long prompts |
| `CACHE_RAM` | `2048` | no | RAM allocated for cache in MiB (0 = disabled, use only VRAM). llama.cpp default: 8192 |
| `CACHE_IDLE_SLOTS` | `1` | no | Keep idle cache slots in RAM (0 = release immediately, 1 = keep warm for faster multi-turn) |
| `N_PREDICT` | `4096` | no | Maximum tokens to generate per response. `-1` = unlimited (can cause infinite generation) |

---

## Full `.env` example

```bash
# Credentials
HUGGINGFACE_TOKEN=hf_your_token_here

# GGUF model
MODEL_HF=unsloth/Qwen3.6-27B-MTP-GGUF
MODEL_FILE=Qwen3.6-27B-Q5_K_M.gguf
TEMPLATE_FILE=data/templates/archive/qwen3.6/chat_template-v18.jinja

# llama.cpp
LLAMA_CPP_DIR=/root/llama.cpp
LLAMA_SERVER=/root/llama.cpp/build/bin/llama-server

# CUDA
CUDA_HOME=/usr/local/cuda

# Server
PORT=8000
SERVED_NAME=qwen3
N_GPU_LAYERS=-1
N_CTX=65536
N_BATCH=512
```

---

## Override without editing the file

Any variable can be passed inline to a `make` command:

```bash
N_CTX=32768 make start     # smaller context (uses less VRAM)
PORT=9000 make start       # different port
SERVED_NAME=llm make start # different name in the API
```

---

## Security

The `.env` file contains `HUGGINGFACE_TOKEN` and is listed in `.gitignore` — it is never committed. The `.env.example` has a placeholder token (`hf_XXXXX`) and is the only versioned configuration file.
