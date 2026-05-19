# Qwen3.6 27B — Local GGUF Server · OpenAI-compatible API

**This project fixes the bugs that make Qwen3.6 27B unusable out of the box on a local RTX 3090.**

The community has been reporting these problems ([Reddit](https://www.reddit.com/r/LocalLLaMA/comments/1t49pqu/struggling_with_qwen36_27b_35b_locally_3090_slow/), [llama.cpp #22746](https://github.com/ggml-org/llama.cpp/issues/22746)):

- **Broken tool calling and thinking mode** — the official GGUF ships with a Jinja2 template that has critical bugs in KV cache handling, `<think>` block termination, and function call formatting. Fixed here by patching the template v18 directly into the GGUF binary.
- **KV cache split across concurrent connections** — when `--parallel N` is used and multiple requests arrive simultaneously, llama-server creates N slots and divides the context window between them (63,488 ÷ 2 = 31,744 tokens per slot), causing "Context size exceeded" errors under LiteLLM or agentic workloads. Fixed here by forcing `--parallel 1` so the full 63,488-token KV cache is always available to each request.

The result is a validated setup that actually works: 63,488 token context, functional tool calling, stable thinking mode, and a warm KV cache across requests.

---

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: Q4_K_M · `--n-gpu-layers -1` · `--parallel 1` · Debian 13 · Driver 590.48.01.  
Inference: 200 tokens generated, 27-token prompt. RSS = `llama-server` process system RAM.

| `N_CTX` | Context | VRAM used | VRAM free | RSS (RAM) | 200 tok time | tok/s | Viable? |
|---|---|---|---|---|---|---|---|
| 63,488 | **62k** | 20,582 MiB | 3,544 MiB | 1.4 GB | 5.6 s | 35.7 | ✓ |
| 65,536 | **64k** | 20,704 MiB | 3,422 MiB | 1.4 GB | 5.5 s | 36.4 | ✓ |
| 81,920 | **80k** | 21,728 MiB | 2,398 MiB | 1.4 GB | 5.6 s | 35.8 | ✓ |
| 98,304 | **96k** | 22,752 MiB | 1,374 MiB | 1.5 GB | 5.6 s | 35.7 | ✓ ← máximo sem penalidade |
| 114,688 | 112k | 22,768 MiB | 1,358 MiB | 2.9 GB | 19.6 s | 10.2 | ⚠️ |
| 131,072 | 128k | 22,356 MiB | 1,770 MiB | 4.4 GB | 37.2 s | 5.4 | ⚠️ |
| 163,840 | 160k | 22,852 MiB | 1,274 MiB | 6.2 GB | 43.7 s | 4.6 | ⚠️ |
| 196,608 | 192k | 22,846 MiB | 1,280 MiB | 8.5 GB | 57.9 s | 3.5 | ⚠️ |
| 229,376 | 224k | 22,842 MiB | 1,284 MiB | 10.7 GB | 73.6 s | 2.7 | ⚠️ |
| 262,144 | 256k | 22,786 MiB | 1,340 MiB | 13.1 GB | 77.2 s | 2.6 | ✗ |

**Conclusões:**

- **Até 96k (98,304): zero penalidade.** VRAM sobe linearmente, RSS fica em ~1.5 GB, tok/s idêntico ao 63k. O llama.cpp mantém o KV cache inteiramente na VRAM.
- **A fronteira está entre 96k e 112k.** De 98k para 114k o RSS dobra (1.5 → 2.9 GB) e o tok/s cai de 35 para 10 — o KV cache começa a transbordar para RAM do sistema.
- **De 128k a 224k o VRAM mal varia** — o llama.cpp pré-aloca em blocos grandes, mas a RAM do sistema cresce continuamente (~2 GB por 32k tokens extras) e a inferência fica cada vez mais lenta.
- **256k é inviável:** 13 GB de RAM, 77 s para 200 tokens (2.6 tok/s).
- A lentidão não é só tamanho de prompt — o Qwen3_5 tem 48 camadas DeltaNet/GDN com estado recorrente que escala com `N_CTX`, então mesmo um prompt curto fica lento num contexto grande.

**Recomendação:** `N_CTX=63488` para uso diário (padrão). Use `N_CTX=98304` se precisar de contexto longo sem abrir mão de velocidade.

> Local inference server for **Qwen3.6 27B** using [llama-server](https://github.com/ggml-org/llama.cpp) with GGUF Q4_K_M model.  
> 100% OpenAI-compatible API · Thinking mode · Tool calling · **63,488 token context**

**Tested and validated on: Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8**

---

## Requirements

### Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q4_K_M model uses ~16 GB of VRAM. With 24,576 MB (RTX 3090), ~8 GB remain for KV cache — enough for **63,488 tokens** of context.

### Software

| Requirement | Minimum | Used/Validated | Check |
|---|---|---|---|
| OS | Debian 12 / Ubuntu 22.04+ | Debian 12 (Bookworm) | `lsb_release -a` |
| NVIDIA Driver | ≥ 560 | **590.48.01** ✓ | `nvidia-smi` |
| CUDA Toolkit | 12.x | **12.8** at `/usr/local/cuda` | `nvcc --version` |
| Git | any | — | `git --version` |

> Python, cmake and build-essential are installed automatically by `make setup`. The only manual prerequisites are the **NVIDIA driver + CUDA toolkit**.

**Install CUDA toolkit (if needed):**
```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update && sudo apt-get install -y cuda-toolkit-12-8
```

---

## Installation

### 1. Clone and configure

```bash
git clone https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing.git qwen3
cd qwen3
cp .env.example .env
```

Edit `.env` and fill in the required token:

```bash
HUGGINGFACE_TOKEN=hf_your_token_here   # https://huggingface.co/settings/tokens
```

### 2. Full setup (run once)

```bash
make setup
```

Runs **8 steps** automatically. Each step checks if it was already done — running twice is safe.

| Step | What it does |
|---|---|
| `[1]` install-system-deps | apt: python3, cmake, git, build-essential |
| `[2]` setup-cuda | Verifies CUDA toolkit, registers libcudart |
| `[3]` create-venv | Creates isolated Python `.venv` |
| `[4]` install-python-deps | pip: gguf, huggingface-hub, openai, requests |
| `[5]` build-llama-server | Clones and compiles llama-server with CUDA |
| `[6]` build-llama-cpp-python | Compiles llama-cpp-python with GPU offload |
| `[7]` download-model | Downloads `Qwen3.6-27B-Q4_K_M.gguf` (~16 GB) |
| `[8]` fix-template | Patches the GGUF with froggeric's v18 template |

Estimated time: **20–40 minutes** (compilation + model download).

### 3. Start and test

```bash
make start     # foreground server — wait for "llama server listening"
make test      # in another terminal — should show 6/6 tests passing
make status    # server state + VRAM usage
```

The server will be available at `http://localhost:8000/v1`.

---

## API Usage

The API is 100% compatible with the OpenAI SDK — just change the `base_url`.

| Parameter | Value |
|---|---|
| Base URL | `http://<host>:8000/v1` |
| Model name | `qwen3` |
| API Key | any string (not validated) |

### Python

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "What is a language model?"}],
    max_tokens=512,
    temperature=0.7
)
print(response.choices[0].message.content)
```

### curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3","messages":[{"role":"user","content":"Hello!"}],"max_tokens":256}'
```

