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

## Troubleshooting

### Server won't start — "model not found"

```bash
ls -lh data/models/*.gguf
# If empty:
make download-model
make fix-template
```

### "CUDA out of memory"

```bash
nvidia-smi          # check current usage
make stop           # stop llama-server
make ollama-unload  # free Ollama memory
make start          # try again
```

The Q4_K_M model uses ~21 GB of VRAM. Other CUDA processes must be stopped before starting.

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
make fix-template
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
