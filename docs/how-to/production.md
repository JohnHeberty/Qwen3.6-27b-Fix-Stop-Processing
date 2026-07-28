# Production & Operations

---

## systemd service (auto-recovery from crashes/OOM)

The service runs with **`Restart=always`** (`RestartSec=20`), so if llama-server is OOM-killed or
crashes, systemd brings it back automatically — no manual `make start-bg`. The unit is a
**portable template**: `make install-service` resolves the repo path into it, so the same repo
works on any VM without editing the unit.

### Install (without auto-start)

```bash
make stop            # stop any manually started instance first (one server per GPU)
make install-service # installs the unit with the repo path resolved
```

By default it does **not** enable auto-start on boot — use the targets below to control that.

### Auto-start on boot

```bash
make enable-service    # enables auto-start on boot + starts now (Restart=always)
make disable-service   # disables auto-start + stops (unit stays installed)
```

> **Warning:** only one llama-server fits in the 24 GB GPU. Enabling the service conflicts with a
> manually started instance and with Ollama if both use the GPU. See
> [Coexistence with Ollama](#coexistence-with-ollama).

### Manage the service

```bash
make service-status    # systemctl status qwen-server
make service-logs      # journalctl -u qwen-server -f
make start-service     # start now
make stop-service      # stop now
```

### Remove the service (e.g. before moving VMs)

```bash
make uninstall-service # stop + disable + remove the unit (repo code untouched)
```

The unit template lives at `infra/llama-server/qwen-server.service`; edit it there and re-run
`make install-service` to change service behavior.

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
CACHE_TYPE_K=q4_0        # fastest + highest ceiling for the default 35B-A3B model (see docs/infra/index.md)
CACHE_TYPE_V=q4_0
CTX_CHECKPOINTS=8        # default llama.cpp: 32 (causes ~4.8GB RAM usage)
CACHE_RAM=2048           # 2GB RAM cache (good balance)
CACHE_IDLE_SLOTS=1       # keep idle slots warm (faster multi-turn)
N_PREDICT=8192           # limit output length (prevent infinite generation)
N_CTX=106496             # 104k — max useful context on the default 35B-A3B model + q4_0 (see infra/configs/current.md)
ENABLE_MTP=true          # Multi-Token Prediction (~116-143 tok/s vs ~100-130 without, on the default 35B-A3B model)
MTP_TOKENS=2             # draft 2 tokens per step — benchmarked optimum for both models
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
N_CTX=106496           # 104k — do not raise without re-benchmarking, see note below
```

> **Note:** The default model (35B-A3B MoE, Q4_K_M) uses ~21.5 GB VRAM for weights. On RTX 3090 (24GB), you have only ~1-2.3 GB remaining for KV cache + system operations — noticeably tighter than the 27B dense model's ~17.1 GB/~6.9 GB free. With the recommended q4_0 KV cache, raising `N_CTX` above 106,496 doesn't OOM outright but causes a sharp performance collapse (~111 tok/s → 11-13 tok/s, benchmarked up to 128k) — see [infra/configs/current.md](../infra/configs/current.md). Monitor with `nvidia-smi` and `htop`.

---

## Client configs & secrets

The client configs under `infra/openclaw/` are versioned as **examples** and use placeholders:

| Placeholder | What goes there |
|---|---|
| `${OPENCLAW_BOT_TOKEN}` | Telegram bot token (from @BotFather) |
| `${OPENCLAW_GATEWAY_TOKEN}` | OpenClaw gateway auth token |
| `${LITELLM_API_KEY}` | Must match `LITELLM_MASTER_KEY` in `infra/litellm/.env` |

Never commit real values. Keep the filled-in copy as `infra/openclaw/*.local.json` (gitignored), or
inject the values through the environment on the OpenClaw host.

> These three were previously committed in plaintext and pushed to the public remote. The history was
> purged with `git filter-repo` and force-pushed, **but a purge is not a rotation** — anything already
> cloned or cached keeps the old values. If a secret ever lands in a commit, rotate it first, then
> clean the history.

Also note `LITELLM_MASTER_KEY` defaults to `sk-litellm-master` throughout the docs. That is a weak,
publicly documented default — change it to a real random key before exposing LiteLLM beyond localhost.

## Thinking / reasoning depth

The server sets the reasoning contract explicitly (`REASONING_MODE=on`, `REASONING_FORMAT=deepseek`,
`REASONING_BUDGET=2048` — see [configuration.md](../reference/configuration.md)).

**Client-side `reasoning_effort` has almost no effect against this backend.** llama.cpp honors only
`none` (turns reasoning off); `low`, `medium` and `high` do *not* change how deeply the model thinks.
Practical consequences for OpenClaw:

- `/think off` genuinely disables reasoning.
- `/think medium` keeps it on.
- `/think high` gives you nothing beyond `medium` — don't expect better answers from it.
- The only real depth knob is `REASONING_BUDGET` **on this server**: raise it (3072–4096) if answers
  are shallow on hard problems, lower it (1024) if you see repetitive thinking.

`agents.defaults.thinkingDefault` is set to `medium` in `infra/openclaw/openclaw.json` so the global
default is explicit; a session-level `/think` override still wins over it.

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

The default model uses ~21.5 GB of VRAM for weights alone. Other CUDA processes (including Ollama) must be stopped before starting — `make start` does this automatically.

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
