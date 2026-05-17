# Infrastructure Configuration

This folder contains the configuration files for running Qwen3.6 27B in production,
integrating with LiteLLM Gateway and OpenCode.

---

## Files

| File | Purpose |
|---|---|
| `qwen-server.service` | systemd unit — auto-start llama-server on boot |
| `litellm_config.yaml` | LiteLLM Gateway proxy configuration |
| `opencode.json` | OpenCode terminal AI assistant configuration |

---

## Context Window Math

Understanding the token budget is critical to avoid `Context size has been exceeded` errors.

```
llama-server hard limit:     63,488 tokens  (--ctx-size 63488)
Reserved for output:        - 4,096 tokens  (max_output_tokens / limit.output)
                            ──────────────
Effective input budget:      59,392 tokens  ← aggressive option adopted
```

**Why 59,392 and not the full 63,488?**

If `max_input_tokens` equals the total context, a request with `input=63488 + output=4096`
would exceed the server's hard limit of 63,488. LiteLLM and OpenCode need room to fit
the output tokens inside the same context window.

**Conservative vs aggressive:**

| Option | `max_input_tokens` | Input headroom | Safety margin |
|---|---|---|---|
| Conservative | 51,200 | 12,288 spare tokens | High — absorbs tools, system prompt, compaction overhead |
| **Aggressive (adopted)** | **59,392** | **4,096 spare tokens** | Tight — maximizes usable context, requires `max_output_tokens` to be respected |

The aggressive option (`59,392`) was adopted here. It maximizes the effective input window
at the cost of a smaller safety margin. If context errors reappear, fall back to `51,200`.

---

## LiteLLM Gateway (`litellm_config.yaml`)

### Key settings

```yaml
model_info:
  max_input_tokens: 59392   # aggressive — 63488 minus output budget
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

Add these to `litellm_config.yaml` to enable pre-call context validation and automatic
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
  "context": 59392,
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

With `context: 59392` and `reserved: 4096`, compaction triggers before the conversation
reaches 59,392 tokens, keeping `4,096` tokens free. If context errors persist, increase
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
--ctx-size 63488 + auto parallel = 2 slots
→ 63,488 ÷ 2 = 31,744 tokens per slot
→ LiteLLM sends up to 59,392 tokens → exceeds 31,744 → "Context size has been exceeded"
```

**Fix:** force `--parallel 1` so the server always uses a single slot with the full
63,488 token KV cache and processes requests sequentially (queued).

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

# Should show: --ctx-size 63488 --parallel 1
```

Or via the API:

```bash
curl -s http://localhost:8000/v1/models | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('n_ctx:', d['data'][0]['meta']['n_ctx'])"
# → n_ctx: 63488
```

If `n_ctx` is less than `63488`, the server was started with a different `N_CTX` value.
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
cp infra/opencode.json ~/your-project/opencode.json
```

---

## Token budget summary

```
llama-server  : 63,488 total
LiteLLM input : 59,392 (max_input_tokens)
LiteLLM output:  4,096 (max_output_tokens)
OpenCode ctx  : 59,392 (limit.context)
OpenCode out  :  4,096 (limit.output)
Compaction buf:  4,096 (reserved)
```

All values are aligned. A request that uses the full input budget (59,392 tokens) plus
the output budget (4,096 tokens) equals 63,488 — exactly the server's hard limit.
