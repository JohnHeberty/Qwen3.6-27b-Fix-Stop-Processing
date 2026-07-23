# MTP Sweep — Q4_K_M / q5_1 KV Cache no llama.cpp

## Metodologia

- **Modelo:** `Qwen3.6-27B-Q4_K_M.gguf` (17.1 GB)
- **GPU:** RTX 3090 (24,576 MiB VRAM)
- **Engine:** llama.cpp (`--spec-type draft-mtp`) — rebuildado com `CUDA_ARCHITECTURES=86` + `GGML_CUDA_FA_ALL_QUANTS=ON`
- **Contexto:** 8k (prompt ~7.372 tokens, 90% fill)
- **Geração:** 2.048 tokens, temperatura 0.3
- **Benchmark:** `usage.completion_tokens` do servidor via `stream_options.include_usage` + server timings
- **KV cache:** q5_1 (tipo K e V), CTX_CHECKPOINTS=8, CACHE_RAM=10240

## Resultados

| MTP | tok/s | TTFT | Prefill t/s | Draft | Aceitos | % aceit. |
|---|---|---|---|---|---|---|
| n=1 | 53,9 | 3,44s | 1059,4 | 1.130 | 916 | 81,1% |
| **n=2** | **55,2** | **3,50s** | **1038,4** | **1.723** | **1.185** | **68,8%** |
| n=3 | 52,7 | 3,39s | 1073,6 | 2.203 | 1.312 | 59,6% |
| n=4 | 51,3 | 3,37s | 1074,8 | 2.667 | 1.379 | 51,7% |
| n=5 | 46,8 | 36,96s* | 1085,0 | 3.097 | 1.427 | 46,1% |
| n=6 | 39,8 | 48,76s* | 1071,6 | 3.644 | 1.438 | 39,5% |

*TTFT alto em n≥5 é artefato de memória RAM (RSS ~5-6 GB vs ~1,9 GB nos demais), não representa degradação real do prefill.

## Análise

**MTP n=2 é o ótimo para Q4_K_M + q5_1 no llama.cpp** (55,2 tok/s, +2,4% sobre n=1). Com a rebuild otimizada (CUDA_ARCH=86 + FA_ALL_QUANTS), o q5_1 alcançou paridade com q8_0 — os 55,2 tok/s do q5_1 estão a apenas **0,2 tok/s do q8_0 (55,4)**.

O prefill mantém-se consistente em ~1060 t/s independente do MTP n, indicando que o custo do prefill não é afetado pela speculative decoding.

TTFT fica em ~3,4s para n=1-4 com o rebuild, valor estável e sem degradação.

## Comparação q5_1 vs q8_0 (pós-rebuild)

| MTP | q5_1 tok/s | q8_0 tok/s | Δ |
|---|---|---|---|
| n=1 | 53,9 | 53,3 | +1,1% |
| **n=2** | **55,2** | **55,4** | **-0,4%** |
| n=3 | 52,7 | 53,5 | -1,5% |
| n=4 | 51,3 | 49,0 | +4,7% |
| n=5 | 46,8 | 45,1 | +3,8% |
| n=6 | 39,8 | 44,9 | -11,4% |

**Com a rebuild, q5_1 e q8_0 têm desempenho virtualmente idêntico com MTP n=2** (diferença de 0,4%). A economia de ~7% VRAM do q5_1 (~1.500 MiB) torna-se um ganho real sem custo em tok/s.

## Comparação com vLLM devnen

| Engine | KV Cache | Ótimo MTP | tok/s @ 8k |
|---|---|---|---|
| llama.cpp (q8_0) | q8_0 | n=2 | 55,4 |
| llama.cpp (q5_1) | q5_1 | n=2 | 55,2 |
| vLLM (devnen) | FP8 | n=6 | 64,5+ |

## Conclusão

Com a build otimizada (CUDA_ARCH=86 + FA_ALL_QUANTS), **q5_1 alcançou paridade de desempenho com q8_0** em MTP n=2 (diferença de 0,4%). A economia de VRAM de ~7% torna o q5_1 a melhor escolha para produção, especialmente em contextos longos (131k) onde cada MiB de VRAM conta.

MTP ótimo: **n=2** (55,2 tok/s), mesma configuração do q8_0. O rebuild com FA_ALL_QUANTS=ON e CUDA_ARCH específica para RTX 3090 foi determinante para eliminar a diferença de desempenho entre q5_1 e q8_0.
