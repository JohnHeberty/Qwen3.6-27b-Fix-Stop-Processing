# Q5_K_M + q4_0 KV Cache — MTP + Context Sweep

**Model:** `Qwen3.6-27B-Q5_K_M.gguf` (~19.8 GB)
**KV Cache:** `q4_0` (Key + Value)
**llama.cpp build:** CUDA_ARCH=86 · FA_ALL_QUANTS=ON
**MTP:** enabled, 2 draft tokens

## MTP Sweep (8k context)

| MTP | tok/s | Prefill t/s | TTFT | Acceptance | VRAM |
|---|---|---|---|---|---|
| n=1 | 49.0 | 1057.8 | 3.44s | 80.4% | 19,154 MiB |
| **n=2** | **53.2** | **1064.0** | **3.42s** | **70.2%** | **19,302 MiB** |
| n=3 | 50.2 | 1069.3 | 3.39s | 57.5% | 19,484 MiB |
| n=4 | 48.9 | 1044.3 | 3.48s | 50.1% | 19,642 MiB |
| n=5 | 45.2 | 1027.4 | 3.54s | 43.5% | 19,790 MiB |
| n=6 | 40.7 | 1042.6 | 3.50s | 37.6% | 19,940 MiB |

**Ótimo:** MTP n=2 (53.2 tok/s).

## Context Sweep (MTP n=2)

| N_CTX | tok/s | TTFT | Prefill t/s | VRAM used | VRAM free |
|---|---|---|---|---|---|
| 8k | **54.0** | 3.52s | 1031.8 | 19,302 MiB | 4,824 MiB |
| 40k | **47.6** | 25.56s | 1064.5 | 20,164 MiB | 3,962 MiB |
| 80k | 41.8 | 97.51s | 924.0 | 21,260 MiB | 2,866 MiB |
| 128k | **36.1** | 120.35s | 796.8 | **22,598 MiB** | **1,528 MiB** |

## Comparação: Q5+q4_0 vs Q4+q4_0 (MTP n=2)

| Contexto | Q5+q4_0 | Q4+q4_0 | Δ |
|---|---|---|---|
| 8k | 54.0 | 56.2 | -3.9% |
| 40k | 47.6 | 51.4 | -7.4% |
| 80k | 41.8 | 43.6 | -4.1% |
| 128k | **36.1** | **37.7** | **-4.2%** |

Q5_K_M é 4-7% mais lento que Q4_K_M com q4_0 cache em todos os contextos. A diferença é menor que os 7-10% observados com q8_0, sugerindo que o cache q4_0 reduz o gargalo de largura de banda, beneficiando mais o modelo maior.
