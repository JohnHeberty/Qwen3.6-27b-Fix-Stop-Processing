# Infrastructure Configuration

This folder contains the configuration files for running Qwen3.6 27B in production,
integrating with LiteLLM Gateway and OpenCode.

---

## Files

| File | Scope | Purpose |
|---|---|---|
| `opencode/install-plugins.md` | global (once) | OpenCode plugins to install on the machine |
| `opencode/config.json` | global or per-project | OpenCode base configuration |
| `repomix/repomix.config.json` | per-project | Repomix config — clean codebase packing for context |
| `litellm/config.yaml` | server | LiteLLM Gateway proxy configuration |
| `litellm/docker-compose.yaml` | server | LiteLLM + Postgres via Docker Compose |
| `litellm/.env.example` | server | Environment variables template (copy to `.env`) |
| `llama-server/qwen-server.service` | system | systemd unit — auto-start llama-server on boot |

---

## Project Setup Guide

How to configure a new project before opening OpenCode for the best results.

### Step 1 — Start the server

```bash
make start       # foreground
make start-bg    # background (recommended for daily use)
```

Verify: `curl -s http://localhost:8000/v1/models` should return `{"data":[{"id":"qwen3",...}]}`.

---

### Step 2 — Install OpenCode plugins (once per machine)

See [`opencode/install-plugins.md`](opencode/install-plugins.md) for the full list. Run these once globally:

```bash
opencode plugin @tarquinen/opencode-dcp@latest --global
opencode plugin opencode-pty@latest --global
opencode plugin opencode-websearch-cited@1.2.0 --global

# Serena MCP (LSP-aware code intelligence)
docker pull ghcr.io/oraios/serena:1.2.0
```

Verify: `opencode plugin list` should show the installed plugins.

---

### Step 3 — Configure OpenCode

**Option A — Global config** (recommended, applies to all projects):

```bash
mkdir -p ~/.config/opencode
cp infra/opencode/config.json ~/.config/opencode/config.json
```

**Option B — Per-project config** (overrides global for that specific project):

```bash
cp infra/opencode/config.json ~/your-project/opencode.json
```

OpenCode loads `opencode.json` from the **project root first**, then falls back to
`~/.config/opencode/config.json`. Use per-project when you need different models or
permissions for a specific project.

Key settings in the provided config:

| Setting | Value | Why |
|---|---|---|
| `model` | `qwen-local/qwen3` | Default model — the local llama-server |
| `limit.context` | `77,824` | Aligned with LiteLLM `max_input_tokens` |
| `limit.output` | `4,096` | Leaves room within the 81,920 hard limit |
| `compaction.auto` | `true` | Auto-prunes history before hitting the limit |
| `compaction.reserved` | `4,096` | Buffer kept free during compaction |
| `permission.*` | `allow` | All tools pre-approved — no prompts during sessions |

---

### Step 4 — Add Repomix config to your project

