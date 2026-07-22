# Qwen3.6 27B — Q5_K_M Benchmark

**Model:** `Qwen3.6-27B-Q5_K_M.gguf` (~19 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q5_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · **MTP enabled (3 draft tokens)** · Debian · Driver 590.48.01.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.

| `N_CTX` | Context | VRAM used | VRAM free | RAM Δ | tok/s | Prompt time | Status |
|---|---|---|---|---|---|---|---|
| 8,192 | 8k | 20,364 MiB | 3,762 MiB | 947 MiB | ~73 | 45.1 s | ✓ |
| 16,384 | 16k | 20,656 MiB | 3,470 MiB | 1,103 MiB | ~69 | 49.2 s | ✓ |
| 24,576 | 24k | 20,948 MiB | 3,178 MiB | 1,362 MiB | ~69 | 49.3 s | ✓ |
| 32,768 | 32k | 21,240 MiB | 2,886 MiB | 1,634 MiB | ~70 | 48.5 s | ✓ |
| 40,960 | 40k | 21,530 MiB | 2,596 MiB | 1,962 MiB | ~69 | 49.6 s | ✓ |
| 49,152 | 48k | 21,824 MiB | 2,302 MiB | 2,233 MiB | ~69 | 49.7 s | ✓ |
| 57,344 | 56k | 22,118 MiB | 2,008 MiB | 2,592 MiB | ~71 | 47.9 s | ✓ |
| 65,536 | 64k | 22,406 MiB | 1,720 MiB | 2,955 MiB | ~68 | 50.4 s | ✓ |
| 73,728 | 72k | 22,702 MiB | 1,424 MiB | 3,253 MiB | ~71 | 47.9 s | ✓ |
| 81,920 | 80k | 22,994 MiB | 1,132 MiB | 3,589 MiB | ~68 | 50.1 s | ✓ padrão |
| 90,112 | 88k | 23,284 MiB | 842 MiB | 3,871 MiB | ~68 | 50.3 s | ✓ |
| 98,304 | 96k | 23,302 MiB | 824 MiB | 4,175 MiB | ~48 | 71.8 s | ⚠ lento |
| 106,496 | 104k | 23,288 MiB | 838 MiB | 4,458 MiB | ~39 | 88.1 s | ⚠ lento |
| 114,688 | 112k | 23,300 MiB | 826 MiB | 4,668 MiB | ~29 | 118.1 s | ⚠ lento |
| 122,880 | 120k | 23,330 MiB | 796 MiB | 4,646 MiB | ~19 | 182.1 s | ✗ |
| 131,072 | 128k | 23,356 MiB | 770 MiB | 4,663 MiB | ~19 | 181.4 s | ✗ |

## Conclusões

- **8k-88k: ~68-72 tok/s** — MTP funciona perfeitamente em qualquer contexto até 88k.
- **96k: ponto de inflexão** — VRAM cheia (~824 MB livre), velocidade cai para ~48 tok/s.
- **120k+: ~19 tok/s** — processamento em RAM, inviável para uso interativo.
- **80k é o padrão** — 68 tok/s, 1.1 GB VRAM livre, máximo estável.
- **88k é o limite** — 68 tok/s, mas apenas 842 MB VRAM livre (sem margem para picos).
- **VRAM cresce linearmente:** 20.4 GB (8k) → 23.0 GB (80k), depois platua.
- **RAM Δ cresce com contexto:** 947 MB (8k) → 3.6 GB (80k) — reflexo do prompt processing.

## Recomendações

**Geral:** `N_CTX=81920` com `ENABLE_MTP=true` (80k + MTP — 68 tok/s, 1.1 GB VRAM livre)

**Codificação:** `N_CTX=81920` com MTP
- ~68 tok/s com MTP — excelente para uso interativo no editor
- Contexto de 80k para projetos grandes com múltiplos arquivos simultâneos
- 1.1 GB VRAM livre dá margem para picos de uso sem risco de OOM

> **Configuração usada:** `ENABLE_MTP=true`, `MTP_TOKENS=3`, `CACHE_TYPE_K=q8_0`, `CACHE_TYPE_V=q8_0`, `CTX_CHECKPOINTS=8`, `CACHE_RAM=2048`, `N_BATCH=4096`

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q5_K_M model uses ~19 GB of VRAM. With 24,576 MB (RTX 3090) and KV cache q8_0, ~1.1 GB remain for KV cache — enough for **81,920 tokens** of context with MTP speculative decoding at ~68 tok/s (benchmarked).

**Tested and validated on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
