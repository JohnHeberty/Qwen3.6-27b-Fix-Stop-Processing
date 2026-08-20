# Qwen3.8-27B — local inference server

Production stack: **vLLM TP=2 + AutoRound INT4 + DFlash2** on 2× RTX 3090 (48 GB VRAM),
exposing an OpenAI-compatible API on port 18020.

- Model: `qwen3.8-27b` — dense 27B, hybrid Gated DeltaNet + Attention
- Engine: vLLM (fork in `qwen38-27b-rtx3090/`, v0.27.1 lineage) + `z-lab/Qwen3.8-27B-DFlash2`
  draft model (7 parallel drafts), target `Frozenlock/Qwen3.8-27B-int4-AutoRound`
- Context: 96k (validated pool of 96,538 tokens on this VRAM), ~22 GB VRAM per GPU
- Measured: **~173 tok/s wall / ~177 tok/s decode** (code), ~97 tok/s (narrative),
  TTFT ~90 ms, 68.3% draft acceptance (code)
- Reasoning: thinking on, effort `low`, `preserve_thinking` off
- Tool calling: validated (OpenCode/LiteLLM work against :8080)

## Run

```bash
systemctl start qwen38-27b        # systemd unit, enabled at boot
# or
bash qwen38-27b-rtx3090/single-user/start_qwen.sh  # foreground
```

- Profile: `qwen38-27b-rtx3090/` clone (start_qwen.sh + env vars)
- Unit: `infra/qwen38-27b.service` (installed as `qwen38-27b.service`)
- Logs: `data/logs/qwen38-27b.log`

Notes:
- First boot takes 3-4 min (CUDA profiling of both GPUs).
- No WebUI and no vision support in this stack — that is the trade-off for speed
  (llama.cpp offered both; see `arquived/`).
- `MAX_MODEL_LEN=96000` is the ceiling: 100k missed by ~30 MiB and 128k+ requires
  the custom revision from the original repo post.

## `arquived/` — the llama.cpp era

The previous engine, **llama.cpp (b10502)** with the Q4_K_XL GGUF and MTP speculative
decoding, was archived on 2026-08-19 because it was **slow compared to the vLLM stack**:

| Engine | 1 client | 2 clients (combined) | Context | Vision | WebUI |
|---|---|---|---|---|---|
| llama.cpp b10502 (archived) | ~56-58 tok/s | ~71-74 tok/s | 2×256k | native (mmproj) | yes |
| vLLM + DFlash2 (current) | ~97-177 tok/s | 2 concurrent short | 96k | no | no |

The llama.cpp setup was extensively tuned before being retired: CUDA-graphs build
(+3.8% over the previous build), MTP sweep (n=2, p_min=0.5 → 82.9% acceptance),
2-slot split across GPUs with `TENSOR_SPLIT`, vision offloaded to CPU, Prometheus
metrics, and a full benchmark in `docs/llama-cpp-b10502-benchmark.md`.

Everything from that era is preserved in `arquived/` (versioned in this repo, except
tens of GB of GGUFs, logs and `.env` secrets, which stay in `.gitignore`):

- `.env` + `Makefile` + `scripts/start-server.sh` + `tests/` — the llama.cpp pipeline
- `data/models/` — GGUF checkpoints (Q6_K_XL, UD-Q4_K_XL, Q5_K_M, mmproj)
- `infra/llama-server/` — systemd units + watchdog for the old server
- `env-examples/` — per-model `.env.example` profiles (Ornith, Qwen3.6, Qwen3.8)
- `llama-cpp-grammar-patches.patch`, `docs/`, benchmarks and MTP sweep results

To restore the old stack, move the contents back to the repo root and rebuild:
`make setup && make start` (the Makefile lives in `arquived/`).