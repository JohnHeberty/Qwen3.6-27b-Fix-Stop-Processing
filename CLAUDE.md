# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A local inference server for **Qwen3.8-27B** (dense 27B, hybrid Gated DeltaNet + Attention, GGUF via
`llama-server` from llama.cpp) exposing an OpenAI-compatible API on `http://localhost:8000/v1`.
Runs on 2x RTX 3090 (48 GB VRAM). Zero-dependency, `make`-driven pipeline: clone,
`cp .env.example .env`, `make setup`, `make start`.

Qwen3.8-27B features:
- **Native vision** (image + video understanding via mmproj-F16.gguf, no separate vision server needed)
- **Native MTP** (Multi-Token Prediction) for speculative decoding (MTP n=3, ~58 tok/s decode)
- **Hybrid architecture**: 16×(3×Gated DeltaNet + FFN) + 1×(Gated Attention + FFN) per block
- **262K native context** (extensible to 1M with RoPE scaling)
- **Thinking/reasoning mode** (default on, controlled via REASONING_BUDGET)

Previous models tested and archived (still available as .env configs):
- Qwen3.6-27B Q4_K_M + MTP n=3 (16GB, ~56 tok/s)
- Qwen3.5-35B-A3B APEX MTP n=2 (Ornith, 24GB, ~85 tok/s)

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
make test                                   # tests/test_api.py — integration tests
python3 tests/test_api.py                   # same, run directly
make benchmark ARGS="--start 16384 --step 16384"   # tests/benchmark.py — context-size sweep
python3 tests/sweep_mtp.py --max-n 8         # sweep MTP_TOKENS (draft count) at fixed context
```

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
  MTP heads (no separate draft model needed). Current: MTP n=3 (~58% acceptance, ~58 tok/s decode).
- `CACHE_TYPE_K` / `CACHE_TYPE_V` — KV cache quantization. Current: q8_0 (f16 doesn't fit with Q8_0 model).
- `N_CTX` — context window. Current: 262144 (262k). f16 KV requires reducing to 131k or smaller quant.
- `N_PARALLEL` — must stay `1` (avoids KV cache split bugs).
- `TEMPLATE_FILE` — empty = use GGUF-embedded template (Qwen3.8 qwen35 architecture, no custom needed).
- `MMPROJ` — path to mmproj file for native vision. Current: `mmproj-F16.gguf`.
- `REASONING_BUDGET` — max thinking tokens (default 8192; -1 = off).
- `REASONING_MODE` / `REASONING_FORMAT` — `on` / `deepseek` for reasoning_content support.
- **Client-side `reasoning_effort` does nothing in llama.cpp** — only `none` (disable) is honored.
  Depth is controlled *only* by `REASONING_BUDGET`.
- `DRY_MULTIPLIER` — OFF by default (0). Do not enable for coding (truncates file paths).
- `CAPTURE_LOG` — `false` by default. `true` logs request/response content for debugging.

**Downstream integration layer** (`infra/`): LiteLLM gateway config (`infra/litellm/config.yaml`) and
OpenCode config (`infra/opencode/config.json`) both reference `qwen3.8-27b` and must stay in sync
with `.env` settings (see `infra/README.md` for context window math).

**Hardware:** 2x RTX 3090 (48 GB). GPU 0: ~21.4GB, GPU 1: ~22.6GB with Q8_0 + q8_0 KV + 262k ctx.

## Current production config

Model: **Qwen3.8-27B Q8_0** (27.05 GB)
- Context: 262k, Output: 65k, KV cache: q8_0
- MTP: draft-mtp, n=3 (~58% acceptance)
- Vision: native (mmproj-F16.gguf)
- Sampling (thinking coding): temp=0.6, top_p=0.95, presence_penalty=1.0
- Reasoning: REASONING_BUDGET=8192, REASONING_MODE=on, REASONING_FORMAT=deepseek