### Streaming

```python
stream = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "Tell me a short story."}],
    max_tokens=512,
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Thinking mode (extended reasoning)

Qwen3.6 reasons internally before responding. The thinking content comes in `reasoning_content`:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[{"role": "user", "content": "What is 17 × 23?"}],
    max_tokens=300   # minimum 300 so thinking mode has enough space
)
print("Reasoning:", response.choices[0].message.reasoning_content)
print("Answer:   ", response.choices[0].message.content)
```

To **disable** thinking (faster responses):
```python
messages=[{"role": "system", "content": "<|think_off|>"}, {"role": "user", "content": "..."}]
```

---

## Coexistence with Ollama

If Ollama is installed, both compete for the 24 GB of VRAM. `make start` already unloads Ollama models automatically. For a permanent fix:

```bash
make configure-ollama   # reduces OLLAMA_KEEP_ALIVE from 30 min → 5 min
make ollama-unload      # manually frees Ollama VRAM right now
```

---

## Production (systemd)

To start the server automatically on boot:

```bash
make install-service    # registers the service (does not enable yet)
make enable-service     # enables auto-start on boot + starts now
```

> **Warning:** auto-start on boot conflicts with Ollama if both use the GPU. Use `make disable-service` to revert.

Manage the service:
```bash
sudo systemctl status qwen-server      # current state
sudo systemctl restart qwen-server     # restart
sudo journalctl -u qwen-server -f      # live logs
```

---

## LiteLLM Integration

A ready-to-use config is available at `infra/litellm/config.yaml`. To start the proxy on port 4000:

```bash
make litellm-start
```

In your projects, point to `http://localhost:4000` with `model="qwen"`. The config already includes `context_window: 63488` to prevent the `Context size has been exceeded` error.

---

## Quick Command Reference

| Command | Description |
|---|---|
| `make setup` | Full pipeline: installs everything from scratch |
| `make start` | Start server in foreground |
| `make start-bg` | Start in background (`make logs` to follow) |
| `make stop` | Stop the server |
| `make restart` | Stop and restart in background |
| `make status` | State + VRAM usage |
| `make test` | 6 integration tests |
| `make install-service` | Register systemd service |
| `make enable-service` | Enable auto-start on boot |
| `make litellm-start` | LiteLLM proxy on port 4000 |
| `make clean` | Remove model, logs and `.venv` |

---

## Quick Troubleshooting

**Server won't start — model not found:**
```bash
make download-model && make fix-template
```

**CUDA out of memory:**
```bash
make ollama-unload && make start
```

**llama.cpp compilation fails:**
```bash
rm -rf ~/llama.cpp/build && make build-llama-server
```

**Empty responses:** increase `max_tokens` to ≥ 300 (thinking mode consumes tokens internally before generating the answer).

---

## Full Documentation

**[→ docs/index.md](docs/index.md)** — complete documentation index

| | |
|---|---|
| [Getting Started (detailed)](docs/tutorials/getting-started.md) | Prerequisites, step-by-step, verification |
| [API Usage](docs/how-to/api-usage.md) | All examples: chat, tools, thinking, streaming |
| [LiteLLM](docs/how-to/litellm.md) | Proxy setup, fix "context size exceeded" |
| [OpenCode](docs/how-to/opencode.md) | Terminal AI assistant integration |
| [Production](docs/how-to/production.md) | systemd, Ollama, full troubleshooting |
| [make commands](docs/reference/make-commands.md) | All targets |
| [.env variables](docs/reference/configuration.md) | All variables with defaults |
| [Architecture](docs/explanation/architecture.md) | Technical decisions, why GGUF vs vLLM |
| [Template v18](docs/explanation/template-v18.md) | froggeric — what the template fixes |

---

## Acknowledgements

Template v18 by [**froggeric**](https://huggingface.co/froggeric) — fixes KV cache, tool calling loops and thinking mode for Qwen3.6:  
**[huggingface.co/froggeric/Qwen-Fixed-Chat-Templates](https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates)**

---

*Model: [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) (Alibaba, Apache 2.0) · GGUF: [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)*
