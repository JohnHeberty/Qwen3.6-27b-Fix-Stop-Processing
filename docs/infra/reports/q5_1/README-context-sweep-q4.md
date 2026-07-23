# Context Sweep — Q4_K_M / q5_1 KV Cache (MTP n=2)

**Model:** `Qwen3.6-27B-Q4_K_M.gguf` (~17.1 GB)
**Source:** [unsloth/Qwen3.6-27B-MTP-GGUF](https://huggingface.co/unsloth/Qwen3.6-27B-MTP-GGUF)
**Template:** froggeric v21.3 (`data/templates/custom/chat_template_v21.jinja`)
**MTP:** enabled, 2 draft tokens (`--spec-type draft-mtp --spec-draft-n-max 2`)

## Context window vs VRAM — measured on RTX 3090 (24,576 MiB)

All measurements: **Q4_K_M** · `--n-gpu-layers -1` · `--parallel 1` · `--cache-type-k q5_1` · `--cache-type-v q5_1` · `--batch-size 4096` · `--ctx-checkpoints 8` · **MTP enabled (2 draft tokens)** · Debian 12 · Driver 590.48.01 · CUDA 12.8.

llama.cpp rebuild com `CUDA_ARCHITECTURES=86` + `GGML_CUDA_FA_ALL_QUANTS=ON`.

Inference: ~250k token PDF (Reinforcement Learning book) truncated to 90% of N_CTX.
Benchmark: `usage.completion_tokens` do servidor via `stream_options.include_usage` + server timings.

| N_CTX | Context | tok/s | TTFT | Prefill t/s | VRAM used | VRAM free | Prompt time | Status |
|---|---|---|---|---|---|---|---|---|
| 8,192 | 8k | **55.7** | 3.63s | 1003.3 | 16,902 MiB | 7,224 MiB | 3.6s | ok |
| 16,384 | 16k | **53.9** | 7.68s | 1103.9 | 17,144 MiB | 6,982 MiB | 7.7s | ok |
| 24,576 | 24k | 52.8 | 12.91s | 1111.6 | 17,416 MiB | 6,710 MiB | 12.9s | ok |
| 32,768 | 32k | 49.2 | 18.43s | 1100.0 | 17,688 MiB | 6,438 MiB | 18.4s | ok |
| 40,960 | 40k | 48.0 | 25.38s | 1072.3 | 17,956 MiB | 6,170 MiB | 25.4s | ok |
| 49,152 | 48k | 45.5 | 31.93s | 1046.7 | 18,228 MiB | 5,898 MiB | 31.9s | ok |
| 57,344 | 56k | 45.5 | 38.94s | 1018.6 | 18,504 MiB | 5,622 MiB | 38.9s | ok |
| 65,536 | 64k | 45.5 | 46.25s | 989.3 | 18,746 MiB | 5,380 MiB | 46.2s | ok |
| 73,728 | 72k | 43.7 | 54.39s | 960.1 | 19,018 MiB | 5,108 MiB | 54.4s | ok |
| 81,920 | 80k | 41.3 | 62.12s | 936.9 | 19,290 MiB | 4,836 MiB | 62.1s | ok |
| 90,112 | 88k | 40.5 | 70.84s | 908.2 | 19,562 MiB | 4,564 MiB | 70.8s | ok |
| 98,304 | 96k | 39.9 | 79.96s | 886.6 | 19,830 MiB | 4,296 MiB | 80.0s | ok |
| 106,496 | 104k | 39.2 | 89.88s | 860.9 | 20,106 MiB | 4,020 MiB | 89.9s | ok |
| 114,688 | 112k | 35.7 | 137.58s* | 820.4 | 20,380 MiB | 3,746 MiB | 137.6s | ok |
| 122,880 | 120k | 35.9 | 111.15s | 809.4 | 20,650 MiB | 3,476 MiB | 111.1s | ok |
| 131,072 | 128k | **35.2** | 119.96s | 799.8 | 20,918 MiB | 3,208 MiB | 120.0s | ok **max** |

*TTFT alto em 112k é artefato (RSS 8.9 GB por server start), não representa degradação real do prefill.

## Análise

- **8k-80k: 41-56 tok/s** — MTP n=2 funciona consistentemente em todo o range.
- **128k é o máximo estável com q5_1** — 35.2 tok/s, 3,208 MiB VRAM livre.
- **Prefill TPS cai gradualmente:** de 1.003 (8k) a 800 (128k) — queda de ~20% no range completo.
- **TTFT escala linearmente:** de 3.6s (8k) a 120s (128k) — esperado para prompt fill de 90%.
- **MTP acceptance rate:** ~65-72% — estável em todos os contextos.
- **VRAM cresce linearmente:** 16.9 GB (8k) → 20.9 GB (128k).
- **q5_1 economiza ~1.300 MiB vs q8_0** em todos os contextos.

## Comparação q5_1 vs q8_0 (Q4_K_M, MTP n=2)

| Contexto | q5_1 tok/s | q8_0 tok/s | Δ | q5_1 VRAM | q8_0 VRAM |
|---|---|---|---|---|---|
| 8k | 55.7 | 56.5 | -1.4% | 16,902 | 16,986 |
| 16k | 53.9 | 55.1 | -2.2% | 17,144 | 17,304 |
| 24k | 52.8 | 52.6 | +0.4% | 17,416 | 17,656 |
| 40k | 48.0 | 49.1 | -2.2% | 17,956 | 18,356 |
| 72k | 43.7 | 46.4 | -5.8% | 19,018 | 19,738 |
| 80k | 41.3 | 44.4 | -7.0% | 19,290 | 20,090 |
| 128k | **35.2** | **39.0** | **-9.7%** | **20,918** | **22,202** |

q5_1 é 1-10% mais lento que q8_0, mas economiza 84-1.284 MiB de VRAM. A diferença em tok/s cresce com o contexto porque o KV cache maior amplifica o custo adicional da descompressão q5_1.

## Configuração recomendada (produção, q5_1)

```
N_CTX=131072
ENABLE_MTP=true
MTP_TOKENS=2
CACHE_TYPE_K=q5_1
CACHE_TYPE_V=q5_1
CTX_CHECKPOINTS=8
CACHE_RAM=10240
```

A economia de ~1.3 GB VRAM do q5_1 permite usar 131k de contexto com folga (3.2 GB livres), mantendo tok/s próximo ao q8_0.

## MTP Sweep

Veja [README-mtp-sweep-q4.md](README-mtp-sweep-q4.md) para o sweep completo de MTP n=1-6 no Q4_K_M + q5_1.
