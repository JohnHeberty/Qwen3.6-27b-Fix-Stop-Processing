# MTP Sweep — Qwen3.6-35B-A3B (MoE) / q5_1 KV Cache no llama.cpp

## Metodologia

- **Modelo:** `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (~22.6 GB, MoE: 256 experts, 8 ativos/token, 1 MTP head)
- **GPU:** RTX 3090 (24,576 MiB VRAM)
- **Engine:** llama.cpp (`--spec-type draft-mtp`), build com `GGML_CUDA_FA_ALL_QUANTS=ON`
- **Contexto:** 8k (prompt ~7,372 tokens, 90% fill)
- **Geração:** ~2,048 tokens, temperatura 0.3
- **Benchmark:** `usage.completion_tokens` do servidor via `stream_options.include_usage`
- **KV cache:** q5_1, CTX_CHECKPOINTS=8, CACHE_RAM=10240

> **Nota:** cache q4_0 é mais estável em contexto longo pra este modelo — ver [reports/35b-a3b/q4_0/README-mtp-sweep-a3b.md](../q4_0/README-mtp-sweep-a3b.md) e a comparação completa em [../q4_0/README-a3b.md](../q4_0/README-a3b.md).

## Resultados

| `MTP_TOKENS` | tok/s | Prefill t/s | TTFT | Draft total | Aceitos | % aceitação | tok/call | VRAM used | VRAM free |
|---|---|---|---|---|---|---|---|---|---|
| n=1 | 148,5 | 2.524,1 | 1,46s | 1.141 | 906 | 79,4% | 0,79 | 21.792 MiB | 2.334 MiB |
| **n=2** | **148,2** | **2.507,2** | **1,46s** | **1.751** | **1.171** | **66,9%** | **1,34** | **21.856 MiB** | **2.270 MiB** |
| n=3 | 146,7 | 2.490,8 | 1,48s | 1.944 | 1.078 | 55,5% | 1,67 | 21.950 MiB | 2.176 MiB |
| n=4 | 145,5 | 2.546,3 | 1,44s | 2.320 | 1.153 | 49,7% | 1,99 | 22.018 MiB | 2.108 MiB |
| n=5 | 130,4 | 2.471,5 | 1,49s | 3.410 | 1.340 | 39,3% | 1,97 | 22.082 MiB | 2.044 MiB |
| n=6 | 129,2 | 2.465,2 | 1,50s | 3.849 | 1.405 | 36,5% | 2,19 | 22.144 MiB | 1.982 MiB |

## Análise

**n=1 e n=2 ficam estatisticamente empatados** neste cache (148,5 vs 148,2 tok/s — diferença dentro do ruído de uma única execução). Diferente de q8_0 e q4_0, onde n=2 vencia n=1 com uma margem clara (+7-9%), aqui o ganho de aceitação em n=2 (66,9% vs 79,4% de n=1, mas draftando 2 tokens em vez de 1) não se traduz em ganho líquido de throughput.

Mesmo assim, **mantive `MTP_TOKENS=2` como padrão** por consistência com os outros dois caches testados (q8_0, q4_0) e porque n=4 quase empata com n=1/n=2 aqui (145,5 tok/s) — sugerindo que o cache q5_1 tem uma curva de aceitação/throughput mais "achatada" nos primeiros valores de n do que os outros caches, tornando a escolha exata entre 1-4 menos crítica.

## Comparação entre os 3 caches (mesmo modelo, contexto 8k)

| `MTP_TOKENS` | q4_0 tok/s | q5_1 tok/s | q8_0 tok/s |
|---|---|---|---|
| n=1 | 147,5 | **148,5** | 133,3 |
| **n=2** | **155,7** | 148,2 | 142,7 |
| n=3 | 146,8 | 146,7 | 134,3 |

Em n=2 (o padrão adotado), **q4_0 é o mais rápido dos três** (155,7 tok/s). q5_1 fica no meio, q8_0 é o mais lento — mesma ordem observada no sweep de contexto (ver [README-a3b.md](README-a3b.md)).

## Conclusão

q5_1 funciona bem mas **não supera q4_0** em nenhuma métrica relevante pra este modelo — nem em tok/s no ponto ótimo (n=2), nem no teto de contexto útil (88k vs 104k, ver [README-a3b.md](README-a3b.md)). Mantido como dado de comparação; **q4_0 é a recomendação final**.
