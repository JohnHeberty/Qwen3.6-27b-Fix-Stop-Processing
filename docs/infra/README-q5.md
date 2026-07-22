# Qwen3.6 27B — Q5_K_M Benchmark (MTP + Template v21)

**Model:** `Qwen3.6-27B-Q5_K_M.gguf` (~19 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 3 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 3`)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q5_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · **MTP enabled (3 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.

| `N_CTX` | Context | tok/s | VRAM used | VRAM free | Prompt time | Status |
|---|---|---|---|---|---|---|
| 8,192 | 8k | **50.0** | 19,612 MiB | 4,514 MiB | 3.6 s | ok |
| 16,384 | 16k | 47.2 | 19,936 MiB | 4,190 MiB | 46.1 s | ok |
| 24,576 | 24k | 47.6 | 20,288 MiB | 3,838 MiB | 30.7 s | ok |
| 32,768 | 32k | 47.3 | 20,640 MiB | 3,486 MiB | 18.8 s | ok |
| 40,960 | 40k | 44.4 | 20,988 MiB | 3,138 MiB | 25.9 s | ok |
| 49,152 | 48k | 45.0 | 21,338 MiB | 2,788 MiB | 32.6 s | ok |
| 57,344 | 56k | 42.7 | 21,696 MiB | 2,430 MiB | 39.8 s | ok |
| 65,536 | 64k | 41.7 | 22,018 MiB | 2,108 MiB | 47.2 s | ok |
| 73,728 | 72k | **41.7** | 22,370 MiB | 1,756 MiB | 55.5 s | ok **max** |
| 81,920 | 80k | **10.0** | 22,484 MiB | 1,642 MiB | 75.0 s | **cliff** |

## Conclusões

- **8k-72k: 41-50 tok/s** — MTP funciona bem até 72k context.
- **72k é o máximo estável** — 41.7 tok/s, 1,756 MiB VRAM livre (margem mínima).
- **80k = cliff** — MTP + KV cache não cabem na VRAM, cai pra 10 tok/s.
- **VRAM cresce linearmente:** 19.6 GB (8k) → 22.4 GB (72k), depois platua.
- **MTP acceptance rate:** ~84.5% (2,308 amostras) — 2.5 de 3 draft tokens aceitos em média.

## Comparação: Q5_K_M vs Q4_K_M (ambos com MTP)

| Métrica | Q5_K_M | Q4_K_M |
|---|---|---|
| Modelo | 19.8 GB | 17.1 GB |
| tok/s @ 8k | 50.0 | 53.5 |
| tok/s @ 40k | 44.4 | 47.6 |
| tok/s @ 72k | **41.7** | 45.7 |
| Contexto máximo (MTP) | **72k** | 120k |
| VRAM livre @ 72k | 1,756 MiB | 4,206 MiB |

> Q4_K_M é mais rápido e suporta mais contexto que Q5_K_M com MTP, porque ocupa menos VRAM para pesos, deixando mais espaço para KV cache.

## Configuração do servidor

**Padrão (produção):**
```
N_CTX=73728          # 72k — máximo estável com MTP
ENABLE_MTP=true
MTP_TOKENS=3
CACHE_TYPE_K=q8_0
CACHE_TYPE_V=q8_0
CTX_CHECKPOINTS=16
CACHE_RAM=18432
TEMPLATE_FILE=data/templates/custom/chat_template_v21.jinja
```

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q5_K_M model uses ~22 GB of VRAM at 72k context. With 24,576 MB (RTX 3090) and KV cache q8_0, only ~1.7 GB remain. **For maximum context with MTP, Q4_K_M (120k) is recommended over Q5_K_M (72k).**

**Tested and validated on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
