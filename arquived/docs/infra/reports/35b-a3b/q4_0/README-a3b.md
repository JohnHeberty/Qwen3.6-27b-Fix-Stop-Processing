# Qwen3.6-35B-A3B (MoE) Benchmark — q4_0 KV Cache (MTP n=2)

**Model:** `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (~22.6 GB, MoE: 256 experts, 8 ativos/token, 1 MTP head)
**Source:** [unsloth/Qwen3.6-35B-A3B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 2 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 2`)
**KV Cache:** q4_0 (requer llama.cpp com `GGML_CUDA_FA_ALL_QUANTS=ON`)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q4_K_M (UD)** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q4_0` · `--cache-type-v q4_0` · `--batch-size 4096` · `--ctx-checkpoints 8` · `--cache-ram 10240` · **MTP enabled (2 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.
Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.
Benchmark: `usage.completion_tokens` do servidor via `stream_options.include_usage`.

| `N_CTX` | Context | tok/s | TTFT | Prefill t/s | MTP acceptance | VRAM used | VRAM free | Status |
|---|---|---|---|---|---|---|---|---|
| 8,192 | 8k | **148.3** | 1.48s | 2.488,9 | 62,7% | 21,842 MiB | 2,284 MiB | ok |
| 16,384 | 16k | 150.0 | 3.13s | 2.716,5 | 67,5% | 21,926 MiB | 2,200 MiB | ok |
| 24,576 | 24k | 144.1 | 5.21s | 2.771,0 | 66,0% | 22,012 MiB | 2,114 MiB | ok |
| 32,768 | 32k | 139.9 | 7.48s | 2.719,4 | 66,2% | 22,104 MiB | 2,022 MiB | ok |
| 40,960 | 40k | 134.6 | 10.23s | 2.671,6 | 65,4% | 22,194 MiB | 1,932 MiB | ok |
| 49,152 | 48k | 133.0 | 12.84s | 2.610,0 | 65,3% | 22,286 MiB | 1,840 MiB | ok |
| 57,344 | 56k | 131.3 | 15.62s | 2.544,3 | 67,7% | 22,380 MiB | 1,746 MiB | ok |
| 65,536 | 64k | 128.2 | 18.67s | 2.458,9 | 68,2% | 22,472 MiB | 1,654 MiB | ok |
| 73,728 | 72k | 122.8 | 32.63s | 2.418,3 | 67,4% | 22,568 MiB | 1,558 MiB | ok |
| 81,920 | 80k | 117.7 | 34.65s | 2.367,1 | 65,4% | 22,660 MiB | 1,466 MiB | ok |
| 90,112 | 88k | 117.4 | 27.82s | 2.317,3 | 67,2% | 22,752 MiB | 1,374 MiB | ok |
| 98,304 | 96k | 112.5 | 31.40s | 2.261,5 | 65,0% | 22,844 MiB | 1,282 MiB | ok |
| **106,496** | **104k** | **111.3** | **35.07s** | **2.209,7** | **66,8%** | **22,938 MiB** | **1,188 MiB** | **ok — candidato a produção** |
| 114,688 | 112k | 11.3 ⚠️ | 48.42s | 1.728,0 | 63,5% | 22,564 MiB | 1,562 MiB | ok (colapso de desempenho) |
| 122,880 | 120k | 13.2 ⚠️ | 53.84s | 1.671,2 | 64,2% | 22,658 MiB | 1,468 MiB | ok (colapso de desempenho) |
| 131,072 | 128k | 13.1 ⚠️ | 58.30s | 1.648,2 | 65,6% | 22,746 MiB | 1,380 MiB | ok — completou, mas inútil |

## Conclusões

- **8k-104k: 111-150 tok/s** — bem mais amplo que o range útil do q8_0 (que colapsava em 80k). **q4_0 empurra o teto de produção de 72k (q8_0) para 104k** — quase 45% mais contexto útil, mantendo velocidade competitiva.
- **Colapso a partir de 112k** — mesmo padrão observado em q8_0: queda abrupta (111.3 → 11.3 tok/s), sem esgotar VRAM tecnicamente (1,188 MiB livres em 104k, ainda 1,562 MiB livres em 112k — na verdade *mais* VRAM livre depois do colapso, porque o próprio colapso reduz o batching/paralelismo interno). Prefill cai de ~2.210 t/s pra ~1.730 t/s no mesmo ponto (~22% de queda) — mais uma vez, o gargalo afeta prefill e decode juntos.
- **q4_0 também é mais rápido que q8_0 no mesmo contexto**, não só mais econômico em VRAM: @72k, 122.8 (q4_0) vs 115.9 tok/s (q8_0) — +5,9%. Ver comparação completa abaixo.
- **MTP acceptance rate:** 62-68% em toda a faixa útil, estável — sem relação com o colapso de desempenho.
- **VRAM cresce ainda mais lentamente que q8_0:** 21.8 GB (8k) → 22.9 GB (104k) — o cache q4_0 ocupa uma fração do que q8_0 ocupava no mesmo contexto, daí o teto mais alto.

## Comparação q4_0 vs q8_0 (mesmo modelo, MTP n=2)

| Contexto | q4_0 tok/s | q8_0 tok/s | Δ | q4_0 VRAM free | q8_0 VRAM free |
|---|---|---|---|---|---|
| 8k | **148.3** | 139.0 | +6,7% | 2,284 MiB | 2,244 MiB |
| 40k | **134.6** | 129.5 | +3,9% | 1,932 MiB | 1,732 MiB |
| 72k | **122.8** | 115.9 | +5,9% | 1,558 MiB | 1,200 MiB |
| **104k** | **111.3** | 10.5 (96k, já colapsado) | — | **1,188 MiB** | — |

**q4_0 vence em todas as métricas** para este modelo: mais rápido, mais VRAM livre em qualquer contexto, e teto de produção quase 45% maior (104k vs 72k). É o cache recomendado para o 35B-A3B — diferente do 27B denso, onde a diferença entre caches era mais uma troca de VRAM por velocidade.

## Configuração do servidor

**Padrão recomendado (produção):**
```
MODEL_FILE=Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
CACHE_TYPE_K=q4_0
CACHE_TYPE_V=q4_0
N_CTX=106496           # 104k — teto de desempenho útil, ver tabela acima
ENABLE_MTP=true
MTP_TOKENS=2
CTX_CHECKPOINTS=8
CACHE_RAM=10240
TEMPLATE_FILE=data/templates/custom/chat_template_v21.jinja
```

> **Não aumente `N_CTX` além de 106496 sem testar primeiro** — colapso de desempenho (não crash) a partir de 112k. Ver tabela completa acima.

## MTP Sweep

Veja [README-mtp-sweep-a3b.md](README-mtp-sweep-a3b.md) para o sweep completo de MTP n=1-6 com q4_0.

## Hardware

| Component | Minimum | Tested/Validated |
|---|---|---|
| GPU NVIDIA VRAM | 24 GB | **Zotac GeForce RTX 3090 Trinity OC — 24,576 MiB VRAM** ✓ |
| RAM | 16 GB | 32 GB |
| Free disk space | 25 GB | 30 GB |

> Requer llama.cpp compilado com `-DGGML_CUDA_FA_ALL_QUANTS=ON` (necessário para Flash Attention suportar KV cache q4_0/q5_1) — ver `llama-cpp-grammar-patches.patch`/`make build-llama-server`.

**Tested on:** Zotac GeForce RTX 3090 Trinity OC · 24,576 MiB VRAM · Driver 590.48.01 · Debian 12 · CUDA 12.8
