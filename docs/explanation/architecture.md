# Architecture

---

## What this project is

A local inference server for **Qwen3.6** with an OpenAI-compatible API. Any client that speaks OpenAI (Python SDK, LiteLLM, OpenCode, curl) works without modification — just change the `base_url` to `http://localhost:8000/v1`.

The default model is **Qwen3.6-35B-A3B** (MoE, ~3B active params/token) as of `MODEL_FILE=Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` — see [why below](#why-the-35b-a3b-moe-model-instead-of-the-27b-dense-model). The original dense **Qwen3.6 27B** remains fully supported (just point `MODEL_HF`/`MODEL_FILE` back at it) and its benchmarks are kept in `docs/infra/reports/27b-dense/` for comparison.

---

## Technical decisions

### Why llama-server instead of vLLM?

| Aspect | vLLM (previous) | llama-server (current) |
|---|---|---|
| Model format | AWQ (safetensors, ~20 GB) | GGUF Q4_K_M (~17.1 GB) |
| Context on RTX 3090 | 6,272 tokens | 98,304 tokens |
| Customizable template | no (limited) | yes (--chat-template-file at runtime) |
| Compilation required | no | yes (with CUDA) |

The AWQ safetensors model with the Qwen3_5 DeltaNet+Mamba architecture left only ~6,272 tokens of context available on the RTX 3090. The GGUF Q4_K_M (27B dense) uses ~17.1 GB of VRAM for weights, leaving ~5.5 GB for KV cache — enough for 80k tokens at good speed with MTP enabled (benchmarked). This decision predates the later switch to the 35B-A3B MoE model as the default — see [below](#why-the-35b-a3b-moe-model-instead-of-the-27b-dense-model).

### Why GGUF Q4_K_M?

- Good quality/size tradeoff — default quantization for local inference
- No Python dependency for inference (llama-server is C++)
- Jinja2 template patchable directly in the binary (though see [Why froggeric's template v21](#why-froggerics-template-v21) — we stopped doing that)

### Why the 35B-A3B MoE model instead of the 27B dense model?

`Qwen3.6-35B-A3B` is a **Mixture-of-Experts** model: 256 experts, 8 routed per token (see [Qwen3_5 architecture](#qwen3_5-architecture)), so despite being the larger checkpoint on disk (~22.6 GB at Q4_K_M vs ~17.1 GB for the 27B dense Q4_K_M), only **~3B parameters are active per generated token** instead of the full 27B.

Single-user decode on a GPU is memory-bandwidth-bound, not compute-bound — each step re-reads the active weights from VRAM. Fewer active parameters per token means less memory traffic per token, which is why the MoE model benchmarks **~2.5x faster** than the dense model at the same context/MTP settings despite the larger file on disk (122.8 vs ~41.7-46.4 tok/s at 72k context, MTP n=2, q4_0 cache). See [docs/infra/reports/35b-a3b/q4_0/README-a3b.md](../infra/reports/35b-a3b/q4_0/README-a3b.md) for the measured numbers.

The tradeoff: the MoE model's weights alone occupy ~21.5-22 GB VRAM (loading every expert, since llama.cpp offloads them all to GPU by default), leaving noticeably less headroom for KV cache than the 27B dense model did — the 27B's ~17.1 GB left ~5.5 GB free, the 35B-A3B's ~21.5 GB leaves only ~1-2.3 GB. In practice this caps the useful context — the full sweep (three KV cache types tested: q8_0, q5_1, q4_0) shows a hard performance collapse to 6-13 tok/s past a model- and cache-dependent point, not a clean OOM, so it's easy to miss if you don't benchmark the full range: **73,728 (72k) with q8_0, 90,112 (88k) with q5_1, 106,496 (104k) with q4_0** — q4_0 wins on both speed and ceiling, see [docs/infra/index.md](../infra/index.md#qwen36-35b-a3b-mtp-gguf-moe-3b-activetoken--active-default) for the full comparison. `--n-cpu-moe` (offloading some experts to CPU RAM) is an unexplored lever to trade some of that speed back for even more context headroom — see `docs/DICA`.

### Why MTP (Multi-Token Prediction)?

The model embeds MTP prediction head(s) that draft multiple tokens per step. With `--spec-type draft-mtp --spec-draft-n-max N`, the server generates up to `N` candidate tokens per forward pass and validates them against the main model — no separate draft model is needed.

The 27B dense GGUF embeds 3 MTP heads (`qwen35.nextn_predict_layers=3`); the 35B-A3B MoE GGUF embeds only 1 (`qwen35moe.nextn_predict_layers=1`), but llama.cpp can still draft more than 1 token per step by reusing that single head recursively — `--spec-draft-n-max` above 1 still works and still helps. Empirically, **`MTP_TOKENS=2` is the sweet spot for both models**: on the 35B-A3B (q4_0 cache) at 8k context this is 155.7 tok/s at 71.1% acceptance (vs 147.5 tok/s / 80.2% at n=1); acceptance drops fast for every additional draft token beyond 2, faster than the extra draft token's speedup compensates. See `docs/infra/reports/*/*/README-mtp-sweep-*.md` for the sweeps.

### Why froggeric's template v21?

The official Qwen3.6 template has critical bugs in KV cache, tool calling and thinking mode. The v21 fixes all of them. The template is loaded at runtime via `--chat-template-file` in `start-server.sh`, overriding the GGUF-embedded template without modifying the model file.

See details in [explanation/template-v21.md](template-v21.md).

### Why compile llama.cpp from source?

The pip package (`llama-cpp-python`) uses a generic pre-compiled binary. Compiling from source with `-DGGML_CUDA=ON` ensures:
- Full GPU usage (all layers offloaded)
- Optimizations specific to the target card

---

## Qwen3_5 architecture

**Qwen3.6 27B** (dense, `qwen35` in GGUF metadata) uses the **hybrid Qwen3_5 architecture**: 64 layers total, with 48 linear attention layers (DeltaNet/GDN) and 16 full attention layers. All 27B parameters are active per token.

**Qwen3.6-35B-A3B** (MoE, `qwen35moe` in GGUF metadata, current default) shares the same lineage but routes through experts: 41 layers, 256 experts with 8 routed per token, `expert_feed_forward_length=512`, native training context length 262,144 tokens. Only the shared layers plus the 8 selected experts' weights (~3B params worth) are read per generated token, which is the source of its speed advantage over the dense model — see [Why the 35B-A3B MoE model](#why-the-35b-a3b-moe-model-instead-of-the-27b-dense-model) above. Inspect any GGUF's metadata with `python3 -c "from gguf import GGUFReader; ..."` (see `gguf` in `requirements.txt`) if you need to confirm which architecture a given file uses.

---

## Folder structure

```
qwen3/
├── .env                    local configuration (not versioned)
├── .env.example            configuration template (versioned)
├── Makefile                full setup and operations pipeline
├── requirements.txt        Python dependencies
│
├── data/
│   ├── models/             GGUF model(s), gitignored (~22.6 GB for the default 35B-A3B Q4_K_M)
│   ├── templates/          froggeric Jinja2 templates (v21 = default)
│   ├── logs/               runtime logs (gitignored)
│   └── backups/            backups of the original GGUF template (gitignored)
│
├── scripts/
│   ├── setup.sh            installation script (called by Makefile)
│   └── start-server.sh     server startup script
│
├── src/
│
├── tests/
│   └── test_api.py         API integration tests (6 endpoints)
│
├── infra/
│   ├── litellm/
│   │   ├── docker-compose.yaml  LiteLLM + Postgres via Docker
│   │   └── config.yaml          LiteLLM proxy config
│   ├── opencode/
│   │   ├── config.json          OpenCode terminal assistant config
│   │   └── install-plugins.md   Plugin installation guide
│   ├── llama-server/
│   │   └── qwen-server.service  systemd unit for autostart
│   └── repomix/
│       └── repomix.config.json  Repomix codebase packing config
│
└── docs/                   documentation (Diátaxis)
    ├── index.md
    ├── tutorials/
    ├── how-to/
    ├── reference/
    └── explanation/
```

---

## Data flow

```
Client (Python SDK / curl / OpenCode)
    │
    ▼  HTTP POST /v1/chat/completions
llama-server (port 8000)
    │  reads
    ▼
data/models/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf   ← template loaded at runtime via --chat-template-file
    │  offloads
    ▼
GPU (RTX 3090, 24,576 MB VRAM)
    │  offloads weights (~21.5 GB — all 256 experts, only 8/token active at inference)
    │  MTP drafts 2 tokens per step, validates with main model
    ▼
llama-server → streaming/complete response → Client (~111 tok/s with MTP @ 104k context, q4_0 cache, see docs/infra/reports/35b-a3b/q4_0/README-a3b.md)
```
