# Getting Started

From zero to a running server.

---

## Requirements

### Hardware

| Component | Minimum | Tested |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | Zotac RTX 3090 Trinity OC (24,576 MB) |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q4_K_M model uses ~17.1 GB of VRAM. With 24,576 MB (RTX 3090), ~2.9 GB remain for KV cache — enough for 32,768 tokens with MTP speculative decoding at ~70 tok/s (benchmarked).

### Software

| Requirement | Minimum | Validated | Check |
|---|---|---|---|
| OS | Debian 12 / Ubuntu 22.04+ | Debian 12 (Bookworm) | `lsb_release -a` |
| NVIDIA Driver | ≥ 560 | 590.48.01 | `nvidia-smi` |
| CUDA Toolkit | 12.x at `/usr/local/cuda` | 12.8 | `nvcc --version` |
| Git | any | — | `git --version` |

Python, cmake and build-essential are installed automatically by `make setup`. The only manual prerequisites are the NVIDIA driver and CUDA toolkit.

**Install CUDA toolkit if needed (Debian/Ubuntu):**
```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update && apt-get install -y cuda-toolkit-12-8
```

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/JohnHeberty/Qwen3.6-27b-Fix-Stop-Processing.git qwen3
cd qwen3
```

---

## Step 2 — Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in the required token:

```bash
HUGGINGFACE_TOKEN=hf_your_token_here
```

Get your token at: https://huggingface.co/settings/tokens

The other values have sensible defaults. See the [configuration reference](../reference/configuration.md) for adjustments.

---

## Step 3 — Run `make setup`

```bash
make setup
```

The setup runs **7 steps** with sentinels — each one checks if it was already done before acting. Running `make setup` twice is safe.

| Step | Target | What it does |
|---|---|---|
| `[1]` | `make install-system-deps` | apt: python3, cmake, git, build-essential, curl |
| `[2]` | `make setup-cuda` | Verifies CUDA toolkit, registers libcudart |
| `[3]` | `make create-venv` | Creates isolated Python `.venv` |
| `[4]` | `make install-python-deps` | pip: gguf, huggingface-hub, openai, requests |
| `[5]` | `make build-llama-server` | Clones llama.cpp, applies Debian trixie patches, compiles with CUDA |
| `[6]` | `make build-llama-cpp-python` | Compiles llama-cpp-python with GPU offload |
| `[7]` | `make download-model` | Downloads `Qwen3.6-27B-Q4_K_M.gguf` (~17.1 GB) from HuggingFace |

Estimated time: **20–40 minutes** (depends on download speed and CPU for compilation).

---

## Step 4 — Start the server

```bash
make start
```

Wait for the `llama server listening` message (30–60 seconds to load the model).

To run in background:
```bash
make start-bg
make logs   # follow output
```

---

## Step 5 — Verify

```bash
make status
# Server: RUNNING at http://localhost:8000/v1 (model: qwen3)
# GPU:    NVIDIA GeForce RTX 3090, 21000 MiB used, 3100 MiB free

make test
# → 6/6 tests passed
```

---

## Next steps

- [Use the API](../how-to/api-usage.md) — chat, streaming, thinking mode and tool calling examples
- [Command reference](../reference/make-commands.md) — all available targets
