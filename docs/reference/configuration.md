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
| `MODEL_HF` | `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` | no | HuggingFace repository of the GGUF model |
| `MODEL_FILE` | `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` | no | GGUF file name to download and serve |
| `TEMPLATE_FILE` | `data/templates/custom/chat_template_local.jinja` | no | Chat template loaded at runtime via `--chat-template-file`. Our default = froggeric v21.3 + `error_warnings` off. The pristine froggeric base is kept untouched at `custom/chat_template_v21.jinja` |
| `ERROR_WARNINGS` | `false` | no | Enable the template's tool-error heuristic (`⚠️ SYSTEM WARNING` injection + force thinking off after 2 failures). In `chat_template_local.jinja` detection is **precise** (explicit `Error:`/`Traceback`/JSON-error only), so enabling is safe; off by default as the conservative choice. `true` forwards `--chat-template-kwargs '{"error_warnings":true}'`. See [template-v21.md](../explanation/template-v21.md#error-escalation-in-tool-chains) |
| `LLAMA_CPP_DIR` | `~/llama.cpp` | no | Directory where llama.cpp will be cloned and compiled |
| `LLAMA_SERVER` | `~/llama.cpp/build/bin/llama-server` | no | Path to the compiled binary |
| `CUDA_HOME` | `/usr/local/cuda` | no | CUDA toolkit root |
| `PORT` | `8000` | no | Server listening port |
| `SERVED_NAME` | `qwen3` | no | Model name exposed in the API (`/v1/models`) |
| `N_GPU_LAYERS` | `-1` | no | Layers to offload to GPU. `-1` = all |
| `N_CTX` | `65536` | no | Maximum context size in tokens — see [infra/configs/current.md](../infra/configs/current.md) for the current benchmarked ceiling |
| `N_BATCH` | `4096` | no | Batch size for prompt processing (larger = faster prompt processing) |
| `N_PARALLEL` | `1` | no | Number of parallel request slots. **Keep at `1`** — with `auto` (-1) the server splits the KV cache across detected connections, reducing tokens per slot |
| `NO_MMAP` | `1` | no | Disable memory-mapped file I/O (recommended for performance) |
| `ENABLE_MTP` | `true` | no | Enable Multi-Token Prediction speculative decoding (requires model with MTP heads) |
| `MTP_TOKENS` | `2` | no | Number of draft tokens per step. Benchmarked optimum for both the 27B dense and 35B-A3B MoE model — see [infra/index.md](../infra/index.md) |
| `CACHE_TYPE_K` | `q4_0` | no | KV cache quantization for Key (K). Options: f32, f16, bf16, q8_0, q5_1, q5_0, q4_1, q4_0, iq4_nl. q4_0 benchmarked fastest + highest context ceiling for the default 35B-A3B model — see [infra/index.md](../infra/index.md) |
| `CACHE_TYPE_V` | `q4_0` | no | KV cache quantization for Value (V). Same options as CACHE_TYPE_K |
| `CTX_CHECKPOINTS` | `8` | no | Number of context checkpoints in RAM (llama.cpp default: 32). Lower values prevent OOM with long prompts |
| `CACHE_RAM` | `2048` | no | RAM allocated for cache in MiB (0 = disabled, use only VRAM). llama.cpp default: 8192 |
| `CACHE_IDLE_SLOTS` | `1` | no | Keep idle cache slots in RAM (0 = release immediately, 1 = keep warm for faster multi-turn) |
| `TEMPERATURE` | `0.6` | no | Sampling temperature. Qwen-recommended for coding/tool-calling. 0.1-0.4 = deterministic, 0.8-1.0 = creative |
| `TOP_K` | `20` | no | Limit sampling to K most probable tokens. 20 = focused (Qwen-recommended for coding), 40 = balanced |
| `TOP_P` | `0.95` | no | Nucleus sampling threshold |
| `MIN_P` | `0.0` | no | Minimum probability threshold relative to top token. `0.0` = off (Qwen-recommended) |
| `REPEAT_PENALTY` | `1.0` | no | Penalize recently seen tokens. `1.0` = off (Qwen-recommended — penalties hurt legit code/JSON repetition) |
| `REPEAT_LAST_N` | `64` | no | Number of recent tokens to consider for repeat penalty |
| `FREQUENCY_PENALTY` | `0.0` | no | Penalize tokens proportional to their frequency. `0.0` = off (Qwen-recommended for coding) |
| `PRESENCE_PENALTY` | `0.1` | no | Binary penalty for any token already used. Qwen recommends `0.0`, but `0.0` let the model fall into repetition loops (generating to the token cap) in long agentic use — `0.1` curbs that with little quality impact. See `HIPOTESE-09`. |
| `DRY_MULTIPLIER` | `0.8` | no | DRY sampler strength (`0` = off). **Primary anti-loop**: penalizes long verbatim repeated sequences (e.g. a reasoning block looping to the token cap) without hurting legitimate code repetition. See `HIPOTESE-09`. |
| `DRY_BASE` | `1.75` | no | DRY exponential base. |
| `DRY_ALLOWED_LENGTH` | `4` | no | Repeats up to this length are allowed. `2` (DRY default) is too aggressive for a thinking model (it rambles); `4` catches paragraph loops without breaking normal reasoning. |
| `DRY_PENALTY_LAST_N` | `1024` | no | Window DRY looks back over (`-1` = whole context — too broad here; a window targets recent loops). |
| `SEED` | `-1` | no | Random seed (-1 = random each call, any positive = reproducible) |
| `N_PREDICT` | `8192` | no | Maximum tokens to generate per response. `-1` = unlimited (can cause infinite generation) |

---

## Full `.env` example

```bash
# Credentials
HUGGINGFACE_TOKEN=hf_your_token_here

# GGUF model
MODEL_HF=unsloth/Qwen3.6-35B-A3B-MTP-GGUF
MODEL_FILE=Qwen3.6-35B-A3B-UD-Q4_K_M.gguf

# Template (froggeric v21.3 + error_warnings off; base pura em custom/chat_template_v21.jinja)
TEMPLATE_FILE=data/templates/custom/chat_template_local.jinja
ERROR_WARNINGS=false

# llama.cpp
LLAMA_CPP_DIR=/root/llama.cpp
LLAMA_SERVER=/root/llama.cpp/build/bin/llama-server

# CUDA
CUDA_HOME=/usr/local/cuda

# Server
PORT=8000
SERVED_NAME=qwen3
N_GPU_LAYERS=-1
N_CTX=106496
N_BATCH=4096
N_PARALLEL=1
NO_MMAP=1

# MTP (Multi-Token Prediction)
ENABLE_MTP=true
MTP_TOKENS=2

# KV Cache
CACHE_TYPE_K=q4_0
CACHE_TYPE_V=q4_0

# RAM control
CTX_CHECKPOINTS=8
CACHE_RAM=2048
CACHE_IDLE_SLOTS=1

# Sampling (Qwen-recommended defaults for coding/tool-calling)
TEMPERATURE=0.6
TOP_K=20
TOP_P=0.95
MIN_P=0.0
REPEAT_PENALTY=1.0
REPEAT_LAST_N=64
FREQUENCY_PENALTY=0.0
PRESENCE_PENALTY=0.1
DRY_MULTIPLIER=0.8
DRY_BASE=1.75
DRY_ALLOWED_LENGTH=4
DRY_PENALTY_LAST_N=1024
SEED=-1
N_PREDICT=8192
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
