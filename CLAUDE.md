# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A local inference server for **Qwen3.6 35B-A3B** (MoE, GGUF via `llama-server` from llama.cpp, ~3B
active params/token) exposing an OpenAI-compatible API on `http://localhost:8000/v1`. Runs alongside
Ollama on the same GPU (single RTX 3090, 24 GB VRAM). Zero-dependency, `make`-driven pipeline:
clone, `cp .env.example .env`, `make setup`, `make start`. The original 27B dense model remains fully
supported (swap `MODEL_HF`/`MODEL_FILE` in `.env`).

The project exists to work around two specific upstream bugs (see `docs/explanation/architecture.md`
and `docs/explanation/template-v21.md`):
- The official Qwen3.6 GGUF ships a buggy Jinja2 chat template (broken tool calling / thinking mode) —
  fixed by loading froggeric's corrected template (v21.3) at runtime via `--chat-template-file`,
  without modifying the GGUF file itself.
- `llama-server --parallel` auto-detection splits the KV cache across concurrent connections, causing
  spurious "Context size exceeded" errors — fixed by forcing `N_PARALLEL=1` (single slot, requests
  queue instead of splitting context).

Repo/docs are bilingual: `Makefile`, shell scripts, and `.env`/`.env.example` comments are in
Portuguese (pt-BR); `README.md` and `docs/` are in English. Match the existing language when editing
a given file.

## Commands

Everything is driven through the `Makefile` (`make help` for the full list). Variables come from
`.env` (copy from `.env.example` first) and can be overridden inline, e.g. `N_CTX=106496 make start`.

**Setup** (idempotent — each step is sentinel-guarded, safe to re-run):
```bash
make setup                    # full pipeline: deps -> CUDA -> venv -> build llama-server -> download model
make build-llama-server       # compile llama-server with CUDA (clones llama.cpp if missing, applies grammar patch)
make rebuild-llama-server     # force clean rebuild
make update-llama-server      # git pull llama.cpp + reapply patches + rebuild
make download-model           # fetch GGUF from HuggingFace (needs HUGGINGFACE_TOKEN in .env)
```

**Server lifecycle:**
```bash
make start        # foreground (Ctrl+C to stop)
make start-bg      # background, logs to data/logs/server.log
make stop / restart / status / logs
```
`make start`/`start-bg` auto-unload any Ollama models from VRAM first (GPU is shared).

**Tests / benchmarks** (require the server to be running on :8000):
```bash
make test                                   # tests/test_api.py — 12 integration tests (health, models, chat, thinking mode, streaming, system prompt, + 6 tool-calling: simple call, tool_choice=required, oneOf schema, correction-after-error, parallel, long multi-tool convo)
python3 tests/test_api.py                   # same, run directly
make benchmark ARGS="--start 16384 --step 16384"   # tests/benchmark.py — context-size sweep, restarts server between runs
python3 tests/sweep_mtp.py --max-n 8         # sweep MTP_TOKENS (draft count) at fixed context
```
There is no unit-test framework/single-test-by-name mechanism — `test_api.py` runs all 12 checks in
one process each time (each has real asserts and fails on wrong content; `BASE_URL`/`TEST_MODEL` are
overridable via env). The template itself has a separate render-level suite:
`python3 data/templates/scripts/test_template.py` (42 checks, incl. the `error_warnings` default-off). `benchmark.py`/`sweep_mtp.py` write CSVs to `data/temp/` and support
`--resume <csv>` to continue an interrupted sweep.

> **Known caveat** (`MAXIMIZE-TOKS.md`): the tok/s figures in `benchmark.py`/`sweep_mtp.py` currently
> count SSE chunks received, not actual tokens from `usage.completion_tokens`. Treat published
> tok/s numbers as approximate until the benchmark is fixed to use `stream_options.include_usage`.

**Integrations:**
```bash
make litellm-start                  # LiteLLM proxy on :4000 (infra/litellm/config.yaml)
```

