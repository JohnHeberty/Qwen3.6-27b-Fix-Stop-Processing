# Reference — `make` Commands

```bash
make help   # lists all targets with descriptions
```

---

## Setup (zero-dependency)

| Command | Description |
|---|---|
| `make setup` | Full pipeline: runs all 7 steps in order |
| `make install-system-deps` | `[1]` apt: python3, cmake, git, build-essential, curl |
| `make setup-cuda` | `[2]` Verifies CUDA toolkit, registers libcudart |
| `make create-venv` | `[3]` Creates isolated Python `.venv` |
| `make install-python-deps` | `[4]` pip: gguf, huggingface-hub, openai, requests |
| `make build-llama-server` | `[5]` Clones and compiles llama-server with CUDA |
| `make build-llama-cpp-python` | `[6]` Compiles llama-cpp-python with GPU offload |
| `make download-model` | `[7]` Downloads GGUF model from HuggingFace (~17.1 GB) |

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
| `make test` | Runs 12 API integration tests (incl. 6 tool-calling scenarios) |

---

## systemd service (portable — install/remove via make, works on any VM)

The unit `infra/llama-server/qwen-server.service` is a **template**: `make install-service`
substitutes `__PROJECT_ROOT__` with the repo's real path, so it works wherever the repo is
cloned. The service runs with **`Restart=always`** (auto-recovers from crashes/OOM, `RestartSec=20`
to let VRAM free between restarts) and starts on boot once enabled. `make` uses `sudo` only when
not root.

| Command | Description |
|---|---|
| `make install-service` | Installs `qwen-server.service` with the resolved repo path (no auto-start yet) |
| `make enable-service` | Enables auto-start on boot **and** starts now (`Restart=always`) |
| `make disable-service` | Disables auto-start + stops (file stays installed) |
| `make start-service` / `make stop-service` | Start / stop now |
| `make service-status` | `systemctl status qwen-server` |
| `make service-logs` | Follow logs (`journalctl -u qwen-server -f`) |
| `make uninstall-service` | Stops, disables and **removes** the unit (repo code untouched) |

> Only one llama-server fits in the 24 GB GPU. Before enabling the service, stop any manually
> started instance (`make stop`) so the two don't contend for VRAM.

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
N_CTX=106496 make start
PORT=9000 make start
```
