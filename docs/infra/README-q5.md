# Qwen3.6 27B — Q5_K_M Benchmark (MTP n=2)

**Model:** `Qwen3.6-27B-Q5_K_M.gguf` (~19 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 2 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 2`)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q5_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q8_0` · `--cache-type-v q8_0` · `--batch-size 4096` · `--ctx-checkpoints 8` · **MTP enabled (2 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.
Benchmark: `usage.completion_tokens` do servidor via `stream_options.include_usage`.

| `N_CTX` | Context | tok/s | VRAM used | VRAM free | Prompt time | Status |
|---|---|---|---|---|---|---|
| 8,192 | 8k | **51.8** | 19,432 MiB | 4,694 MiB | 31.1 s | ok |
| 16,384 | 16k | **52.8** | 19,754 MiB | 4,372 MiB | 33.9 s | ok |
| 24,576 | 24k | 49.7 | 20,106 MiB | 4,020 MiB | 31.1 s | ok |
| 32,768 | 32k | 46.7 | 20,458 MiB | 3,668 MiB | 31.0 s | ok |
| 40,960 | 40k | 47.1 | 20,810 MiB | 3,316 MiB | 34.3 s | ok |
| 49,152 | 48k | 46.2 | 21,158 MiB | 2,968 MiB | 31.2 s | ok |
| 57,344 | 56k | 43.8 | 21,514 MiB | 2,612 MiB | 31.2 s | ok |
| 65,536 | 64k | 42.9 | 21,836 MiB | 2,290 MiB | 31.1 s | ok |
| 73,728 | 72k | 41.7 | 22,188 MiB | 1,938 MiB | 31.1 s | ok |
| 81,920 | 80k | **40.8** | 22,540 MiB | 1,586 MiB | 31.0 s | ok **max** |

## Conclusões

- **8k-80k: 40-53 tok/s** — MTP n=2 funciona consistentemente em todo o range.
- **80k é estável com MTP n=2** — 40.8 tok/s, 1,586 MiB VRAM livre.
- **MTP n=2 é ~3-7% mais rápido que n=3** em todos os contextos, e libera VRAM suficiente para 80k (vs OOM com n=3).
- **MTP acceptance rate:** ~68-70% (estável em todos os contextos) — 1.4 de 2 draft tokens aceitos em média.
- **VRAM cresce linearmente:** 19.4 GB (8k) → 22.5 GB (80k).
- **CACHE_RAM e CTX_CHECKPOINTS têm impacto mínimo** no tok/s (diferença <2% entre 2048 e 10240 MiB).

## Comparação: MTP n=2 vs MTP n=3 (Q5_K_M)

| Contexto | MTP n=2 | MTP n=3 | Δ |
|---|---|---|---|
| 8k | **51.8** | 49.4 | +4.9% |
| 16k | **52.8** | 50.2 | +5.2% |
| 24k | **49.7** | 46.8 | +6.2% |
| 40k | **47.1** | 45.8 | +2.8% |
| 72k | **41.7** | 40.4 | +3.2% |
| **80k** | **40.8** | OOM | ✅ |

> MTP n=2 aceita 68-70% dos drafts vs 59-60% do n=3. A aceitação 11% maior mais do que compensa a perda de 1 token draft por call.

## Comparação: Q5_K_M vs Q4_K_M (ambos com MTP n=2)

| Métrica | Q5_K_M | Q4_K_M |
|---|---|---|
| Modelo | 19.8 GB | 17.1 GB |
| tok/s @ 8k | 51.8 | 53.5 |
| tok/s @ 40k | 47.1 | 47.6 |
| tok/s @ 80k | **40.8** | 43.3 |
| Contexto máximo (MTP) | **80k** | 120k |
| VRAM livre @ 80k | 1,586 MiB | 3,854 MiB |

> Q4_K_M é ligeiramente mais rápido e suporta mais contexto que Q5_K_M, porque ocupa menos VRAM para pesos, deixando mais espaço para KV cache.

## Configuração do servidor

**Padrão (produção):**
```
N_CTX=81920          # 80k — máximo estável com MTP n=2
ENABLE_MTP=true
MTP_TOKENS=2
CACHE_TYPE_K=q8_0
CACHE_TYPE_V=q8_0
CTX_CHECKPOINTS=8
CACHE_RAM=10240       # 10 GiB — suporta 2 prompts de 80k em RAM
TEMPLATE_FILE=data/templates/custom/chat_template_v21.jinja
```

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> The Q5_K_M model uses ~22.5 GB of VRAM at 80k context with MTP n=2. With 24,576 MB (RTX 3090) and KV cache q8_0, ~1.6 GB remain. **For maximum context, Q4_K_M (120k) is recommended over Q5_K_M (80k).**

**Tested and validated on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
