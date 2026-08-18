# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A local inference server for **Qwen3.8-27B** (dense 27B, hybrid Gated DeltaNet + Attention, GGUF via
`llama-server` from llama.cpp) exposing an OpenAI-compatible API on `http://localhost:8080/v1`.
Runs on 2x RTX 3090 (48 GB VRAM). Zero-dependency, `make`-driven pipeline: clone,
copy a config from `env-examples/` to `.env`, `make setup`, `make start`.

Qwen3.8-27B features:
- **Native vision** (image + video understanding via mmproj-F16.gguf, no separate vision server needed)
- **Native MTP** (Multi-Token Prediction) for speculative decoding (MTP n=3; 36-40 tok/s decode at
  short context, 24-26 tok/s in the real long-context agent regime; 355-715 tok/s prompt processing)
- **Hybrid architecture**: 16×(3×Gated DeltaNet + FFN) + 1×(Gated Attention + FFN) per block
- **262K native context** (extensible to 1M with RoPE scaling)
- **Thinking/reasoning mode** (default on, controlled via REASONING_BUDGET)

Previous models tested and archived (still available as .env configs):
- Qwen3.6-27B Q4_K_M + MTP n=3 (16GB, ~56 tok/s)
- Qwen3.5-35B-A3B APEX MTP n=2 (Ornith, 24GB, ~85 tok/s)

Repo is bilingual: `Makefile`, shell scripts, and `.env` comments are in Portuguese (pt-BR);
`README.md` and `CLAUDE.md` are in English. Match the existing language when editing a given file.
(`docs/` exists but is empty — older notes cite `docs/...` paths that no longer exist.)

## Commands

Everything is driven through the `Makefile` (`make help` for the full list). Variables come from
`.env` (start from one of the `env-examples/<gpu-count>/<config>/` files) and can be overridden
inline, e.g. `N_CTX=106496 make start`.

