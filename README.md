# Qwen3.6 27B — Local GGUF Server · OpenAI-compatible API

**This project fixes the bugs that make Qwen3.6 27B unusable out of the box on a local RTX 3090.**

The community has been reporting these problems ([Reddit](https://www.reddit.com/r/LocalLLaMA/comments/1t49pqu/struggling_with_qwen36_27b_35b_locally_3090_slow/), [llama.cpp #22746](https://github.com/ggml-org/llama.cpp/issues/22746)):

- **Broken tool calling and thinking mode** — the official GGUF ships with a Jinja2 template that has critical bugs in KV cache handling, `<think>` block termination, and function call formatting. Fixed here by patching the template v18 directly into the GGUF binary.
- **KV cache split across concurrent connections** — when `--parallel N` is used and multiple requests arrive simultaneously, llama-server creates N slots and divides the context window between them (63,488 ÷ 2 = 31,744 tokens per slot), causing "Context size exceeded" errors under LiteLLM or agentic workloads. Fixed here by forcing `--parallel 1` so the full 63,488-token KV cache is always available to each request.

The result is a validated setup that actually works: **81,920 token context with MTP** (80k, maximum stable on RTX 3090 with Q5_K_M, KV cache q8_0, and Multi-Token Prediction enabled), functional tool calling, stable thinking mode, and a warm KV cache across requests.

---

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q5_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · **MTP enabled (3 draft tokens)** · Debian · Driver 590.48.01.  
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.

| `N_CTX` | Context | VRAM used | VRAM free | RAM Δ | tok/s | Prompt time | Status |
|---|---|---|---|---|---|---|---|
| 8,192 | 8k | 20,364 MiB | 3,762 MiB | 947 MiB | ~73 | 45.1 s | ✓ |
| 16,384 | 16k | 20,656 MiB | 3,470 MiB | 1,103 MiB | ~69 | 49.2 s | ✓ |
| 24,576 | 24k | 20,948 MiB | 3,178 MiB | 1,362 MiB | ~69 | 49.3 s | ✓ |
| 32,768 | 32k | 21,240 MiB | 2,886 MiB | 1,634 MiB | ~70 | 48.5 s | ✓ |
| 40,960 | 40k | 21,530 MiB | 2,596 MiB | 1,962 MiB | ~69 | 49.6 s | ✓ |
| 49,152 | 48k | 21,824 MiB | 2,302 MiB | 2,233 MiB | ~69 | 49.7 s | ✓ |
| 57,344 | 56k | 22,118 MiB | 2,008 MiB | 2,592 MiB | ~71 | 47.9 s | ✓ |
| 65,536 | 64k | 22,406 MiB | 1,720 MiB | 2,955 MiB | ~68 | 50.4 s | ✓ |
| 73,728 | 72k | 22,702 MiB | 1,424 MiB | 3,253 MiB | ~71 | 47.9 s | ✓ |
| 81,920 | 80k | 22,994 MiB | 1,132 MiB | 3,589 MiB | ~68 | 50.1 s | ✓ padrão |
| 90,112 | 88k | 23,284 MiB | 842 MiB | 3,871 MiB | ~68 | 50.3 s | ✓ |
| 98,304 | 96k | 23,302 MiB | 824 MiB | 4,175 MiB | ~48 | 71.8 s | ⚠ lento |
| 106,496 | 104k | 23,288 MiB | 838 MiB | 4,458 MiB | ~39 | 88.1 s | ⚠ lento |
| 114,688 | 112k | 23,300 MiB | 826 MiB | 4,668 MiB | ~29 | 118.1 s | ⚠ lento |
| 122,880 | 120k | 23,330 MiB | 796 MiB | 4,646 MiB | ~19 | 182.1 s | ✗ |
| 131,072 | 128k | 23,356 MiB | 770 MiB | 4,663 MiB | ~19 | 181.4 s | ✗ |

**Conclusões:**

- **8k-88k: ~68-72 tok/s** — MTP funciona perfeitamente em qualquer contexto até 88k.
- **96k: ponto de inflexão** — VRAM cheia (~824 MB livre), velocidade cai para ~48 tok/s.
- **120k+: ~19 tok/s** — processamento em RAM, inviável para uso interativo.
- **80k é o padrão** — 68 tok/s, 1.1 GB VRAM livre, máximo estável.
- **88k é o limite** — 68 tok/s, mas apenas 842 MB VRAM livre (sem margem para picos).
- **VRAM cresce linearmente:** 20.4 GB (8k) → 23.0 GB (80k), depois platua.
- **RAM Δ cresce com contexto:** 947 MB (8k) → 3.6 GB (80k) — reflexo do prompt processing.

**Recomendação geral:** `N_CTX=81920` com `ENABLE_MTP=true` (80k + MTP — 68 tok/s, 1.1 GB VRAM livre)

**Recomendação para codificação:** `N_CTX=81920` com MTP
- ~68 tok/s com MTP — excelente para uso interativo no editor
- Contexto de 80k para projetos grandes com múltiplos arquivos simultâneos
- 1.1 GB VRAM livre dá margem para picos de uso sem risco de OOM

> **Configuração usada:** `ENABLE_MTP=true`, `MTP_TOKENS=3`, `CACHE_TYPE_K=q8_0`, `CACHE_TYPE_V=q8_0`, `CTX_CHECKPOINTS=8`, `CACHE_RAM=2048`, `N_BATCH=4096`

> Local inference server for **Qwen3.6 27B** using [llama-server](https://github.com/ggml-org/llama.cpp) with GGUF Q5_K_M model and MTP speculative decoding.  
> 100% OpenAI-compatible API · Thinking mode · Tool calling · **81,920 token context with MTP** (~68 tok/s on RTX 3090 with Q5_K_M)

**Tested and validated on: Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8**

---

## Requirements

### Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q5_K_M model uses ~19 GB of VRAM. With 24,576 MB (RTX 3090) and KV cache q8_0, ~1.1 GB remain for KV cache — enough for **81,920 tokens** of context with MTP speculative decoding at ~68 tok/s (benchmarked).

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
| `[7]` download-model | Downloads `Qwen3.6-27B-Q5_K_M.gguf` (~19 GB) |
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

In your projects, point to `http://localhost:4000` with `model="qwen"`. The config already includes `max_input_tokens: 30000` to prevent the `Context size has been exceeded` error.

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
