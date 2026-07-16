# Reference — `make` Commands

```bash
make help   # lists all targets with descriptions
```

---

## Setup (zero-dependency)

| Command | Description |
|---|---|
| `make setup` | Full pipeline: runs all 8 steps in order |
| `make install-system-deps` | `[1]` apt: python3, cmake, git, build-essential, curl |
| `make setup-cuda` | `[2]` Verifies CUDA toolkit, registers libcudart |
| `make create-venv` | `[3]` Creates isolated Python `.venv` |
| `make install-python-deps` | `[4]` pip: gguf, huggingface-hub, openai, requests |
| `make build-llama-server` | `[5]` Clones and compiles llama-server with CUDA |
| `make build-llama-cpp-python` | `[6]` Compiles llama-cpp-python with GPU offload |
| `make download-model` | `[7]` Downloads GGUF model from HuggingFace (~16 GB) |
| `make fix-template` | `[8]` Patches the GGUF with template v18 |

Each step uses a **sentinel** — checks if it was already done before acting. Running `make setup` twice is safe.

---

## Server

| Command | Description |
|---|---|
| `make start` | Start server in foreground (Ctrl+C to stop) |
| `make start-bg` | Start in background (log at `data/logs/server.log`) |
| `make stop` | Stop the server (frees VRAM) |
| `make restart` | Stop and restart in background |
| `make status` | Server state + VRAM usage |
| `make logs` | `tail -f data/logs/server.log` |
| `make test` | Runs 6 API integration tests |

---

## systemd service

| Command | Description |
|---|---|
| `make install-service` | Registers `qwen-server.service` (no auto-start) |
| `make enable-service` | Enables auto-start on boot + starts now |
| `make disable-service` | Disables auto-start + stops the service |
| `make start-service` | Starts via systemd without enabling on boot |

---

## Ollama / GPU

| Command | Description |
|---|---|
| `make configure-ollama` | Reduces `OLLAMA_KEEP_ALIVE` from 30 min to 5 min |
| `make ollama-unload` | Forces Ollama to release all models from VRAM now |

---

## LiteLLM

| Command | Description |
|---|---|
| `make litellm-start` | Starts LiteLLM proxy on port 4000 using `infra/litellm/config.yaml` |

---

## Cleanup

| Command | Description |
|---|---|
| `make clean` | Removes GGUF model, logs and `.venv` (keeps code and templates) |

---

## Override variables

Any `.env` variable can be overridden inline:

```bash
N_CTX=81920 make start
PORT=9000 make start
```
