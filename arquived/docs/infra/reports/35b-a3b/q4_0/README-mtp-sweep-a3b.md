# MTP Sweep — Qwen3.6-35B-A3B (MoE) / q4_0 KV Cache no llama.cpp

## Metodologia

- **Modelo:** `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (~22.6 GB, MoE: 256 experts, 8 ativos/token, 1 MTP head)
- **GPU:** RTX 3090 (24,576 MiB VRAM)
- **Engine:** llama.cpp (`--spec-type draft-mtp`), build com `GGML_CUDA_FA_ALL_QUANTS=ON` (necessário para KV cache quantizado abaixo de q8_0)
- **Contexto:** 8k (prompt ~7,372 tokens, 90% fill)
- **Geração:** ~2,048 tokens, temperatura 0.3
- **Benchmark:** `usage.completion_tokens` do servidor via `stream_options.include_usage`
- **KV cache:** q4_0, CTX_CHECKPOINTS=8, CACHE_RAM=10240

## Resultados

| `MTP_TOKENS` | tok/s | Prefill t/s | TTFT | Draft total | Aceitos | % aceitação | tok/call | VRAM used | VRAM free |
|---|---|---|---|---|---|---|---|---|---|
| n=1 | 147,5 | 2.564,0 | 1,43s | 1.136 | 911 | 80,2% | 0,80 | 21.778 MiB | 2.348 MiB |
| **n=2** | **155,7** | **2.564,4** | **1,43s** | **1.690** | **1.201** | **71,1%** | **1,42** | **21.842 MiB** | **2.284 MiB** |
| n=3 | 146,8 | 2.562,1 | 1,43s | 2.300 | 1.279 | 55,6% | 1,67 | 21.936 MiB | 2.190 MiB |
| n=4 | 142,5 | 2.477,1 | 1,48s | 2.740 | 1.296 | 47,3% | 1,89 | 22.004 MiB | 2.122 MiB |
| n=5 | 129,8 | 2.483,8 | 1,48s | 3.095 | 1.191 | 38,5% | 1,93 | 22.068 MiB | 2.058 MiB |
| n=6 | 123,1 | 2.559,7 | 1,43s | 3.810 | 1.290 | 33,9% | 2,03 | 22.130 MiB | 1.996 MiB |

## Análise

**MTP n=2 continua o ótimo** (155,7 tok/s, +5,6% sobre n=1) — mesmo padrão de n=2 vencer visto em q8_0 e no modelo 27B denso.

Curiosidade: **q4_0 é mais rápido que q8_0 em qualquer n** (ex.: n=2 155,7 vs 142,7 tok/s, +9,1%), não só por sobrar mais VRAM — o cache menor também significa menos bytes lidos por passo de atenção, então o ganho de velocidade é real, não só de contexto disponível.

## Comparação q4_0 vs q8_0 (mesmo modelo, mesmo contexto 8k)

| `MTP_TOKENS` | q4_0 tok/s | q8_0 tok/s | Δ |
|---|---|---|---|
| n=1 | 147,5 | 133,3 | +10,7% |
| **n=2** | **155,7** | **142,7** | **+9,1%** |
| n=3 | 146,8 | 134,3 | +9,3% |

## Conclusão

Para **llama.cpp + Qwen3.6-35B-A3B (Q4_K_M) + q4_0 KV cache + RTX 3090**, o MTP ótimo continua **n=2** (155,7 tok/s). Ver [README-a3b.md](README-a3b.md) para o sweep completo de contexto com essa configuração — q4_0 empurra o teto de contexto útil bem além do que q8_0 permite.
