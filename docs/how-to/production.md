# Production & Operations

---

## systemd service

### Install (without auto-start)

```bash
make install-service
```

Registers the `qwen-server` service in systemd. By default it does **not** enable auto-start on boot — use the targets below to control that.

### Auto-start on boot

```bash
make enable-service    # enables auto-start + starts now
make disable-service   # disables auto-start + stops the service
```

> **Warning:** auto-start on boot conflicts with Ollama if both use the GPU. See [Coexistence with Ollama](#coexistence-with-ollama) below.

### Manage the service manually

```bash
sudo systemctl status qwen-server       # current state
sudo systemctl start qwen-server        # start
sudo systemctl stop qwen-server         # stop
sudo systemctl restart qwen-server      # restart
sudo journalctl -u qwen-server -f       # live logs
```

### Install manually (without Makefile)

```bash
sudo cp infra/llama-server/qwen-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qwen-server
```

---

## Coexistence with Ollama

The llama-server and Ollama compete for the 24 GB of GPU VRAM. `make start` already unloads Ollama models automatically before starting. For a permanent adjustment:

```bash
make configure-ollama
# → reduces OLLAMA_KEEP_ALIVE from 30 min to 5 min
# → Ollama frees VRAM 5 min after last use (instead of 30)
```

To manually free Ollama's VRAM at any time:

```bash
make ollama-unload
```

---

## RAM Control & OOM Prevention (LXC/Proxmox)

The llama-server saves prompt cache checkpoints in RAM. With long prompts (70k+ tokens), this can consume 4-5GB and cause OOM kills in containers or memory-limited environments.

### Default configuration (balanced for RTX 3090 + 80k context with MTP)

The `.env` file includes balanced defaults for maximum speed with MTP enabled:

```bash
CACHE_TYPE_K=q8_0        # KV cache quantization (reduces ~50% VRAM vs f16)
CACHE_TYPE_V=q8_0        # KV cache quantization (reduces ~50% VRAM vs f16)
CTX_CHECKPOINTS=8        # default llama.cpp: 32 (causes ~4.8GB RAM usage)
CACHE_RAM=2048           # 2GB RAM cache (good balance)
CACHE_IDLE_SLOTS=1       # keep idle slots warm (faster multi-turn)
N_PREDICT=4096           # limit output length (prevent infinite generation)
N_CTX=81920              # maximum context (80k with MTP on RTX 3090)
ENABLE_MTP=true          # Multi-Token Prediction (~68 tok/s vs ~25 without)
MTP_TOKENS=3             # draft 3 tokens per step (max for Qwen3.6-27B)
```

### If you experience OOM kills

Check for OOM events:

```bash
dmesg -T | grep -i oom
cat /sys/fs/cgroup/memory.events
journalctl -k -b | grep -i killed
```

Adjust in `.env`:

```bash
# Conservative settings (sacrifice performance for stability)
CTX_CHECKPOINTS=4      # fewer checkpoints in RAM
CACHE_RAM=0            # disable RAM cache completely
CACHE_IDLE_SLOTS=0     # release RAM immediately
N_CTX=16384            # reduce context size (uses less VRAM+RAM)
```

### Maximum performance (if you have RAM to spare)

```bash
CTX_CHECKPOINTS=16     # more checkpoints = faster multi-turn
CACHE_RAM=4096         # 4GB RAM cache
CACHE_IDLE_SLOTS=1     # keep idle slots warm
N_CTX=81920            # full context window with MTP
```

> **Note:** The Q4_K_M model uses ~17.1 GB VRAM. On RTX 3090 (24GB), you have ~6.9 GB remaining for KV cache + system operations. Monitor with `nvidia-smi` and `htop`.

---

## Troubleshooting

### Server won't start — "model not found"

```bash
ls -lh data/models/*.gguf
# If empty:
make download-model
```

### "CUDA out of memory"

```bash
nvidia-smi          # check current usage
make stop           # stop llama-server
make ollama-unload  # free Ollama memory
make start          # try again
```

The Q4_K_M model uses ~17.1 GB of VRAM. Other CUDA processes must be stopped before starting.

### "CUDA not found" — `[2] setup-cuda FAIL`

```bash
nvcc --version   # should show version 12.x

# If not found:
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt-get update && apt-get install -y cuda-toolkit-12-8
```

### llama.cpp compilation fails — "mathcalls error"

The Makefile automatically applies the required patches for Debian trixie (glibc 2.40+). If it still fails:

```bash
rm -rf ~/llama.cpp/build
make build-llama-server
```

### Corrupted model or template not applied

```bash
rm data/models/*.gguf
make download-model
```

### Empty responses or thinking mode never finishes

Use `max_tokens` ≥ 300–500 — the model consumes tokens for internal reasoning before generating the answer:

```python
response = client.chat.completions.create(
    model="qwen3",
    messages=[...],
    max_tokens=500
)
```
