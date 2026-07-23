# Q5_K_M + q5_1 KV Cache — MTP + Context Sweep

**Model:** `Qwen3.6-27B-Q5_K_M.gguf` (~19.8 GB)
**KV Cache:** `q5_1` (Key + Value)
**llama.cpp build:** CUDA_ARCH=86 · FA_ALL_QUANTS=ON
**MTP:** enabled, 2 draft tokens

## MTP Sweep (8k context)

| MTP | tok/s | Prefill t/s | TTFT | Acceptance | VRAM |
|---|---|---|---|---|---|
| n=1 | 49.2 | 1057.4 | 3.43s | 81.0% | 19,200 MiB |
| **n=2** | **53.0** | **1067.1** | **3.40s** | **68.7%** | **19,352 MiB** |
| n=3 | 48.4 | 1022.7 | 3.55s | 56.2% | 19,532 MiB |
| n=4 | 46.4 | 1004.9 | 3.63s | 47.8% | 19,690 MiB |
| n=5 | 47.1 | 1002.4 | 3.69s | 47.5% | 19,838 MiB |
| n=6 | 42.3 | 1005.3 | 3.62s | 40.5% | 19,988 MiB |

**Ótimo:** MTP n=2 (53.0 tok/s).

## Context Sweep (MTP n=2)

| N_CTX | tok/s | TTFT | Prefill t/s | VRAM used | VRAM free | Notas |
|---|---|---|---|---|---|---|
| 8k | 51.9 | 3.57s | 1024.0 | 19,352 MiB | 4,774 MiB | |
| 40k | 45.4 | 25.68s | 1059.4 | 20,404 MiB | 3,722 MiB | |
| 80k | 40.1 | 62.95s | 923.7 | 21,740 MiB | 2,386 MiB | |
| 104k | 38.4 | 90.84s | 850.8 | 22,556 MiB | 1,570 MiB | |
| 112k | **8.1** | 116.69s | 716.1 | 22,624 MiB | 1,502 MiB | ❌ colapso VRAM |
| 120k | **8.3** | 142.41s | 631.3 | 22,622 MiB | 1,504 MiB | ❌ |
| 128k | **7.4** | 146.91s | 653.0 | 22,608 MiB | 1,518 MiB | ❌ |

## Análise

**Q5_K_M atinge o limite de VRAM em ~104k com cache q5_1.** Acima disso, o sistema sofre pressão severa de memória (RSS cresce de 1.6 GB para 2.5 GB), e o decode cai de ~38 tok/s para ~8 tok/s — colapso OOM-like.

## Comparação: Q5+q5_1 vs Q5+q4_0 (MTP n=2)

| Contexto | Q5+q5_1 | Q5+q4_0 | Δ |
|---|---|---|---|
| 8k | 51.9 | 54.0 | -3.9% |
| 40k | 45.4 | 47.6 | -4.6% |
| 80k | 40.1 | 41.8 | -4.1% |
| 104k | 38.4 | 39.6 | -3.0% |
| 128k | **7.4** ❌ | **36.1** ✅ | — |

q4_0 é claramente superior para Q5_K_M: oferece desempenho similar até 104k, mas suporta 128k sem colapso, graças aos ~700 MiB extras de VRAM livre.

## Conclusão

- **Q5_K_M + q5_1:** máximo prático ≈ 100k (VRAM livre < 1.6 GB). Não recomendado para contexto longo (>80k).
- **Q5_K_M + q4_0:** suporta 128k estável (36.1 tok/s). Recomendado para Q5_K_M.
- **Q4_K_M + q4_0:** melhor combinação geral (37.7 tok/s @128k, mais VRAM livre).
