# MTP Sweep — Q5_K_M no llama.cpp

## Metodologia

- **Modelo:** `Qwen3.6-27B-Q5_K_M.gguf` (19 GB)
- **GPU:** RTX 3090 (24,576 MiB VRAM)
- **Engine:** llama.cpp (`--spec-type draft-mtp`)
- **Contexto:** 8k (prompt ~7,372 tokens, 90% fill)
- **Geração:** 2,048 tokens, temperatura 0.3
- **Benchmark:** `usage.completion_tokens` do servidor via `stream_options.include_usage`
- **KV cache:** q8_0, CTX_CHECKPOINTS=8, CACHE_RAM=10240

## Resultados

| `MTP_TOKENS` | tok/s | Draft total | Aceitos | % aceitação | tok/call |
|---|---|---|---|---|---|
| n=1 | 46.6 | 1.080 | 892 | 82,6% | 0,83 |
| **n=2** | **52.3** | **1.684** | **1.204** | **71,5%** | **1,43** |
| n=3 | 51.2 | 2.196 | 1.314 | 59,8% | 1,79 |
| n=4 | 48.2 | 2.706 | 1.370 | 50,6% | 2,02 |
| n=5 | 42.7 | 3.330 | 1.380 | 41,4% | 2,07 |
| n=6 | 43.5 | 3.498 | 1.464 | 41,9% | 2,51 |

## Análise

**MTP n=2 é o ótimo para Q5_K_M no llama.cpp** (52,3 tok/s). A aceitação cai rapidamente após n=2:

- n=1 → n=2: +12,2% (46,6 → 52,3)
- n=2 → n=3: -2,1% (52,3 → 51,2)
- n=3 → n=4: -5,9% (51,2 → 48,2)
- n=4 → n=5: -11,4% (48,2 → 42,7)
- n=5 → n=6: +1,9% (42,7 → 43,5) — ruído estatístico

O padrão é claro: cada token draft adicional reduz a taxa de aceitação numérica mais do que o ganho marginal compensa. Com n=2 o modelo aceita 71,5% dos drafts (1,43 tok/call), enquanto n=6 aceita apenas 41,9% (2,51 tok/call) — porém o custo computacional por call é ~3x maior.

## Comparação com vLLM devnen

Os resultados do [devnen](https://github.com/devnen/qwen3.6-windows-server) mostram n=6 como ótimo (64,5 tok/s), mas com engine vLLM:

| Engine | Ótimo MTP | tok/s @ 24k | Razão |
|---|---|---|---|
| llama.cpp (este teste) | n=2 | 52,3 | — |
| vLLM (devnen) | n=6 | 64,5 | +23% |

A diferença deve-se a:
1. **vLLM integra MTP ao scheduler** — menor overhead por call speculative
2. **AutoRound INT4** (16,9 GB) vs **GGUF Q5_K_M** (19 GB) — mais VRAM livre para KV cache
3. **Triton Attention + CUDA Graphs** — kernels mais eficientes
4. **KV FP8 E4M3** — cache mais compacto

## Conclusão

Para **llama.cpp + Q5_K_M + RTX 3090**, o MTP ótimo é **n=2** (52,3 tok/s, +12% sobre n=1). Valores acima de n=3 degradam o desempenho por excesso de overhead computacional vs aceitação marginal.
