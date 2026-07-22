# Qwen3.6 27B — Q4_K_M Benchmark (MTP n=2)

**Model:** `Qwen3.6-27B-Q4_K_M.gguf` (~17.1 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 2 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 2`)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q4_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · `--ctx-checkpoints 8` · **MTP enabled (2 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.
Benchmark: `usage.completion_tokens` do servidor via `stream_options.include_usage`.

| `N_CTX` | Context | tok/s | VRAM used | VRAM free | Prompt time | Status |
|---|---|---|---|---|---|---|
| 8,192 | 8k | **56.5** | 16,986 MiB | 7,140 MiB | 68.6 s | ok |
| 16,384 | 16k | **55.1** | 17,304 MiB | 6,822 MiB | 7.5 s | ok |
| 24,576 | 24k | 52.6 | 17,656 MiB | 6,470 MiB | 12.7 s | ok |
| 32,768 | 32k | 51.0 | 18,008 MiB | 6,118 MiB | 18.4 s | ok |
| 40,960 | 40k | 49.1 | 18,356 MiB | 5,770 MiB | 25.3 s | ok |
| 49,152 | 48k | 47.0 | 18,708 MiB | 5,418 MiB | 32.0 s | ok |
| 57,344 | 56k | 47.4 | 19,064 MiB | 5,062 MiB | 39.0 s | ok |
| 65,536 | 64k | 45.6 | 19,386 MiB | 4,740 MiB | 46.4 s | ok |
| 73,728 | 72k | 46.4 | 19,738 MiB | 4,388 MiB | 54.3 s | ok |
| 81,920 | 80k | 44.4 | 20,090 MiB | 4,036 MiB | 62.1 s | ok |
| 90,112 | 88k | 42.8 | 20,442 MiB | 3,684 MiB | 70.5 s | ok |
| 98,304 | 96k | 40.8 | 20,790 MiB | 3,336 MiB | 79.9 s | ok |
| 106,496 | 104k | 42.0 | 21,146 MiB | 2,980 MiB | 89.2 s | ok |
| 114,688 | 112k | 39.7 | 21,498 MiB | 2,628 MiB | 99.1 s | ok |
| 122,880 | 120k | 39.7 | 21,850 MiB | 2,276 MiB | 109.4 s | ok |
| 131,072 | 128k | **39.0** | 22,202 MiB | 1,924 MiB | 161.8 s | ok **max** |

## Conclusões

- **8k-80k: 44-56 tok/s** — MTP n=2 funciona consistentemente em todo o range.
- **128k é o máximo estável** — 39.0 tok/s, 1,924 MiB VRAM livre.
- **Q4 é mais rápido que Q5** — 56.5 vs 51.8 tok/s @ 8k (+9%).
- **MTP acceptance rate:** ~69-73% (estável em todos os contextos) — 1.4 de 2 draft tokens aceitos em média.
- **VRAM cresce linearmente:** 17.0 GB (8k) → 22.2 GB (128k).
- **Prompt time escala linearmente:** 7s (16k) → 162s (128k). O valor alto em 8k (68.6s) foi primeira execução (warm-up).

## Comparação: Q4_K_M vs Q5_K_M (ambos com MTP n=2)

| Contexto | Q4_K_M | Q5_K_M | Δ |
|---|---|---|---|
| 8k | **56.5** | 51.8 | +9.1% |
| 16k | **55.1** | 52.8 | +4.4% |
| 24k | **52.6** | 49.7 | +5.8% |
| 40k | **49.1** | 47.1 | +4.2% |
| 72k | **46.4** | 41.7 | +11.3% |
| **80k** | **44.4** | 40.8 | +8.8% |
| **128k** | **39.0** | OOM | ✅ |

> Q4_K_M é **4-11% mais rápido** que Q5_K_M com MTP n=2 em todos os contextos, e suporta **128k** de contexto (vs 80k do Q5), porque ocupa 2.7 GB a menos de VRAM para pesos, deixando mais espaço para KV cache.

## MTP Sweep

Veja [README-mtp-sweep-q4.md](README-mtp-sweep-q4.md) para o sweep completo de MTP n=1-6 no Q4_K_M.

## Configuração do servidor

**Padrão (produção):**
```
N_CTX=81920           # 80k — folga para 80k, suporta até 128k
ENABLE_MTP=true
MTP_TOKENS=2
CACHE_TYPE_K=q8_0
CACHE_TYPE_V=q8_0
CTX_CHECKPOINTS=8
CACHE_RAM=10240        # 10 GiB — suporta 2 prompts de 80k em RAM
TEMPLATE_FILE=data/templates/custom/chat_template_v21.jinja
```

**Máximo contexto:**
```
N_CTX=131072           # 128k — máximo estável (39 tok/s)
```

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q4_K_M model uses ~17 GB of VRAM. With 24,576 MB (RTX 3090) and KV cache q8_0, ~4 GB remain for KV cache at 80k context — enough for **128k tokens** max context with MTP n=2 speculative decoding at ~39 tok/s (benchmarked).

**Tested on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
