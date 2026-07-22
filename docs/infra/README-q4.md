# Qwen3.6 27B — Q4_K_M Benchmark

**Model:** `Qwen3.6-27B-Q4_K_M.gguf` (~17.1 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q4_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · **MTP enabled (3 draft tokens)** · Debian · Driver 590.48.01.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.

| `N_CTX` | Context | VRAM used | VRAM free | RAM Δ | tok/s | Prompt time | Status |
|---|---|---|---|---|---|---|---|
| 8,192 | 8k | 17,164 MiB | 6,962 MiB | 682 MiB | 53.5 | 3.4 s | ✓ |
| 16,384 | 16k | 17,486 MiB | 6,640 MiB | 781 MiB | 51.7 | 7.4 s | ✓ |
| 24,576 | 24k | 17,838 MiB | 6,288 MiB | 738 MiB | 53.3 | 12.5 s | ✓ |
| 32,768 | 32k | 18,190 MiB | 5,936 MiB | 892 MiB | 48.2 | 18.0 s | ✓ |
| 40,960 | 40k | 18,538 MiB | 5,588 MiB | 973 MiB | 47.6 | 25.0 s | ✓ |
| 49,152 | 48k | 18,890 MiB | 5,236 MiB | 1,009 MiB | 46.9 | 31.4 s | ✓ |
| 57,344 | 56k | 19,246 MiB | 4,880 MiB | 1,064 MiB | 44.5 | 38.5 s | ✓ |
| 65,536 | 64k | 19,568 MiB | 4,558 MiB | 1,108 MiB | 44.0 | 45.6 s | ✓ |
| 73,728 | 72k | 19,920 MiB | 4,206 MiB | 1,166 MiB | 45.7 | 53.5 s | ✓ |
| 81,920 | 80k | 20,272 MiB | 3,854 MiB | 1,212 MiB | 43.3 | 61.4 s | ✓ |
| 90,112 | 88k | 20,624 MiB | 3,502 MiB | 1,322 MiB | 42.9 | 69.8 s | ✓ |
| 98,304 | 96k | 20,976 MiB | 3,150 MiB | 2,438 MiB | 41.0 | 91.8 s | ✓ |
| 106,496 | 104k | 21,328 MiB | 2,798 MiB | 1,346 MiB | 39.7 | 88.5 s | ✓ |
| 114,688 | 112k | 21,680 MiB | 2,446 MiB | 1,402 MiB | 40.6 | 98.2 s | ✓ |
| 122,880 | 120k | 22,032 MiB | 2,094 MiB | 1,447 MiB | 39.7 | 108.3 s | ✓ |
| 131,072 | 128k | — | — | — | — | — | ✗ OOM |

## Conclusões

- **8k-80k: ~43-53 tok/s** — Performance sólida com MTP em qualquer contexto até 80k.
- **88k-120k: ~40-43 tok/s** — Leve degradação mas totalmente usável.
- **120k é o limite prático** — 2,094 MiB VRAM livre, sem margem para picos.
- **128k: OOM** — Modelo + KV cache excedem 24 GB de VRAM.
- **VRAM cresce linearmente:** 17.2 GB (8k) → 22.0 GB (120k).
- **RAM Δ moderada:** 682 MB (8k) → 1,447 MB (120k) — menor que Q5 devido ao menor modelo.
- **MTP acceptance rate: 64.8%** — significativamente menor que Q5 (84.5%), resultando em ~25-30% menos tok/s.

## Comparação com Q5_K_M

| Métrica | Q4_K_M | Q5_K_M | Delta |
|---|---|---|---|---|
| Modelo | 17.1 GB | 19.8 GB | -2.7 GB |
| tok/s @ 8k | 53.5 | 51.8 | +3.3% |
| tok/s @ 80k | 43.3 | 40.8 | +6.1% |
| VRAM livre @ 80k | 3,854 MiB | 1,586 MiB | +2,268 MiB |
| Limite max | 120k | 80k | +40k |
| MTP acceptance | 64.8% | ~69% | -4% |

Q4_K_M é ligeiramente mais rápido que Q5_K_M (3-6%) e suporta **120k** de contexto (vs 80k), porque ocupa 2.7 GB a menos de VRAM para pesos, deixando mais espaço para KV cache.

## Recomendações

**Geral:** `N_CTX=81920` com `ENABLE_MTP=true` (80k + MTP — 43 tok/s, 3.8 GB VRAM livre)

**Codificação:** `N_CTX=81920` com MTP
- ~43 tok/s com MTP — aceitável para uso interativo no editor
- Contexto de 80k para projetos grandes
- 3.8 GB VRAM livre — muita margem para picos de uso

**Máximo contexto:** `N_CTX=122880` (120k) se precisar de contexto extremo
- ~40 tok/s, mas apenas 2 GB VRAM livre

> **Configuração usada:** `ENABLE_MTP=true`, `MTP_TOKENS=3`, `CACHE_TYPE_K=q8_0`, `CACHE_TYPE_V=q8_0`, `CTX_CHECKPOINTS=16`, `CACHE_RAM=18432`, `N_BATCH=4096`

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q4_K_M model uses ~17 GB of VRAM. With 24,576 MB (RTX 3090) and KV cache q8_0, ~3.8 GB remain for KV cache at 80k context — enough for **120k tokens** max context with MTP speculative decoding at ~40 tok/s (benchmarked).

**Tested on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
