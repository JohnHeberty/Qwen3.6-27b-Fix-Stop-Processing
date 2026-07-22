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
| `MODEL_FILE` | `Qwen3.6-27B-Q4_K_M.gguf` | no | GGUF file name to download and serve |
| `TEMPLATE_FILE` | `data/templates/custom/chat_template_v21.jinja` | no | Chat template file loaded at runtime via `--chat-template-file` (froggeric v21.3) |
| `LLAMA_CPP_DIR` | `~/llama.cpp` | no | Directory where llama.cpp will be cloned and compiled |
| `LLAMA_SERVER` | `~/llama.cpp/build/bin/llama-server` | no | Path to the compiled binary |
| `CUDA_HOME` | `/usr/local/cuda` | no | CUDA toolkit root |
| `PORT` | `8000` | no | Server listening port |
| `SERVED_NAME` | `qwen3` | no | Model name exposed in the API (`/v1/models`) |
| `N_GPU_LAYERS` | `-1` | no | Layers to offload to GPU. `-1` = all |
| `N_CTX` | `81920` | no | Maximum context size in tokens (80k, maximum stable with MTP on RTX 3090) |
| `N_BATCH` | `4096` | no | Batch size for prompt processing (larger = faster prompt processing) |
| `N_PARALLEL` | `1` | no | Number of parallel request slots. **Keep at `1`** — with `auto` (-1) the server splits the KV cache across detected connections, reducing tokens per slot |
| `NO_MMAP` | `1` | no | Disable memory-mapped file I/O (recommended for performance) |
| `ENABLE_MTP` | `true` | no | Enable Multi-Token Prediction speculative decoding (requires model with MTP heads) |
| `MTP_TOKENS` | `3` | no | Number of draft tokens per step (1-3). 3 = maximum for Qwen3.6-27B |
| `CACHE_TYPE_K` | `q8_0` | no | KV cache quantization for Key (K). Options: f32, f16, bf16, q8_0, q5_1, q5_0, q4_1, q4_0, iq4_nl. Lower = less VRAM |
| `CACHE_TYPE_V` | `q8_0` | no | KV cache quantization for Value (V). Same options as CACHE_TYPE_K |
| `CTX_CHECKPOINTS` | `8` | no | Number of context checkpoints in RAM (llama.cpp default: 32). Lower values prevent OOM with long prompts |
| `CACHE_RAM` | `2048` | no | RAM allocated for cache in MiB (0 = disabled, use only VRAM). llama.cpp default: 8192 |
| `CACHE_IDLE_SLOTS` | `1` | no | Keep idle cache slots in RAM (0 = release immediately, 1 = keep warm for faster multi-turn) |
| `TEMPERATURE` | `0.3` | no | Sampling temperature. 0.1-0.4 = deterministic (coding), 0.6 = recommended by Qwen3, 0.8-1.0 = creative |
| `TOP_K` | `40` | no | Limit sampling to K most probable tokens. 20 = focused (coding), 40 = balanced |
| `TOP_P` | `0.95` | no | Nucleus sampling threshold |
| `MIN_P` | `0.05` | no | Minimum probability threshold relative to top token |
| `REPEAT_PENALTY` | `1.15` | no | Penalize recently seen tokens. 1.0 = off, 1.15 = moderate |
| `REPEAT_LAST_N` | `64` | no | Number of recent tokens to consider for repeat penalty |
| `FREQUENCY_PENALTY` | `0.2` | no | Penalize tokens proportional to their frequency |
| `PRESENCE_PENALTY` | `0.1` | no | Binary penalty for any token already used |
| `SEED` | `-1` | no | Random seed (-1 = random each call, any positive = reproducible) |
| `N_PREDICT` | `4096` | no | Maximum tokens to generate per response. `-1` = unlimited (can cause infinite generation) |

---

## Full `.env` example

```bash
# Credentials
HUGGINGFACE_TOKEN=hf_your_token_here

# GGUF model
MODEL_HF=unsloth/Qwen3.6-27B-MTP-GGUF
MODEL_FILE=Qwen3.6-27B-Q4_K_M.gguf

# Template (froggeric v21.3)
TEMPLATE_FILE=data/templates/custom/chat_template_v21.jinja

# llama.cpp
LLAMA_CPP_DIR=/root/llama.cpp
LLAMA_SERVER=/root/llama.cpp/build/bin/llama-server

# CUDA
CUDA_HOME=/usr/local/cuda

# Server
PORT=8000
SERVED_NAME=qwen3
N_GPU_LAYERS=-1
N_CTX=81920
N_BATCH=4096
N_PARALLEL=1
NO_MMAP=1

# MTP (Multi-Token Prediction)
ENABLE_MTP=true
MTP_TOKENS=3

# KV Cache
CACHE_TYPE_K=q8_0
CACHE_TYPE_V=q8_0

# RAM control
CTX_CHECKPOINTS=8
CACHE_RAM=2048
CACHE_IDLE_SLOTS=1

# Sampling
TEMPERATURE=0.3
TOP_K=40
TOP_P=0.95
MIN_P=0.05
REPEAT_PENALTY=1.15
REPEAT_LAST_N=64
FREQUENCY_PENALTY=0.2
PRESENCE_PENALTY=0.1
SEED=-1
N_PREDICT=4096
```

---

## Override without editing the file

Any variable can be passed inline to a `make` command:

```bash
N_CTX=16384 make start     # smaller context (uses less VRAM)
PORT=9000 make start       # different port
ENABLE_MTP=false make start # disable MTP
```

---

## Security

The `.env` file contains `HUGGINGFACE_TOKEN` and is listed in `.gitignore` — it is never committed. The `.env.example` has a placeholder token (`hf_XXXXX`) and is the only versioned configuration file.