**Setup** (idempotent — each step is sentinel-guarded, safe to re-run):
```bash
make setup                    # full pipeline: deps -> CUDA -> venv -> build llama-server -> download model
make build-llama-server       # compile llama-server with CUDA (clones llama.cpp if missing, applies grammar patch)
                              # patch = llama-cpp-grammar-patches.patch (auto-anchor regex + raises
                              # MAX_REPETITION_THRESHOLD 2000 -> 100000). It went missing from the repo
                              # and was recovered from the live ~/llama.cpp working tree on 2026-08-17;
                              # without it a rebuild silently drops both changes (only a WARN is printed).
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

**Tests / benchmarks** (require the server to be running on :8080):
```bash
make test                       # tests/test_api.py — integration tests
python3 tests/test_api.py       # same, run directly
python3 tests/bench_decode.py   # decode throughput
python3 tests/test-128k.py      # long-context smoke test
```
NOTE: `make benchmark` and `make benchmark-sweep` are **broken** — both invoke `tests/benchmark.py`,
which does not exist in the repo. Use `tests/bench_decode.py` or `scripts/bench-speed.sh` instead
(the latter still references Qwen3.6-era model paths and needs updating before it will run).

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
just forwards it.

**Key runtime levers (all in `.env`):**
- `MODEL_FILE` / quantization choice (Q8_0/Q4_K_M) — tradeoff between max context and tok/s.
  Current: Q8_0 (28GB) with q8_0 KV at 262k context.
- `ENABLE_MTP` + `MTP_TOKENS` — Multi-Token Prediction speculative decoding using the model's built-in
  MTP heads (no separate draft model needed). Current: MTP n=3 (~36-40 tok/s decode measured).
- `CACHE_TYPE_K` / `CACHE_TYPE_V` — KV cache quantization. Current: q8_0 (f16 doesn't fit with Q8_0 model).
- `N_CTX` — context window. Current: 262144 (262k). f16 KV requires reducing to 131k or smaller quant.
- `N_PARALLEL` — must stay `1` (avoids KV cache split bugs).
- `TEMPLATE_FILE` — empty = use GGUF-embedded template (Qwen3.8 qwen35 architecture, no custom needed).
- `MMPROJ` — path to mmproj file for native vision. Current: `mmproj-F16.gguf`.
- `REASONING_BUDGET` — hard ceiling on thinking tokens (8192; -1 = off). It is a **guillotine, not
  a brake**: on hitting it llama.cpp force-closes `</think>` and makes the model answer mid-thought,
  which wrecks tool-call quality. Do not tighten it to reduce verbosity — tighten `REASONING_EFFORT`
  instead. (Learned the hard way: 4096 was tried on 2026-08-17 and 90 of 674 real requests hit it.)
- `REASONING_MODE` / `REASONING_FORMAT` — `on` / `deepseek` for reasoning_content support.
- `REASONING_EFFORT` — forwarded as `--chat-template-kwargs '{"reasoning_effort":"..."}'` (there is
  no `--reasoning-effort` flag). Valid: `low`|`medium`|`xhigh`; `high` is an **alias of `xhigh`**,
  anything else makes the template raise and the request fail. Read the template itself (`GET
  /props`) before trusting these names — what each value *injects* is not what the names suggest:
  - `xhigh` (template default) → "think carefully, validate key assumptions, consider alternatives…"
  - `medium` → **nothing at all**. There is no `medium` branch in the template, so
    `reasoning_instructions` stays empty. It is "no guidance", not "medium effort".
  - `low` → "Keep your thinking brief and focused, moving directly to the conclusion."
  Current: `low` — the only value that actually asks for short thinking. `medium` was used briefly
  and produced long thinking that then hit `REASONING_BUDGET`.
- `REASONING_PRESERVE` — `false` here → `--no-reasoning-preserve`. The Qwen3.8 template keeps
  `preserve_thinking` on by default, so every prior turn's `<think>` block stays in history and
  each agent step re-feeds all accumulated reasoning, inflating prompt size and latency over a
  session. Empty = template default.
- `DRY_MULTIPLIER` — OFF by default (0). Do not enable for coding (truncates file paths).
- `CAPTURE_LOG` — `false` by default. `true` logs request/response content for debugging.

**Server sampling is only a default — clients override it.** Any `temperature`/`top_p`/
`presence_penalty`/`max_tokens` in a request body wins over the `.env` values. Verified: OpenCode
traffic (from a Windows workstation, per the captured prompts) arrived with `temperature=0.6,
top_p=1.0, presence_penalty=1.0, max_tokens=32000` — none of which came from `.env`. So tuning
`.env` alone does not change what such a client actually gets. `.env` remains the source of truth
for this repo — it sets the server defaults, which apply to every request that omits those fields.
Fixing a client's own overrides is a change on that client, out of scope here. (For reference, if it
ever comes up: OpenCode keeps sampling **per agent** — `agent.<name>.{temperature,top_p}` plus a
free-form `options` object — not per model; its *model*-level `temperature` key is a boolean
capability flag, so putting a number there does nothing.)

**Debugging what a client actually sent:** with `CAPTURE_LOG=true`, rendered prompts land in
`data/logs/capture/prompts/<date>/` (this is how the Windows/PowerShell OpenCode client was
identified, and how you can confirm the template rendered "Reasoning effort is set to X").
Effective per-request sampling shows up in `server.log` on the `launching slot` lines.

**Downstream integration layer** (`infra/`): LiteLLM gateway config (`infra/litellm/config.yaml`) and
OpenCode config (`infra/opencode/config.json`) both reference `qwen3.8-27b` on port 8080 and must
stay in sync with `.env` settings. Also here: systemd units + watchdog (`infra/llama-server/`),
logrotate config, and OpenClaw workspace files.

**Hardware:** 2x RTX 3090 (48 GB). GPU 0: ~21.4GB, GPU 1: ~22.7GB with Q8_0 + q8_0 KV + 262k ctx —
little headroom left.

## Current production config

Model: **Qwen3.8-27B Q8_0** (29.0 GB on disk / as reported by the server)
- Port: 8080, Context: 262k, Output: 65k, KV cache: q8_0
- MTP: draft-mtp, n=3
- Vision: native (mmproj-F16.gguf)
- Sampling — official **thinking-mode** profile from the HF model card (verified 2026-08-17):
  temp=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repeat_penalty=1.0.
  The card gives only two profiles (thinking / non-thinking) and **no coding-specific one**; the
  older `temp=0.6 + presence_penalty=1.0` in this repo was an inherited Qwen3.6 recipe mislabeled
  as official. Raise presence_penalty toward 2.0 only if endless repetition shows up (the card
  warns it can cause language mixing).
- Reasoning: REASONING_MODE=on, REASONING_FORMAT=deepseek, REASONING_EFFORT=low,
  REASONING_BUDGET=8192 (safety net only), REASONING_PRESERVE=false
- Measured decode: **24-26 tok/s in the real agent regime** (long context, ~4k-token generations
  taking 140-175s per step); 36-40 tok/s only at short context. Prompt processing 355-715 tok/s.