**Cleanup:**
```bash
make clean            # removes GGUF model, logs, .venv (keeps code/templates)
make clean-logs        # deletes logs older than LOG_RETENTION_DAYS
make cron-clean-logs   # installs a daily cron for the above
```

## Architecture

**Config flow:** `.env` → `Makefile` (reads `.env` vars, applies fallbacks, drives build/setup targets)
→ `scripts/start-server.sh` (re-reads `.env`, applies its own fallbacks, translates every variable
into a `llama-server` CLI flag) → the compiled `llama-server` binary. When changing a runtime
parameter (context size, cache quant, sampling, MTP), the source of truth is `.env`; `start-server.sh`
just forwards it. `src/server.py` is a *separate*, unused-by-default alternative entrypoint that runs
the model through the `llama-cpp-python` Python server instead of the compiled binary — the default
path (`make start`) execs `llama-server` directly and does not go through `src/server.py`.

**Key runtime levers (all in `.env`, documented inline there and in `docs/reference/configuration.md`):**
- `MODEL_FILE` / quantization choice (Q4_K_M/Q5_K_M/Q6_K) — tradeoff between max context and tok/s.
- `ENABLE_MTP` + `MTP_TOKENS` — Multi-Token Prediction speculative decoding using the model's built-in
  MTP heads (no separate draft model needed); `MTP_TOKENS` is a sweet-spot tradeoff between draft
  acceptance rate and speedup, not "higher is always better."
- `DRAFT_ENABLED` + `DRAFT_MODEL_FILE` — alternative speculative decoding using an external small
  draft model instead of MTP; mutually exclusive with MTP (draft wins if enabled).
- `CACHE_TYPE_K` / `CACHE_TYPE_V` — KV cache quantization (q8_0 default), the main lever trading VRAM
  for max context length.
- `N_PARALLEL` — must stay `1` (see the bug this fixes, above); do not "optimize" this back to `-1`/auto.
- `CTX_CHECKPOINTS` / `CACHE_RAM` — bound host-RAM usage of llama-server's prompt-cache checkpoints;
  relevant because this runs in an LXC/Proxmox container prone to OOM on long prompts.
- `TEMPLATE_FILE` — path to the Jinja2 template overriding the GGUF-embedded one. Default is
  `data/templates/custom/chat_template_local.jinja` (our version = froggeric v21.3 + one change).
  The **pristine froggeric v21.3 base is kept untouched** at `custom/chat_template_v21.jinja` — edit
  `chat_template_local.jinja`, not the v21 file, if you need to change template behavior.
- `ERROR_WARNINGS` — `false` by default. Gates the template's tool-error heuristic (injects a
  `⚠️ SYSTEM WARNING` and force-disables thinking after 2 consecutive tool errors). `true` forwards
  `--chat-template-kwargs '{"error_warnings":true}'`. Only `chat_template_local.jinja` honors this
  flag **and uses precise detection** — it flags a tool response only if it *starts with* an explicit
  error marker (`Error:`, `Traceback…`, `Fatal:`, `panic:`) or is a JSON declaring an error
  (`"error"`, `"ok": false`, `"status": "error"`), so `grep` hits / "0 errors" / mid-line "error"
  don't false-positive. Pristine `chat_template_v21.jinja` keeps froggeric's always-on loose string
  match. Enabling is safe now; left off by default as the conservative choice.
- `DRY_MULTIPLIER` (+ `DRY_BASE`/`DRY_ALLOWED_LENGTH`/`DRY_PENALTY_LAST_N`) — DRY sampler,
  **OFF by default (`0`)**. We tried it against the verbatim reasoning-loop, but in agentic/coding use
  it **truncated repeated file paths** (the model kept emitting `src/…/file.py`; DRY penalized the
  repeat and cut the path mid-token → broken tool calls; confirmed in capture, see `HIPOTESE-09`).
  Do not enable for coding. Anti-loop is instead handled by: small client context (~60k),
  `error_warnings`, and `presence_penalty=0.1`; if a verbatim loop returns, prefer a mild
  `REPEAT_PENALTY=1.05` (linear) over DRY (exponential, path-destroying).
