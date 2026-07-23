# Q4_K_M + q4_0 KV Cache — MTP Sweep

**Model:** `Qwen3.6-27B-Q4_K_M.gguf` (~17.1 GB)
**KV Cache:** `q4_0` (Key + Value)
**llama.cpp build:** CUDA_ARCH=86 · FA_ALL_QUANTS=ON

## MTP Sweep (8k context)

| MTP | tok/s | Prefill t/s | TTFT | Acceptance | VRAM |
|---|---|---|---|---|---|
| n=1 | 54.1 | 1057.2 | 3.44s | 81.5% | 16,704 MiB |
| **n=2** | **56.6** | **1074.7** | **3.37s** | **70.6%** | **16,854 MiB** |
| n=3 | 53.9 | 1082.0 | 3.37s | 60.9% | 17,036 MiB |
| n=4 | 50.0 | 1068.3 | 3.39s | 49.2% | 17,192 MiB |
| n=5 | 47.5 | 1053.4 | 3.44s | 45.4% | 17,340 MiB |
| n=6 | 44.3 | 1055.6 | 3.44s | 40.6% | 17,490 MiB |

**Ótimo:** MTP n=2 (56.6 tok/s) — consistente com q8_0 e q5_1.

## Comparação q4_0 vs q5_1 vs q8_0 (8k, MTP n=2)

| Cache | tok/s | VRAM | VRAM vs q8_0 |
|---|---|---|---|
| **q8_0** | 56.5 | 16,986 MiB | — |
| **q4_0** | **56.6** | **16,854 MiB** | **-132 MiB** |
| **q5_1** | 55.2 | 17,120 MiB | +134 MiB |

Em 8k, q4_0 é praticamente idêntico a q8_0 (56.6 vs 56.5 tok/s) com leve economia de VRAM.

## Conclusão

- MTP n=2 é o ótimo independente do tipo de KV cache.
- q4_0 e q8_0 têm desempenho virtualmente idêntico em 8k.
- Veja o [context sweep](README-context-sweep-q4.md) para desempenho em contexto longo (8k→128k).