[Repomix](https://github.com/yamadashy/repomix) packs your entire codebase into a single
file that OpenCode can use as context. The provided config ignores binaries, lock files,
and build artifacts — keeping the packed output clean and token-efficient.

```bash
cp infra/repomix/repomix.config.json ~/your-project/repomix.config.json
```

To generate a codebase pack (useful before starting a large refactor):

```bash
cd ~/your-project
npx repomix   # outputs repomix-output.xml
```

OpenCode's Repomix MCP plugin can also run this automatically during a session.

---

### Step 5 — (Optional) LiteLLM Gateway

Use LiteLLM when the llama-server is on a **different machine** or when you want a proxy
with context validation and fallbacks.

**First, create the `.env` file:**

```bash
cp infra/litellm/.env.example infra/litellm/.env
# then edit .env and change the values
```

| Variable | Default | Description |
|---|---|---|
| `LITELLM_MASTER_KEY` | `sk-litellm-master` | Auth key clients must pass — must start with `sk-`. Use this as `apiKey` in `opencode.json` |
| `LITELLM_SALT_KEY` | *(random hex)* | Internal salt for key hashing — change in production |
| `UI_USERNAME` | `admin@admin.com` | Login for the LiteLLM web UI at `:4000/ui` |
| `UI_PASSWORD` | `admin1234` | Password for the web UI — change in production |

> **Important:** the `apiKey` in `opencode.json` (and any other client) must match `LITELLM_MASTER_KEY` exactly. If you get `Authentication Error, LiteLLM Virtual Key expected`, this value is wrong or missing the `sk-` prefix.

```bash
make litellm-start   # starts proxy at http://localhost:4000
```

Then in your `opencode.json`, change the provider `baseURL` to:
```json
"baseURL": "http://<server-ip>:4000/v1"
```

And set `apiKey` to match `LITELLM_MASTER_KEY`:
```json
"apiKey": "sk-litellm-master"
```

And change the model name from `qwen-local/qwen3` to `litellm/qwen`.

---

### Pre-flight checklist

Before opening OpenCode in a project:

```
□ make status          → server RUNNING at :8000
□ opencode plugin list → @tarquinen/opencode-dcp, opencode-pty, opencode-websearch-cited
□ opencode.json        → in ~/.config/opencode/ or project root
□ repomix.config.json  → in project root
□ (optional) make litellm-start → proxy at :4000
```

---

## Context Window Math

Understanding the token budget is critical to avoid `Context size has been exceeded` errors.

```
llama-server hard limit:     81,920 tokens  (--ctx-size 81920, zero-penalty on RTX 3090)
Reserved for output:        - 4,096 tokens  (max_output_tokens / limit.output)
                            ──────────────
Effective input budget:      77,824 tokens
```

**Why 77,824 and not the full 81,920?**

If `max_input_tokens` equals the total context, a request with `input=81920 + output=4096`
would exceed the server's hard limit of 81,920. LiteLLM and OpenCode need room to fit
the output tokens inside the same context window.

**Why 81,920 as the limit?**

Benchmarks on RTX 3090 show that up to 81,920 tokens the inference speed is identical to
63,488 (~35 tok/s, fully in VRAM, RSS ~1.5 GB). At 114,688 the speed drops to ~10 tok/s
and RSS doubles. See the benchmark table in the root README for full data.

---

## LiteLLM Gateway (`litellm/config.yaml`)

### Key settings

```yaml
model_info:
  max_input_tokens: 77824   # 81920 minus output budget (4096)
  max_output_tokens: 4096   # must match max_tokens in litellm_params
```

Without `max_input_tokens`, LiteLLM does not know the context window and lets oversized
requests through unchecked — the server then returns an error mid-stream, which surfaces
as `MidStreamFallbackError` in the client.

### Two model deployments, same group name

The config registers two deployments both named `qwen`:

| Deployment | `api_base` | Use case |
|---|---|---|
| `openai/qwen` | `http://localhost:8000/v1` | Requests from the same machine as the Gateway |
| `openai/qwen3` | `http://192.168.1.139:8000/v1` | Requests from remote clients on the LAN |

LiteLLM treats multiple entries with the same `model_name` as a **load-balanced group**
and routes between them. Both point to the same physical llama-server — this is effectively
a primary + alias setup.

### Recommended additions

Add these to `litellm/config.yaml` to enable pre-call context validation and automatic
fallback when the context is exceeded:

```yaml
router_settings:
  enable_pre_call_checks: true   # validates token count BEFORE sending the request

litellm_settings:
  drop_params: true
  context_window_fallbacks:
    - qwen:
        - <fallback-model-name>  # replace with another model if available
```

`enable_pre_call_checks: true` prevents the mid-stream error by rejecting oversized
requests at the router level instead of letting them fail on the server.

---

## OpenCode (`opencode.json`)

### Context limits

```json
"limit": {
  "context": 77824,
  "output": 4096
}
```

Mirrors the LiteLLM values exactly. OpenCode uses `limit.context` to decide when to
trigger compaction (pruning old conversation turns) before sending a request.

### Compaction

```json
"compaction": {
  "auto": true,
  "prune": true,
  "reserved": 4096
}
```

| Field | Value | Meaning |
|---|---|---|
| `auto` | `true` | Automatically compacts when approaching the context limit |
| `prune` | `true` | Removes old assistant output turns to free space |
| `reserved` | `4096` | Tokens kept as buffer during compaction |

With `context: 77824` and `reserved: 4096`, compaction triggers before the conversation
reaches 77,824 tokens, keeping `4,096` tokens free. If context errors persist, increase
`reserved` to `8192` or `12000`.

### Permissions

The config grants `allow` to all tool categories (`read`, `edit`, `bash`, `glob`, `grep`,
`list`, etc.). Adjust `permission.bash` to `"ask"` if you want confirmation before shell
commands in untrusted projects.

---

## Running 2 projects simultaneously — root cause and fix

**Symptom:** error disappears with 1 project, reappears with 2 running at the same time.

**Root cause:** `llama-server --parallel` defaults to `-1` (auto). When 2 concurrent
connections are detected, the server automatically creates **2 slots** and **divides the
KV cache between them**:

```
--ctx-size 81920 + auto parallel = 2 slots
→ 81,920 ÷ 2 = 49,152 tokens per slot
→ LiteLLM sends up to 77,824 tokens → exceeds 49,152 → "Context size has been exceeded"
```

**Fix:** force `--parallel 1` so the server always uses a single slot with the full
81,920 token KV cache and processes requests sequentially (queued).

This is now set via `N_PARALLEL=1` in `.env` and passed as `--parallel "$N_PARALLEL"` in
`scripts/start-server.sh`. **Restart the server after pulling this change:**

```bash
make stop && make start
```

**Trade-off:** with `--parallel 1`, the second project's requests queue behind the first.
Each individual request still completes correctly. Latency increases when both are actively
generating at the exact same time, but there are no context errors.

**If you need true parallel serving** (2 simultaneous streams without queuing), you would
need to double the context: `N_CTX=126976 --parallel 2`, which requires ~16 GB of KV
cache — not possible on a 24 GB card that already uses 16 GB for model weights.

---

## llama-server verification

Confirm the server was started with the correct context size and parallelism:

```bash
# Check running process
ps aux | grep llama-server | grep -v grep

# Should show: --ctx-size 81920 --parallel 1
```

Or via the API:

```bash
curl -s http://localhost:8000/v1/models | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('n_ctx:', d['data'][0]['meta']['n_ctx'])"
# → n_ctx: 81920
```

If `n_ctx` is less than `81920`, the server was started with a different `N_CTX` value.
Check `.env` and restart with `make restart`.

---

## Quick reference

```bash
# Start LiteLLM proxy (port 4000)
make litellm-start

# Start llama-server (port 8000)
make start

# Check server context window
curl -s http://localhost:8000/v1/models | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['meta']['n_ctx'])"

# Copy OpenCode config to a project
cp infra/opencode/config.json ~/your-project/opencode.json
```

---

## Token budget summary

```
llama-server  : 81,920 total  (zero-penalty ceiling on RTX 3090, benchmarked)
LiteLLM input : 77,824 (max_input_tokens)
LiteLLM output:  4,096 (max_output_tokens)
OpenCode ctx  : 77,824 (limit.context)
OpenCode out  :  4,096 (limit.output)
Compaction buf:  4,096 (reserved)
```

All values are aligned. A request that uses the full input budget (77,824 tokens) plus
the output budget (4,096 tokens) equals 81,920 — exactly the server's hard limit.
