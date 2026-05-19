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
| `TEMPLATE_FILE` | `data/templates/archive/qwen3.6/chat_template-v18.jinja` | no | Jinja2 template to patch into the GGUF |
| `LLAMA_CPP_DIR` | `~/llama.cpp` | no | Directory where llama.cpp will be cloned and compiled |
| `LLAMA_SERVER` | `~/llama.cpp/build/bin/llama-server` | no | Path to the compiled binary |
| `CUDA_HOME` | `/usr/local/cuda` | no | CUDA toolkit root |
| `PORT` | `8000` | no | Server listening port |
| `SERVED_NAME` | `qwen3` | no | Model name exposed in the API (`/v1/models`) |
| `N_GPU_LAYERS` | `-1` | no | Layers to offload to GPU. `-1` = all |
| `N_CTX` | `81920` | no | Maximum context size in tokens (zero-penalty ceiling on RTX 3090) |
| `N_BATCH` | `512` | no | Batch size for prompt processing |
| `N_PARALLEL` | `1` | no | Number of parallel request slots. **Keep at `1`** — with `auto` (-1) the server splits the KV cache across detected connections, reducing tokens per slot |

---

## Full `.env` example

```bash
# Credentials
HUGGINGFACE_TOKEN=hf_your_token_here

# GGUF model
MODEL_HF=unsloth/Qwen3.6-27B-MTP-GGUF
MODEL_FILE=Qwen3.6-27B-Q4_K_M.gguf
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
N_CTX=81920
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