- `CAPTURE_LOG` — `false` by default. `true` (or `make capture-on`) logs real request/response
  **content** (`--log-prompts-dir` + `--verbose` to `data/logs/capture/`) so `scripts/analyze-capture.py`
  (`make capture-report`) can flag loops/empty-turns/overflow. Opt-in and voluminous; see
  `docs/how-to/debugging.md`.

**GPU/VRAM sharing with Ollama:** both llama-server and Ollama want the same 24 GB card. `make start`
force-unloads Ollama models before launching. `make configure-ollama` / `make ollama-unload` and the
"Ollama coexistence" doc (`docs/how-to/production.md`) cover the rest. Don't assume the full 24 GB is
available when reasoning about context/VRAM math — check current usage via `make status` or
`nvidia-smi`.

**Downstream integration layer** (`infra/`): LiteLLM gateway config (`infra/litellm/config.yaml`) and
OpenCode terminal-assistant config (`infra/opencode/config.json`) both hardcode a context-window
budget that must stay in sync with `N_CTX` in `.env` (see the "Context Window Math" section of
`infra/README.md` for the exact arithmetic: total ctx − output reserve = effective input budget).
If you change `N_CTX`, check whether `infra/litellm/config.yaml`'s `max_input_tokens` and
`infra/opencode/config.json`'s `limit.context` need updating too.

**Docs layout** follows the Diátaxis framework under `docs/`: `tutorials/` (getting started),
`how-to/` (task-oriented guides), `reference/` (make targets, `.env` variables), `explanation/`
(architecture rationale, template internals). `docs/infra/reports/` is organized **per model first**
(`27b-dense/`, `35b-a3b/`), then per KV cache type (`q4_0/`, `q5_1/`, `q8_0/`) — check
`docs/infra/index.md` for the full map and `docs/infra/configs/current.md` for whatever's actually
running right now (it drifts from what's in `.env.example`/script fallbacks more often than you'd like).

**Known untested performance levers** (as of the 35B-A3B benchmarking pass) — things that came up as
plausible tok/s or context-ceiling levers but weren't (fully) tested, roughly ranked by expected value:
- `--cache-reuse N` — **tested**, no effect (see `docs/infra/configs/current.md`). Simulated
  OpenCode-style history pruning (drop an old turn, keep the long leading context block at
  position 0); default prefix caching already reused 89.6% of the prompt with `cache-reuse=0`,
  identical with `256`. Would only matter if the reusable block itself shifted position (something
  removed *before* it), which isn't the typical pruning pattern.
- Smaller `--ubatch-size` (e.g. 256) specifically at contexts *above* the current collapse point
  (112k+ with q4_0) — untested whether it delays/avoids the collapse the way it changed the ubatch=1024+
  collapse at fixed context. If it does, that raises the real usable context ceiling, not just speed.
- Output quality/coherence of q4_0 vs q8_0 KV cache at long context — **tested**, no difference (see
  `docs/infra/configs/current.md`). Needle-in-haystack (3 unique codes at 10/50/90% of ~46k tokens),
  4/4 runs correct on both caches with production sampling. A greedy-decoding (temp=0) run got q8_0
  stuck in a self-correction loop that never finished, but that reproduced as a known greedy-decoding
  failure mode, not a cache-quality issue — production never uses temp=0 anyway.
- `--spec-draft-p-min` / `--spec-draft-n-min` (default 0.00 / 0) — direct MTP acceptance-criteria knobs,
  never touched (we only ever varied `--spec-draft-n-max` via `MTP_TOKENS`).
- `--threads` / `--threads-batch` (currently `-1` = auto) — deferred, not yet tested.
- `ngram-simple`/`ngram-map-k`/`ngram-mod` spec-types were tested once (lost to `draft-mtp` on a
  code-editing prompt, see `docs/infra/configs/current.md`) but only with default ngram-size params —
  a pure-reformatting task (no new free text) might favor them more; not retested with tuned params.
